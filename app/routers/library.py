"""
Library router – serves the library search HTMX partial endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.dependencies import get_db
from models import Bundle, Item

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("/library/search")
def library_search(
    request: Request,
    q: str = "",
    publisher: str | None = None,
    bundle_id: int | None = None,
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
    base_query = db.query(Item)

    # Apply strict equality filters when provided
    if publisher is not None:
        base_query = base_query.filter(Item.publisher == publisher)
    if bundle_id is not None:
        base_query = base_query.filter(Item.bundle_id == bundle_id)
    if q:
        base_query = base_query.filter(Item.title.ilike(f"%{q}%"))

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
        publisher_rows = (
            db.query(Item.publisher, func.count(Item.id).label("count"))
            .group_by(Item.publisher)
            .order_by(func.count(Item.id).desc())
            .limit(5)
            .all()
        )
        bundle_rows = (
            db.query(Bundle.title, func.count(Item.id).label("count"))
            .join(Item, Item.bundle_id == Bundle.id)
            .group_by(Bundle.id)
            .order_by(func.count(Item.id).desc())
            .limit(5)
            .all()
        )
        publishers_summary = [
            {"name": name, "count": count} for name, count in publisher_rows
        ]
        bundles_summary = [
            {"name": name, "count": count} for name, count in bundle_rows
        ]
    else:
        publishers_summary = []
        bundles_summary = []

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
    total_items = db.query(func.count(Item.id)).scalar() or 0
    total_publishers = db.query(func.count(distinct(Item.publisher))).scalar() or 0
    total_bundles = db.query(func.count(Bundle.id)).scalar() or 0

    # Count items per format by scanning the available_formats JSON arrays
    # in Python. This keeps the query portable across SQL backends (SQLite
    # stores JSON columns as text, so backend-specific JSON functions would
    # otherwise be needed).
    format_counts: dict[str, int] = {}
    for (formats,) in db.query(Item.available_formats).all():
        for fmt in formats or []:
            format_counts[fmt] = format_counts.get(fmt, 0) + 1

    format_breakdown = [
        {"format": fmt, "count": format_counts[fmt]}
        for fmt in sorted(
            format_counts, key=lambda f: (-format_counts[f], f)
        )
    ]

    return templates.TemplateResponse(
        request,
        "partials/library_overview.html",
        {
            "total_items": total_items,
            "total_publishers": total_publishers,
            "total_bundles": total_bundles,
            "format_breakdown": format_breakdown,
        },
    )


@router.get("/library/publishers")
def library_publishers(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    HTMX partial endpoint – returns every publisher in the library along
    with the total number of items attributed to it.  The results are
    sorted in descending order of item count so the most prominent
    publishers surface first.  The rendered partial is swapped into the
    ``#master-stream`` container, replacing the previous view.
    """
    rows = (
        db.query(Item.publisher, func.count(Item.id).label("count"))
        .group_by(Item.publisher)
        .order_by(func.count(Item.id).desc())
        .all()
    )
    publishers = [{"name": name, "count": count} for name, count in rows]
    return templates.TemplateResponse(
        request,
        "partials/publisher_list.html",
        {"publishers": publishers},
    )


@router.get("/library/bundles")
def library_bundles(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    HTMX partial endpoint – returns every bundle in the library along
    with the total number of items contained in it.  Bundles with more
    items are listed first so the most content-rich bundles are at the
    top of the stream.  The rendered partial is swapped into the
    ``#master-stream`` container.
    """
    rows = (
        db.query(Bundle.id, Bundle.title, func.count(Item.id).label("count"))
        .join(Item, Item.bundle_id == Bundle.id)
        .group_by(Bundle.id)
        .order_by(func.count(Item.id).desc())
        .all()
    )
    bundles = [{"id": id, "name": name, "count": count} for id, name, count in rows]
    return templates.TemplateResponse(
        request,
        "partials/bundle_list.html",
        {"bundles": bundles},
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
