"""
Deal Inspector router – serves the live deal browsing and inspection endpoints.
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.dependencies import get_db
from bundle_inspector import (
    evaluate_deal,
    fetch_bundle_items,
    load_active_bundles,
    log_evaluated_bundle,
)
from models import Item

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")

_CATEGORY_GROUPS = {
    "books": "📚 Books",
    "games": "🎮 Games",
    "software": "💻 Software",
}


def _categorise_bundle_url(url: str) -> str:
    """Return the category key (books/games/software) from a bundle URL."""
    if "/books/" in url:
        return "books"
    if "/games/" in url:
        return "games"
    if "/software/" in url:
        return "software"
    return "books"


@router.get("/deals")
def deals_page(request: Request):
    """Serve the main Deal Inspector page."""
    return templates.TemplateResponse(request, "pages/deals.html")


@router.get("/deals/live")
def deals_live(request: Request):
    """
    HTMX partial – fetches active bundles via load_active_bundles(),
    groups them by category, and renders the deal_list partial.
    """
    try:
        bundles = load_active_bundles()
    except RuntimeError as e:
        return templates.TemplateResponse(
            request,
            "partials/deal_list.html",
            {"error": str(e)},
        )

    # Group bundles by category
    grouped: dict[str, list[dict]] = {"books": [], "games": [], "software": []}
    for b in bundles:
        cat = _categorise_bundle_url(b.get("url", ""))
        grouped.setdefault(cat, []).append(b)

    categories = [
        {"key": k, "label": _CATEGORY_GROUPS.get(k, k), "bundles": grouped.get(k, [])}
        for k in ("books", "games", "software")
    ]

    return templates.TemplateResponse(
        request,
        "partials/deal_list.html",
        {"categories": categories},
    )


@router.get("/deals/reset")
def deals_reset(request: Request):
    """HTMX partial – resets the inspector drawer to its default empty state."""
    return templates.TemplateResponse(
        request,
        "partials/deal_inspector.html",
        {
            "placeholder": True,
        },
    )


@router.get("/deals/inspect")
def deals_inspect(
    request: Request,
    url: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    HTMX partial – fetches bundle items from *url*, evaluates overlap
    against the user's library, logs the evaluation, and renders the
    deal inspector drawer.
    """
    # 1. Fetch bundle items & pricing from Humble Bundle
    try:
        bundle_data = fetch_bundle_items(url)
    except RuntimeError as e:
        return templates.TemplateResponse(
            request,
            "partials/deal_inspector.html",
            {"error": f"Failed to load bundle: {e}", "url": url},
        )

    bundle_name = bundle_data.get("bundle_name", "Unknown Bundle")
    bundle_items = bundle_data.get("items", [])
    pricing = bundle_data.get("pricing", [])
    tier_item_map = bundle_data.get("tier_item_map", {})

    # 2. Fetch library items from DB
    library_rows = db.query(Item).all()
    library_items = [{"title": row.title} for row in library_rows]

    # 3. Evaluate overlap
    eval_data = evaluate_deal(bundle_items, library_items, pricing, tier_item_map)

    # 4. Log evaluation
    try:
        log_evaluated_bundle(
            bundle_name=bundle_name,
            bundle_url=url,
            machine_name=bundle_data.get("machine_name", ""),
            end_date="",
            eval_data=eval_data,
        )
    except Exception:
        pass  # Non-critical logging error

    return templates.TemplateResponse(
        request,
        "partials/deal_inspector.html",
        {
            "url": url,
            "bundle_name": bundle_name,
            "total_items": eval_data.get("total_items", 0),
            "matched_count": eval_data.get("matched_count", 0),
            "overlap_percentage": eval_data.get("overlap_percentage", 0.0),
            "new_items_count": len(eval_data.get("new_items", [])),
            "pricing": pricing,
            "tier_breakdown": eval_data.get("tier_breakdown", []),
        },
    )