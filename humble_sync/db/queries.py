"""Reusable query helpers for the Humble Library Sync catalog."""

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from humble_sync.db.models import Bundle, Item

_VALID_CATEGORY_SORTS = {"title_asc", "title_desc", "count_desc", "count_asc", "date_desc", "date_asc"}


def _normalize_category_sort(sort: str) -> str:
    """Normalize a sort value for the publishers/bundles endpoints."""
    if sort in _VALID_CATEGORY_SORTS:
        return sort
    return "title_asc"


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


def get_top_publishers_and_bundles(db: Session) -> dict:
    """Return the top 5 publishers and bundles by item count.

    Used by the library search endpoint to populate the category summary
    cards on the initial page load (empty search, first page).

    The returned dictionary contains:
    - ``publishers_summary``: list of dicts with ``name`` and ``count``.
    - ``bundles_summary``: list of dicts with ``name`` and ``count``.
    """
    publisher_rows = (
        db.query(Item.publisher, func.count(Item.id).label("count"))
        .group_by(Item.publisher)
        .order_by(func.count(Item.id).desc())
        .limit(5)
        .all()
    )
    bundle_rows = (
        db.query(Bundle.title, func.count(Item.id).label("count"))
        .join(Item, Item.bundle_id == Bundle.id)
        .group_by(Bundle.id)
        .order_by(func.count(Item.id).desc())
        .limit(5)
        .all()
    )

    return {
        "publishers_summary": [
            {"name": name, "count": count} for name, count in publisher_rows
        ],
        "bundles_summary": [
            {"name": name, "count": count} for name, count in bundle_rows
        ],
    }


def get_all_publishers(db: Session, q: str = "", sort: str = "title_asc") -> tuple[list[dict], str]:
    """Return all publishers with item counts, filtered and sorted.

    Parameters
    ----------
    db:
        SQLAlchemy session.
    q:
        Optional case-insensitive substring filter on publisher name.
    sort:
        Sort key. One of ``title_asc``, ``title_desc``, ``count_desc``,
        ``count_asc``. Falls back to ``title_asc`` for invalid values.

    Returns
    -------
    tuple[list[dict], str]
        A ``(publishers, active_sort)`` pair where each publisher dict
        contains ``"name"`` and ``"count"`` keys.
    """
    active_sort = _normalize_category_sort(sort)
    base_query = db.query(Item.publisher, func.count(Item.id).label("count"))
    if q:
        base_query = base_query.filter(Item.publisher.ilike(f"%{q}%"))

    if active_sort == "title_desc":
        rows = (
            base_query
            .group_by(Item.publisher)
            .order_by(Item.publisher.desc())
            .all()
        )
    elif active_sort == "count_desc":
        rows = (
            base_query
            .group_by(Item.publisher)
            .order_by(func.count(Item.id).desc())
            .all()
        )
    elif active_sort == "count_asc":
        rows = (
            base_query
            .group_by(Item.publisher)
            .order_by(func.count(Item.id).asc())
            .all()
        )
    else:  # title_asc
        rows = (
            base_query
            .group_by(Item.publisher)
            .order_by(Item.publisher.asc())
            .all()
        )

    publishers = [{"name": name, "count": count} for name, count in rows]
    return publishers, active_sort
