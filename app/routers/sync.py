"""
Sync router – session cookie library synchronization endpoints.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.dependencies import get_db
from humble_sync.services.client import sync_account_library

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("/library/sync/modal")
def sync_modal(request: Request):
    """
    HTMX partial endpoint – returns the sync modal form.
    The rendered partial is swapped into the #sync-modal-container.
    """
    return templates.TemplateResponse(
        request,
        "partials/sync_modal.html",
        {},
    )


@router.post("/library/sync")
async def sync_library(
    request: Request,
    session_cookie: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    HTMX partial endpoint – syncs the user's Humble Bundle library
    using the provided session cookie. Returns a status partial with
    item/bundle counts on success, or an error message on failure.
    """
    if not session_cookie or not session_cookie.strip():
        return templates.TemplateResponse(
            request,
            "partials/sync_status.html",
            {"error": "Session cookie is required."},
        )

    try:
        catalog = await sync_account_library(session_cookie.strip(), db_session=db)
        metadata = catalog.get("metadata", {})
        total_items = metadata.get("total_items", 0)
        # Count unique bundles from the items list
        bundles = set()
        for item in catalog.get("items", []):
            bundle_name = item.get("bundle")
            if bundle_name:
                bundles.add(bundle_name)
        total_bundles = len(bundles)

        return templates.TemplateResponse(
            request,
            "partials/sync_status.html",
            {
                "total_items": total_items,
                "total_bundles": total_bundles,
            },
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "partials/sync_status.html",
            {"error": str(exc)},
        )