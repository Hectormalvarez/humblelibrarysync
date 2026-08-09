"""
Export router – provides download manifest export functionality.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.dependencies import get_db
from humble_sync.auth import fastapi_users
from humble_sync.db.models import User
from humble_sync.db.queries import get_user_booklog

router = APIRouter()

current_active_user = fastapi_users.current_user(active=True)


@router.post("/export/manifest/download")
def export_manifest_download(
    request: Request,
    user: User = Depends(current_active_user),
    db: Session = Depends(get_db),
):
    """Return a plain-text manifest of the user's book log entries.

    The response is served as a ``text/plain`` attachment file named
    ``booklog_manifest.txt``.
    """
    entries = get_user_booklog(db, user_id=user.id)

    lines: list[str] = [
        "# Book Log Manifest",
        f"# User: {user.email}",
        f"# Total entries: {len(entries)}",
        "",
    ]

    for entry in entries:
        line_parts = [entry.title]
        if entry.status:
            line_parts.append(f"[{entry.status}]")
        if entry.author_or_publisher:
            line_parts.append(f"- {entry.author_or_publisher}")
        if entry.volume_info:
            line_parts.append(f"({entry.volume_info})")
        if entry.target_price is not None:
            line_parts.append(f"${entry.target_price:.2f}")
        if entry.notes:
            line_parts.append(f'"{entry.notes}"')
        lines.append(" ".join(line_parts))

    content = "\n".join(lines) + "\n"

    return Response(
        content=content,
        media_type="text/plain",
        headers={
            "Content-Disposition": 'attachment; filename="booklog_manifest.txt"'
        },
    )