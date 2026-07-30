"""
Library status module for Humble Library Sync.
Analyzes catalog health, sync age, and CDN download URL expiration states.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def check_status(library_file: str | Path = "my_library.json") -> dict[str, Any]:
    """
    Analyzes catalog existence, sync age, and CDN download link expiration times.
    Returns a dictionary of health metrics.
    """
    path = Path(library_file)
    if not path.exists():
        return {
            "status": "MISSING",
            "file_path": str(path),
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {
            "status": "CORRUPTED",
            "file_path": str(path),
        }

    metadata = catalog.get("metadata", {})
    items = catalog.get("items", [])

    now = datetime.now(timezone.utc)
    captured_at_raw = metadata.get("dump_captured_at") or metadata.get("generated_at")

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

    active_links = 0
    expired_links = 0
    key_only_items = 0
    earliest_expiration: datetime | None = None
    bundles = set()

    for item in items:
        bundle_name = item.get("bundle")
        if bundle_name:
            bundles.add(bundle_name)

        if item.get("type") == "redemption_key":
            key_only_items += 1
            continue

        downloads = item.get("downloads", {})
        for fmt_data in downloads.values():
            expires_at_raw = fmt_data.get("url_expires_at")
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
        "file_path": str(path),
        "total_items": len(items),
        "total_bundles": len(bundles),
        "key_only_items": key_only_items,
        "sync_age": sync_age_str,
        "active_links": active_links,
        "expired_links": expired_links,
        "link_time_remaining": time_remaining_str,
    }


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