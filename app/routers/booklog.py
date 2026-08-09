"""
Book Log router – CRUD endpoints for wishlist/reading items.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_db
from humble_sync.auth import fastapi_users
from humble_sync.db.models import User
from humble_sync.db.queries import (
    add_or_update_booklog_entry,
    delete_booklog_entry,
    get_booklog_entry_by_id,
    get_user_booklog,
)
from humble_sync.utils.text import normalize_title

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")

current_active_user = fastapi_users.current_user(active=True)


class BookLogCreateRequest(BaseModel):
    title: str
    status: str = "wishlist"
    item_id: str | None = None
    volume_info: str | None = None
    author_or_publisher: str | None = None
    notes: str | None = None
    target_price: float | None = None
    cover_url: str | None = None


class BookLogStatusRequest(BaseModel):
    status: str


@router.get("/booklog")
def booklog_page(request: Request, user: User = Depends(current_active_user)):
    """Serve the Book Log page."""
    return templates.TemplateResponse(request, "pages/booklog.html", {"user": user})


@router.get("/booklog/stream")
def booklog_stream(
    request: Request,
    user: User = Depends(current_active_user),
    db: Session = Depends(get_db),
):
    """HTMX partial – returns the list of booklog entries."""
    entries = get_user_booklog(db, user_id=user.id)
    return templates.TemplateResponse(
        request,
        "partials/booklog_list.html",
        {"entries": entries},
    )


@router.get("/booklog/entries/{entry_id}")
def booklog_entry_detail(
    request: Request,
    entry_id: int,
    user: User = Depends(current_active_user),
    db: Session = Depends(get_db),
):
    """HTMX partial – returns the inspector detail for a single entry."""
    entry = get_booklog_entry_by_id(db, entry_id, user_id=user.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Book log entry not found")
    return templates.TemplateResponse(
        request,
        "partials/booklog_inspector.html",
        {"entry": entry},
    )


@router.post("/booklog/entries")
def booklog_create(
    request: Request,
    body: BookLogCreateRequest,
    user: User = Depends(current_active_user),
    db: Session = Depends(get_db),
):
    """Create a new booklog entry."""
    norm_title = normalize_title(body.title)
    entry = add_or_update_booklog_entry(
        db,
        user_id=user.id,
        title=body.title,
        norm_title=norm_title,
        status=body.status,
        item_id=body.item_id,
        volume_info=body.volume_info,
        author_or_publisher=body.author_or_publisher,
        notes=body.notes,
        target_price=body.target_price,
        cover_url=body.cover_url,
    )
    db.commit()
    # Return updated list partial
    entries = get_user_booklog(db, user_id=user.id)
    return templates.TemplateResponse(
        request,
        "partials/booklog_list.html",
        {"entries": entries},
    )


@router.post("/booklog/entries/{entry_id}/status")
def booklog_update_status(
    request: Request,
    entry_id: int,
    body: BookLogStatusRequest,
    user: User = Depends(current_active_user),
    db: Session = Depends(get_db),
):
    """Update the status of an existing booklog entry."""
    entry = get_booklog_entry_by_id(db, entry_id, user_id=user.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Book log entry not found")
    entry.status = body.status
    entry.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    db.commit()
    db.refresh(entry)
    return templates.TemplateResponse(
        request,
        "partials/booklog_inspector.html",
        {"entry": entry},
    )


@router.delete("/booklog/entries/{entry_id}")
def booklog_delete(
    request: Request,
    entry_id: int,
    user: User = Depends(current_active_user),
    db: Session = Depends(get_db),
):
    """Delete a booklog entry."""
    deleted = delete_booklog_entry(db, entry_id, user_id=user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Book log entry not found")
    db.commit()
    # Return updated list partial
    entries = get_user_booklog(db, user_id=user.id)
    return templates.TemplateResponse(
        request,
        "partials/booklog_list.html",
        {"entries": entries},
    )