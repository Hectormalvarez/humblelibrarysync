"""
Library router – serves the library search HTMX partial endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.dependencies import get_db
from humble_sync.db.queries import (
    get_all_bundles,
    get_all_publishers,
    get_item_by_id,
    get_library_metrics,
    get_sort_key,
    get_top_publishers_and_bundles,
    search_library_items,
)

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


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
    result = search_library_items(
        db,
        q=q,
        publisher=publisher,
        bundle_id=bundle_id,
        sort=sort,
        limit=limit,
        offset=offset,
    )

    # Add request-specific context for template rendering
    result["q"] = q
    result["limit"] = limit
    result["offset"] = offset

    # For pagination requests (offset > 0), return only the item rows partial
    # so HTMX can swap them in without re-rendering the filter bar or wrapper.
    if offset > 0:
        return templates.TemplateResponse(
            request,
            "partials/item_rows.html",
            result,
        )

    # Initial page load state (empty search, first page): aggregate top
    # publishers and bundles so the home page can show category stats.
    if q == "" and publisher is None and bundle_id is None:
        summaries = get_top_publishers_and_bundles(db)
        result["publishers_summary"] = summaries["publishers_summary"]
        result["bundles_summary"] = summaries["bundles_summary"]
    else:
        result["publishers_summary"] = []
        result["bundles_summary"] = []

    return templates.TemplateResponse(
        request,
        "partials/search_results.html",
        result,
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
    item = get_item_by_id(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    return templates.TemplateResponse(
        request,
        "partials/item_inspector.html",
        {"item": item},
    )
