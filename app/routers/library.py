"""
Library router – serves the library search HTMX partial endpoint.
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_db
from models import Bundle, Item

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("/library/search")
def library_search(
    request: Request,
    q: str = "",
    limit: int = Query(30, ge=1),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    HTMX partial endpoint – searches items by title (case-insensitive) and
    returns a fragment of HTML to be swapped into the search-results container.
    Designed for HTMX partial rendering.
    """
    base_query = db.query(Item).filter(Item.title.ilike(f"%{q}%"))
    total_count = base_query.count()
    items = base_query.offset(offset).limit(limit).all()
    has_more = (offset + len(items)) < total_count

    # Initial page load state (empty search, first page): aggregate top
    # publishers and bundles so the home page can show category stats.
    if q == "" and offset == 0:
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
        db.query(Bundle.title, func.count(Item.id).label("count"))
        .join(Item, Item.bundle_id == Bundle.id)
        .group_by(Bundle.id)
        .order_by(func.count(Item.id).desc())
        .all()
    )
    bundles = [{"name": name, "count": count} for name, count in rows]
    return templates.TemplateResponse(
        request,
        "partials/bundle_list.html",
        {"bundles": bundles},
    )
