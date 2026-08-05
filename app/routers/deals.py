"""
Deal Inspector router – serves the live deal browsing and inspection endpoints.
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.dependencies import get_db
from humble_sync.services.evaluator import (
    evaluate_deal,
    fetch_bundle_items,
    get_expired_entries,
    load_active_bundles,
    load_evaluated_bundles_log,
    log_evaluated_bundle,
    mark_expired_entries,
)
from humble_sync.db.models import EvaluatedBundle, Item

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


@router.get("/deals/expired")
def deals_expired(request: Request):
    """
    HTMX partial – marks past deals as expired, fetches all evaluated
    bundle logs, filters to expired entries, and renders the expired_deals
    partial with a clickable list of past bundle evaluations.
    """
    # 1. Transition past deals to expired state
    try:
        mark_expired_entries()
    except Exception:
        pass  # Non-critical

    # 2. Fetch all log records
    try:
        all_entries = load_evaluated_bundles_log()
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "partials/expired_deals.html",
            {"error": str(e)},
        )

    # 3. Filter to expired entries
    expired_bundles = get_expired_entries(all_entries)

    return templates.TemplateResponse(
        request,
        "partials/expired_deals.html",
        {"expired_bundles": expired_bundles},
    )


@router.get("/deals/inspect_expired")
def deals_inspect_expired(
    request: Request,
    url: str = Query(...),
):
    """
    HTMX partial – fetches a saved EvaluatedBundle record by URL and
    renders the deal inspector drawer using the stored evaluation data.
    """
    from humble_sync.db.database import SessionLocal

    db = SessionLocal()
    try:
        record = db.query(EvaluatedBundle).filter(
            EvaluatedBundle.url == url
        ).first()

        if not record:
            return templates.TemplateResponse(
                request,
                "partials/deal_inspector.html",
                {"error": "Expired bundle not found.", "url": url},
            )

        eval_data = record.evaluation or {}

        return templates.TemplateResponse(
            request,
            "partials/deal_inspector.html",
            {
                "url": url,
                "bundle_name": record.bundle_name,
                "total_items": eval_data.get("total_items", 0),
                "matched_count": eval_data.get("matched_count", 0),
                "overlap_percentage": eval_data.get("overlap_percentage", 0.0),
                "new_items_count": len(eval_data.get("new_items", [])),
                "pricing": eval_data.get("pricing", []),
                "tier_breakdown": eval_data.get("tier_breakdown", []),
            },
        )
    finally:
        db.close()


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