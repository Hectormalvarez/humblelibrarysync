"""
Library status module for Humble Library Sync.
Analyzes catalog health, sync age, and CDN download URL expiration states.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from database import SessionLocal
from models import Bundle, Item


def check_status(library_file: str | Path | None = None) -> dict[str, Any]:
    """
    Analyzes catalog health, sync age, and CDN download link expiration times
    by querying the SQLite database directly.

    Args:
        library_file: Ignored (kept for backward compatibility).

    Returns:
        Dictionary of health metrics matching the previous output contract.
    """
    db = SessionLocal()
    try:
        total_bundles = db.query(Bundle).count()
        total_items = db.query(Item).count()

        if total_items == 0:
            return {
                "status": "MISSING",
                "file_path": "sqlite:///./humble_library.db",
            }

        now = datetime.now(timezone.utc)

        # Latest captured_at across all bundles
        latest_bundle = db.query(Bundle).order_by(Bundle.captured_at.desc()).first()
        captured_at_raw = latest_bundle.captured_at if latest_bundle else None

        sync_age_str = "Unknown"
        if captured_at_raw:
            try:
                captured_dt = datetime.fromisoformat(captured_at_raw)
                delta = now - captured_dt
                days = delta.days
                hours = delta.seconds // 3600
                sync_age_str = f"{days}d {hours}h ago ({captured_dt.strftime('%Y-%m-%d')})"
            except ValueError:
                pass

        # Count key-only items
        key_only_items = db.query(Item).filter(
            Item.item_type == "redemption_key"
        ).count()

        # Iterate over all download items to compute link health
        active_links = 0
        expired_links = 0
        earliest_expiration: datetime | None = None

        download_items = db.query(Item).filter(
            Item.item_type != "redemption_key"
        ).all()

        for item in download_items:
            downloads = item.downloads or {}
            for fmt_data in downloads.values():
                expires_at_raw = fmt_data.get("url_expires_at") if isinstance(fmt_data, dict) else None
                if not expires_at_raw:
                    continue

                try:
                    exp_dt = datetime.fromisoformat(expires_at_raw)
                    if exp_dt > now:
                        active_links += 1
                        if earliest_expiration is None or exp_dt < earliest_expiration:
                            earliest_expiration = exp_dt
                    else:
                        expired_links += 1
                except ValueError:
                    continue

        total_download_links = active_links + expired_links

        if total_download_links == 0:
            health_status = "NO_DOWNLOADS"
        elif active_links > 0:
            health_status = "ACTIVE"
        else:
            health_status = "EXPIRED"

        time_remaining_str = "None"
        if earliest_expiration and health_status == "ACTIVE":
            remaining_seconds = int((earliest_expiration - now).total_seconds())
            hours = remaining_seconds // 3600
            minutes = (remaining_seconds % 3600) // 60
            time_remaining_str = f"{hours}h {minutes}m"

        return {
            "status": health_status,
            "file_path": "sqlite:///./humble_library.db",
            "total_items": total_items,
            "total_bundles": total_bundles,
            "key_only_items": key_only_items,
            "sync_age": sync_age_str,
            "active_links": active_links,
            "expired_links": expired_links,
            "link_time_remaining": time_remaining_str,
        }
    finally:
        db.close()


def format_status_report(data: dict[str, Any]) -> str:
    """Formats raw status health metrics into a printable terminal report."""
    status_code = data.get("status", "UNKNOWN")
    lines = [
        "=" * 50,
        "HUMBLE LIBRARY STATUS",
        "=" * 50,
        f"Catalog File:        {data.get('file_path', 'Unknown')}",
    ]

    if status_code == "MISSING":
        lines.append("Status:              MISSING (Catalog file not found)")
        lines.append("-" * 50)
        lines.append("Action Needed:       Run 'parse' or 'capture' to initialize.")
        lines.append("=" * 50)
        return "\n".join(lines)

    if status_code == "CORRUPTED":
        lines.append("Status:              CORRUPTED (Unable to parse JSON)")
        lines.append("-" * 50)
        lines.append("Action Needed:       Run 'parse' to regenerate library file.")
        lines.append("=" * 50)
        return "\n".join(lines)

    lines.extend([
        f"Total Items:         {data.get('total_items', 0)} ({data.get('key_only_items', 0)} redemption keys)",
        f"Bundles Represented: {data.get('total_bundles', 0)}",
        f"Last Synced:         {data.get('sync_age', 'Unknown')}",
        "-" * 50,
        "LINK HEALTH",
        f"Active CDN Links:    {data.get('active_links', 0)}",
        f"Expired CDN Links:   {data.get('expired_links', 0)}",
    ])

    if status_code == "ACTIVE":
        lines.append(f"Overall Health:      ACTIVE (Valid for next {data.get('link_time_remaining')})")
    elif status_code == "EXPIRED":
        lines.append("Overall Health:      EXPIRED (All download URLs expired)")
        lines.append("Action Needed:       Run 'capture' when you need fresh download links.")
    else:
        lines.append("Overall Health:      NO LINKS FOUND")

    lines.append("=" * 50)
    return "\n".join(lines)


if __name__ == "__main__":
    status_data = check_status()
    print(format_status_report(status_data))