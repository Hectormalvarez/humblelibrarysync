"""
Library router – serves the library search HTMX partial endpoint.
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.dependencies import get_db
from models import Item

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
    return templates.TemplateResponse(
        request,
        "partials/search_results.html",
        {"items": items, "limit": limit, "offset": offset, "has_more": has_more},
    )
