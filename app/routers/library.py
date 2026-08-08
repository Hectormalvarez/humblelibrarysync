"""
Library router – serves the library search HTMX partial endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.dependencies import get_db
from humble_sync.db.models import Bundle, Item
from humble_sync.db.queries import (
    get_all_bundles,
    get_all_publishers,
    get_library_metrics,
    get_sort_key,
    get_top_publishers_and_bundles,
)

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")

_VALID_SEARCH_SORTS = {"title_asc", "title_desc", "publisher_asc"}


def _normalize_search_sort(sort: str) -> str:
    """Normalize a sort value for the search endpoint.

    Falls back to ``title_asc`` when the value is invalid or belongs to a
    different view (e.g. ``count_desc`` from a category tab).
    """
    if sort in _VALID_SEARCH_SORTS:
        return sort
    return "title_asc"


@router.get("/library/search")
def library_search(
    request: Request,
    q: str = "",
    publisher: str | None = None,
    bundle_id: int | None = None,
    sort: str = Query("title_asc"),
    limit: int = Query(30, ge=1),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    HTMX partial endpoint – searches items by title (case-insensitive) and
    returns a fragment of HTML to be swapped into the search-results container.
    Supports optional exact-match filters for publisher and bundle_id.
    Designed for HTMX partial rendering.
    """
    active_sort = _normalize_search_sort(sort)
    base_query = db.query(Item)

    # Apply strict equality filters when provided
    if publisher is not None:
        base_query = base_query.filter(Item.publisher == publisher)
    if bundle_id is not None:
        base_query = base_query.filter(Item.bundle_id == bundle_id)
    if q:
        base_query = base_query.filter(Item.title.ilike(f"%{q}%"))

    # Apply sort ordering
    if active_sort == "title_desc":
        base_query = base_query.order_by(Item.title.desc())
    elif active_sort == "publisher_asc":
        base_query = base_query.order_by(Item.publisher.asc(), Item.title.asc())
    else:
        base_query = base_query.order_by(Item.title.asc())

    total_count = base_query.count()
    items = base_query.offset(offset).limit(limit).all()
    has_more = (offset + len(items)) < total_count

    # Resolve active filter objects for the filter pill header
    active_publisher = publisher
    active_bundle = None
    if bundle_id is not None:
        active_bundle = db.query(Bundle).filter(Bundle.id == bundle_id).first()

    # Initial page load state (empty search, first page): aggregate top
    # publishers and bundles so the home page can show category stats.
    if q == "" and publisher is None and bundle_id is None and offset == 0:
        summaries = get_top_publishers_and_bundles(db)
        publishers_summary = summaries["publishers_summary"]
        bundles_summary = summaries["bundles_summary"]
    else:
        publishers_summary = []
        bundles_summary = []

    # For pagination requests (offset > 0), return only the item rows partial
    # so HTMX can swap them in without re-rendering the filter bar or wrapper.
    if offset > 0:
        return templates.TemplateResponse(
            request,
            "partials/item_rows.html",
            {
                "items": items,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "q": q,
                "active_publisher": active_publisher,
                "active_bundle": active_bundle,
                "active_sort": active_sort,
            },
        )

    return templates.TemplateResponse(
        request,
        "partials/search_results.html",
        {
            "items": items,
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "q": q,
            "publishers_summary": publishers_summary,
            "bundles_summary": bundles_summary,
            "active_publisher": active_publisher,
            "active_bundle": active_bundle,
            "active_sort": active_sort,
        },
    )


@router.get("/library/overview")
def library_overview(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    HTMX partial endpoint – returns aggregate library metrics (total items,
    total publishers, total bundles, and per-format availability) for the
    default right inspector pane. The rendered partial is swapped into the
    ``#inspector-drawer`` container on page load.
    """
    metrics = get_library_metrics(db)

    return templates.TemplateResponse(
        request,
        "partials/library_overview.html",
        metrics,
    )


@router.get("/library/publishers")
def library_publishers(
    request: Request,
    q: str = "",
    sort: str = Query("title_asc"),
    db: Session = Depends(get_db),
):
    """
    HTMX partial endpoint – returns every publisher in the library along
    with the total number of items attributed to it.  The rendered partial
    is swapped into the ``#master-stream`` container, replacing the
    previous view.
    """
    publishers, active_sort = get_all_publishers(db, q=q, sort=sort)
    return templates.TemplateResponse(
        request,
        "partials/publisher_list.html",
        {"publishers": publishers, "active_sort": active_sort},
    )


@router.get("/library/bundles")
def library_bundles(
    request: Request,
    q: str = "",
    sort: str = Query("title_asc"),
    db: Session = Depends(get_db),
):
    """
    HTMX partial endpoint – returns every bundle in the library along
    with the total number of items contained in it.  The rendered partial
    is swapped into the ``#master-stream`` container.
    """
    bundles, active_sort = get_all_bundles(db, q=q, sort=sort)
    return templates.TemplateResponse(
        request,
        "partials/bundle_list.html",
        {"bundles": bundles, "active_sort": active_sort},
    )


@router.get("/library/items/{item_id}")
def library_item_detail(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
):
    """
    HTMX partial endpoint – returns the full detail view for a single
    ``Item`` (publisher, bundle, type, available formats, and download
    keys/links).  The item is fetched with a join to its parent ``Bundle``
    so the template can render the bundle title without an extra query.
    Returns HTTP 404 when the requested item does not exist.  The rendered
    partial is swapped into the ``#inspector-drawer`` container.
    """
    # Join Bundle so the template can access `item.bundle.title` without a
    # lazy-load round trip.  `first()` returns None if no row matches.
    item = (
        db.query(Item)
        .join(Bundle, Item.bundle_id == Bundle.id)
        .filter(Item.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    return templates.TemplateResponse(
        request,
        "partials/item_inspector.html",
        {"item": item},
    )
