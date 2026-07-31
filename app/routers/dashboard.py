"""
Dashboard router – serves the main web GUI page with dynamic data.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.dependencies import get_db
from models import Item

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """
    Root endpoint – renders the main web GUI page with dynamic data.

    Uses `Depends(get_db)` to inject a request-scoped database session,
    allowing the endpoint to query the total count of Item records and
    pass it to the template for display.
    """
    item_count = db.query(func.count(Item.id)).scalar()
    return templates.TemplateResponse(
        request,
        "pages/home.html",
        {"item_count": item_count},
    )