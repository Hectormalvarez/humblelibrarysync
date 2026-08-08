"""Reusable query helpers for the Humble Library Sync catalog."""

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from humble_sync.db.models import Bundle, Item


def get_library_metrics(db: Session) -> dict:
    """Return aggregate library metrics for the overview panel.

    The returned dictionary contains:
    - ``total_items``: total number of items in the catalog.
    - ``total_publishers``: number of distinct publishers.
    - ``total_bundles``: total number of bundles.
    - ``format_breakdown``: list of dicts with ``format`` and ``count``
      keys, sorted by descending count then format name.
    """
    total_items = db.query(func.count(Item.id)).scalar() or 0
    total_publishers = db.query(func.count(distinct(Item.publisher))).scalar() or 0
    total_bundles = db.query(func.count(Bundle.id)).scalar() or 0

    # Count items per format by scanning the available_formats JSON arrays
    # in Python. This keeps the query portable across SQL backends (SQLite
    # stores JSON columns as text, so backend-specific JSON functions would
    # otherwise be needed).
    format_counts: dict[str, int] = {}
    for (formats,) in db.query(Item.available_formats).all():
        for fmt in formats or []:
            format_counts[fmt] = format_counts.get(fmt, 0) + 1

    format_breakdown = [
        {"format": fmt, "count": format_counts[fmt]}
        for fmt in sorted(
            format_counts, key=lambda f: (-format_counts[f], f)
        )
    ]

    return {
        "total_items": total_items,
        "total_publishers": total_publishers,
        "total_bundles": total_bundles,
        "format_breakdown": format_breakdown,
    }