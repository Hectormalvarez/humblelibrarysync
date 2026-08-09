"""Reusable query helpers for the Humble Library Sync catalog."""

import re
import uuid

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from humble_sync.db.models import Bundle, EvaluatedBundle, Item

_VALID_CATEGORY_SORTS = {"title_asc", "title_desc", "count_desc", "count_asc", "date_desc", "date_asc"}
_VALID_SEARCH_SORTS = {"title_asc", "title_desc", "publisher_asc"}

# Regex to strip common Humble Bundle title prefixes for smart A-Z sorting.
# Matches (case-insensitive):
#   - "Humble <sub-bundle> Bundle: " (e.g. "Humble Book Bundle: ")
#   - "Humble " (e.g. "Humble Foo")
#   - "The " (e.g. "The Foo")
_PREFIX_RE = re.compile(
    r"^(?:humble\s+(?:[a-z0-9-]+\s+)?bundle:\s*|humble\s+|the\s+)",
    re.IGNORECASE,
)


def get_total_item_count(db: Session, user_id: uuid.UUID | str | None = None) -> int:
    """Return the total number of items in the catalog.

    Parameters
    ----------
    db:
        SQLAlchemy session.
    user_id:
        Optional user UUID to scope results to a single user.
    """
    query = db.query(func.count(Item.id))
    if user_id is not None:
        query = query.filter(Item.user_id == user_id)
    return query.scalar() or 0


def get_sort_key(title: str) -> str:
    """Return a lowercase, prefix-stripped title suitable for smart A-Z sorting."""
    return _PREFIX_RE.sub("", title).strip().lower()


def _normalize_search_sort(sort: str) -> str:
    """Normalize a sort value for the search endpoint.

    Falls back to ``title_asc`` when the value is invalid or belongs to a
    different view (e.g. ``count_desc`` from a category tab).
    """
    if sort in _VALID_SEARCH_SORTS:
        return sort
    return "title_asc"


def _normalize_category_sort(sort: str) -> str:
    """Normalize a sort value for the publishers/bundles endpoints."""
    if sort in _VALID_CATEGORY_SORTS:
        return sort
    return "title_asc"


def get_library_metrics(db: Session, user_id: uuid.UUID | str | None = None) -> dict:
    """Return aggregate library metrics for the overview panel.

    The returned dictionary contains:
    - ``total_items``: total number of items in the catalog.
    - ``total_publishers``: number of distinct publishers.
    - ``total_bundles``: total number of bundles.
    - ``format_breakdown``: list of dicts with ``format`` and ``count``
      keys, sorted by descending count then format name.

    Parameters
    ----------
    db:
        SQLAlchemy session.
    user_id:
        Optional user UUID to scope results to a single user.
    """
    item_query = db.query(Item)
    bundle_query = db.query(Bundle)
    if user_id is not None:
        item_query = item_query.filter(Item.user_id == user_id)
        bundle_query = bundle_query.filter(Bundle.user_id == user_id)

    total_items = item_query.count() or 0
    total_publishers = item_query.with_entities(func.count(distinct(Item.publisher))).scalar() or 0
    total_bundles = bundle_query.count() or 0

    # Count items per format by scanning the available_formats JSON arrays
    # in Python. This keeps the query portable across SQL backends (SQLite
    # stores JSON columns as text, so backend-specific JSON functions would
    # otherwise be needed).
    format_counts: dict[str, int] = {}
    for (formats,) in item_query.with_entities(Item.available_formats).all():
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


def get_library_item_titles(db: Session, user_id: uuid.UUID | str | None = None) -> list[dict[str, str]]:
    """Return a list of all library item titles.

    Parameters
    ----------
    db:
        SQLAlchemy session.
    user_id:
        Optional user UUID to scope results to a single user.

    Returns
    -------
    list[dict[str, str]]
        A list of dicts, each containing a single ``"title"`` key.
    """
    query = db.query(Item.title)
    if user_id is not None:
        query = query.filter(Item.user_id == user_id)
    rows = query.all()
    return [{"title": title} for (title,) in rows]


def get_top_publishers_and_bundles(db: Session, user_id: uuid.UUID | str | None = None) -> dict:
    """Return the top 5 publishers and bundles by item count.

    Used by the library search endpoint to populate the category summary
    cards on the initial page load (empty search, first page).

    The returned dictionary contains:
    - ``publishers_summary``: list of dicts with ``name`` and ``count``.
    - ``bundles_summary``: list of dicts with ``name`` and ``count``.

    Parameters
    ----------
    db:
        SQLAlchemy session.
    user_id:
        Optional user UUID to scope results to a single user.
    """
    pub_query = (
        db.query(Item.publisher, func.count(Item.id).label("count"))
    )
    bundle_query = (
        db.query(Bundle.title, func.count(Item.id).label("count"))
        .join(Item, Item.bundle_id == Bundle.id)
    )
    if user_id is not None:
        pub_query = pub_query.filter(Item.user_id == user_id)
        bundle_query = bundle_query.filter(Item.user_id == user_id)

    publisher_rows = (
        pub_query
        .group_by(Item.publisher)
        .order_by(func.count(Item.id).desc())
        .limit(5)
        .all()
    )
    bundle_rows = (
        bundle_query
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


def get_all_publishers(
    db: Session,
    q: str = "",
    sort: str = "title_asc",
    user_id: uuid.UUID | str | None = None,
) -> tuple[list[dict], str]:
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
    user_id:
        Optional user UUID to scope results to a single user.

    Returns
    -------
    tuple[list[dict], str]
        A ``(publishers, active_sort)`` pair where each publisher dict
        contains ``"name"`` and ``"count"`` keys.
    """
    active_sort = _normalize_category_sort(sort)
    base_query = db.query(Item.publisher, func.count(Item.id).label("count"))
    if user_id is not None:
        base_query = base_query.filter(Item.user_id == user_id)
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


def get_all_bundles(
    db: Session,
    q: str = "",
    sort: str = "title_asc",
    user_id: uuid.UUID | str | None = None,
) -> tuple[list[dict], str]:
    """Return all bundles with item counts, filtered and sorted.

    Parameters
    ----------
    db:
        SQLAlchemy session.
    q:
        Optional case-insensitive substring filter on bundle title.
    sort:
        Sort key. One of ``title_asc``, ``title_desc``, ``count_asc``,
        ``count_desc``, ``date_asc``, ``date_desc``. Falls back to
        ``title_asc`` for invalid values.
    user_id:
        Optional user UUID to scope results to a single user.

    Returns
    -------
    tuple[list[dict], str]
        A ``(bundles, active_sort)`` pair where each bundle dict contains
        ``"id"``, ``"name"``, ``"purchase_date"``, and ``"count"`` keys.
    """
    active_sort = _normalize_category_sort(sort)
    base_query = (
        db.query(Bundle.id, Bundle.title, Bundle.purchase_date, func.count(Item.id).label("count"))
        .join(Item, Item.bundle_id == Bundle.id)
    )
    if user_id is not None:
        base_query = base_query.filter(Bundle.user_id == user_id)
    if q:
        base_query = base_query.filter(Bundle.title.ilike(f"%{q}%"))

    if active_sort in ("title_asc", "title_desc"):
        # For title sorts, fetch all rows then sort in Python using the
        # prefix-stripping helper so "Humble Book Bundle: Foo" sorts as "foo".
        rows = (
            base_query
            .group_by(Bundle.id)
            .all()
        )
        bundles_raw = [
            {"id": id, "name": name, "purchase_date": purchase_date, "count": count}
            for id, name, purchase_date, count in rows
        ]
        reverse = active_sort == "title_desc"
        bundles_raw.sort(key=lambda b: get_sort_key(b["name"]), reverse=reverse)
        bundles = bundles_raw
    elif active_sort == "count_asc":
        rows = (
            base_query
            .group_by(Bundle.id)
            .order_by(func.count(Item.id).asc())
            .all()
        )
        bundles = [{"id": id, "name": name, "purchase_date": purchase_date, "count": count} for id, name, purchase_date, count in rows]
    elif active_sort == "date_desc":
        rows = (
            base_query
            .group_by(Bundle.id)
            .order_by(Bundle.purchase_date.desc().nulls_last())
            .all()
        )
        bundles = [{"id": id, "name": name, "purchase_date": purchase_date, "count": count} for id, name, purchase_date, count in rows]
    elif active_sort == "date_asc":
        rows = (
            base_query
            .group_by(Bundle.id)
            .order_by(Bundle.purchase_date.asc().nulls_last())
            .all()
        )
        bundles = [{"id": id, "name": name, "purchase_date": purchase_date, "count": count} for id, name, purchase_date, count in rows]
    else:  # count_desc (default for category views)
        rows = (
            base_query
            .group_by(Bundle.id)
            .order_by(func.count(Item.id).desc())
            .all()
        )
        bundles = [{"id": id, "name": name, "purchase_date": purchase_date, "count": count} for id, name, purchase_date, count in rows]

    return bundles, active_sort


def get_evaluated_bundle_by_url(
    db: Session,
    url: str,
    user_id: uuid.UUID | str | None = None,
) -> EvaluatedBundle | None:
    """Return an EvaluatedBundle matching the given URL, or ``None`` if not found.

    Parameters
    ----------
    db:
        SQLAlchemy session.
    url:
        The bundle URL to look up.
    user_id:
        Optional user UUID to scope results to a single user.

    Returns
    -------
    EvaluatedBundle | None
        The matching ``EvaluatedBundle`` ORM object, or ``None`` if no row
        matches the given URL.
    """
    query = db.query(EvaluatedBundle).filter(EvaluatedBundle.url == url)
    if user_id is not None:
        query = query.filter(EvaluatedBundle.user_id == user_id)
    return query.first()


def get_item_by_id(
    db: Session,
    item_id: int,
    user_id: uuid.UUID | str | None = None,
) -> Item | None:
    """Return a single item joined with its bundle, or ``None`` if not found.

    Parameters
    ----------
    db:
        SQLAlchemy session.
    item_id:
        Primary key of the item to fetch.
    user_id:
        Optional user UUID to scope results to a single user.

    Returns
    -------
    Item | None
        The ``Item`` ORM object with its parent ``Bundle`` eagerly loaded,
        or ``None`` if no row matches the given id.
    """
    query = (
        db.query(Item)
        .join(Bundle, Item.bundle_id == Bundle.id)
        .filter(Item.id == item_id)
    )
    if user_id is not None:
        query = query.filter(Item.user_id == user_id)
    return query.first()


def search_library_items(
    db: Session,
    q: str = "",
    publisher: str | None = None,
    bundle_id: int | None = None,
    sort: str = "title_asc",
    limit: int = 30,
    offset: int = 0,
    user_id: uuid.UUID | str | None = None,
) -> dict:
    """Search, filter, sort, and paginate library items.

    Parameters
    ----------
    db:
        SQLAlchemy session.
    q:
        Optional case-insensitive substring filter on item title.
    publisher:
        Optional exact-match filter on publisher name.
    bundle_id:
        Optional exact-match filter on bundle id.
    sort:
        Sort key. One of ``title_asc``, ``title_desc``, ``publisher_asc``.
        Falls back to ``title_asc`` for invalid values.
    limit:
        Maximum number of items to return.
    offset:
        Number of items to skip (for pagination).
    user_id:
        Optional user UUID to scope results to a single user.

    Returns
    -------
    dict
        A dictionary containing:
        - ``items``: list of ``Item`` ORM objects for the current page.
        - ``total_count``: total number of items matching the filters.
        - ``has_more``: whether more items exist beyond the current page.
        - ``active_publisher``: the publisher filter value (or ``None``).
        - ``active_bundle``: the ``Bundle`` ORM object if ``bundle_id`` was
          provided, otherwise ``None``.
        - ``active_sort``: the resolved sort key.
    """
    active_sort = _normalize_search_sort(sort)
    base_query = db.query(Item)

    # Apply user scope
    if user_id is not None:
        base_query = base_query.filter(Item.user_id == user_id)

    # Apply strict equality filters when provided
    if publisher is not None:
        base_query = base_query.filter(Item.publisher == publisher)
    if bundle_id is not None:
        base_query = base_query.filter(Item.bundle_id == bundle_id)
    if q:
        base_query = base_query.filter(Item.title.ilike(f"%{q}%"))

    # Apply sort ordering
    if active_sort == "title_desc":
        base_query = base_query.order_by(Item.title.desc())
    elif active_sort == "publisher_asc":
        base_query = base_query.order_by(Item.publisher.asc(), Item.title.asc())
    else:
        base_query = base_query.order_by(Item.title.asc())

    total_count = base_query.count()
    items = base_query.offset(offset).limit(limit).all()
    has_more = (offset + len(items)) < total_count

    # Resolve active filter objects for the filter pill header
    active_publisher = publisher
    active_bundle = None
    if bundle_id is not None:
        active_bundle = db.query(Bundle).filter(Bundle.id == bundle_id).first()

    return {
        "items": items,
        "total_count": total_count,
        "has_more": has_more,
        "active_publisher": active_publisher,
        "active_bundle": active_bundle,
        "active_sort": active_sort,
    }