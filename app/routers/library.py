"""
Library router – serves the library search HTMX partial endpoint.
"""

from fastapi import APIRouter, Depends, Request
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
    db: Session = Depends(get_db),
):
    """
    HTMX partial endpoint – searches items by title (case-insensitive) and
    returns a fragment of HTML to be swapped into the search-results container.
    Designed for HTMX partial rendering.
    """
    items = (
        db.query(Item)
        .filter(Item.title.ilike(f"%{q}%"))
        .limit(50)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "partials/search_results.html",
        {"items": items},
    )