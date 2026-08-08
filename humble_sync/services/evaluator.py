"""
Deal Evaluator module for Humble Library Sync.
Fetches live bundle data from Humble Bundle and evaluates overlap against owned library.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from humble_sync.db.database import SessionLocal, init_db
from humble_sync.services.duplicates import normalize_title
from humble_sync.db.models import EvaluatedBundle
from humble_sync.services.scraper import (
    _USER_AGENT,
    _fetch_landing_page_data,
    _parse_bundles_from_data,
    fetch_bundle_items,
)


# Default paths and TTL
_BUNDLES_DUMP_PATH = Path("raw_bundles_dump.json")
_CACHE_TTL_SECONDS = 3600  # 1 hour


def capture_active_bundles(
    dump_path: Path = _BUNDLES_DUMP_PATH,
    force: bool = False,
) -> list[dict[str, str]]:
    """
    Captures active bundles from Humble Bundle and writes raw data to disk.

    Fetches the landing page JSON and saves it to *dump_path* with a
    ``captured_at`` timestamp.  Returns the parsed bundle list.

    Args:
        dump_path: Path to write the raw dump file.
        force: If True, always fetch from network even if dump exists.

    Returns:
        List of dicts with keys: title, url, author, end_date, machine_name.

    Raises:
        RuntimeError: If network request fails or data cannot be parsed.
    """
    page_data = _fetch_landing_page_data()

    # Save raw data with timestamp
    dump = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "data": page_data,
    }
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dump_path, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2, ensure_ascii=False)

    return _parse_bundles_from_data(page_data)


def parse_bundles_dump(dump_path: Path = _BUNDLES_DUMP_PATH) -> list[dict[str, str]]:
    """
    Parses a previously captured bundles dump file into active bundle listings.

    Args:
        dump_path: Path to the raw bundles dump JSON file.

    Returns:
        List of dicts with keys: title, url, author, end_date, machine_name.

    Raises:
        FileNotFoundError: If the dump file does not exist.
        RuntimeError: If the dump file is malformed.
    """
    if not dump_path.exists():
        raise FileNotFoundError(f"Bundle dump not found: {dump_path}")

    with open(dump_path, "r", encoding="utf-8") as f:
        try:
            dump = json.load(f)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"[!] Corrupted bundle dump: {e}") from e

    page_data = dump.get("data", {})
    return _parse_bundles_from_data(page_data)


def _any_bundle_expired(bundles: list[dict[str, str]]) -> bool:
    """Returns True if any bundle's end_date is in the past (UTC)."""
    now = datetime.now(timezone.utc)
    for b in bundles:
        end_str = b.get("end_date", "")
        if not end_str:
            continue
        try:
            end_dt = datetime.fromisoformat(end_str)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            if end_dt < now:
                return True
        except (ValueError, TypeError):
            continue
    return False


def _dump_is_stale(dump_path: Path, ttl_seconds: int = _CACHE_TTL_SECONDS) -> bool:
    """Returns True if the dump file is older than *ttl_seconds*."""
    if not dump_path.exists():
        return True
    mtime = datetime.fromtimestamp(dump_path.stat().st_mtime, tz=timezone.utc)
    age = (datetime.now(timezone.utc) - mtime).total_seconds()
    return age > ttl_seconds


def load_active_bundles(
    dump_path: Path = _BUNDLES_DUMP_PATH,
    ttl_seconds: int = _CACHE_TTL_SECONDS,
) -> list[dict[str, str]]:
    """
    Loads active bundles, refreshing from network if the cached dump is stale.

    Refreshes when:
    - The dump file is missing.
    - The dump is older than *ttl_seconds*.
    - Any bundle in the cached dump has expired.

    Args:
        dump_path: Path to the raw bundles dump JSON file.
        ttl_seconds: Maximum age of the dump in seconds before refresh.

    Returns:
        List of dicts with keys: title, url, author, end_date, machine_name.

    Raises:
        RuntimeError: If network request fails and no cached data is available.
    """
    # Check if we need to refresh
    needs_refresh = (
        not dump_path.exists()
        or _dump_is_stale(dump_path, ttl_seconds)
    )

    if not needs_refresh:
        # Check if any cached bundles have expired
        try:
            cached = parse_bundles_dump(dump_path)
            if _any_bundle_expired(cached):
                needs_refresh = True
        except (FileNotFoundError, RuntimeError):
            needs_refresh = True

    if needs_refresh:
        try:
            return capture_active_bundles(dump_path, force=True)
        except RuntimeError as e:
            # If we have a stale cache, fall back to it
            if dump_path.exists():
                print(f"[!] Network error, using cached data: {e}")
                return parse_bundles_dump(dump_path)
            raise

    return parse_bundles_dump(dump_path)


def evaluate_deal(
    bundle_items: list[dict[str, Any]],
    library_items: list[dict[str, Any]],
    pricing: list[dict[str, Any]] | None = None,
    tier_item_map: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """
    Evaluates overlap between bundle items and owned library items.

    Uses normalized title matching to compare bundle contents against
    the user's existing library to determine deal value.

    Args:
        bundle_items: List of items from the bundle (with 'title' key).
        library_items: List of items from the user's library (with 'title' key).
        pricing: Optional list of pricing tiers from fetch_bundle_items().
        tier_item_map: Optional mapping of tier_id to item list.

    Returns:
        Dict with keys:
            - total_items: Total number of items in the bundle.
            - matched_count: Number of items already owned.
            - overlap_percentage: Percentage of bundle already owned (0-100).
            - matched_items: List of titles already owned.
            - new_items: List of titles not yet owned.
            - pricing: Pricing tier info (if provided).
            - tier_breakdown: Per-tier item lists with ownership status (if tier_item_map provided).
    """
    # Build a set of normalized library titles for fast lookup
    library_titles: set[str] = set()
    for item in library_items:
        raw_title = item.get("title", "").strip()
        if raw_title:
            library_titles.add(normalize_title(raw_title))

    total_items = len(bundle_items)
    matched_items: list[str] = []
    new_items: list[str] = []

    for item in bundle_items:
        raw_title = item.get("title", "").strip()
        if not raw_title:
            continue

        norm_title = normalize_title(raw_title)
        if norm_title in library_titles:
            matched_items.append(raw_title)
        else:
            new_items.append(raw_title)

    matched_count = len(matched_items)
    overlap_percentage = (matched_count / total_items * 100) if total_items > 0 else 0.0

    result: dict[str, Any] = {
        "total_items": total_items,
        "matched_count": matched_count,
        "overlap_percentage": round(overlap_percentage, 1),
        "matched_items": sorted(matched_items),
        "new_items": sorted(new_items),
    }
    if pricing is not None:
        result["pricing"] = pricing

    if tier_item_map is not None:
        tier_breakdown: list[dict[str, Any]] = []
        for tier in (pricing or []):
            tid = tier["tier_id"]
            tier_items = tier_item_map.get(tid, [])
            owned: list[str] = []
            unowned: list[str] = []
            for item in tier_items:
                raw_title = item.get("title", "").strip()
                if not raw_title:
                    continue
                norm_title = normalize_title(raw_title)
                if norm_title in library_titles:
                    owned.append(raw_title)
                else:
                    unowned.append(raw_title)
            tier_breakdown.append({
                "tier_id": tid,
                "amount": tier["amount"],
                "currency": tier["currency"],
                "is_bta": tier["is_bta"],
                "header": tier["header"],
                "owned": sorted(owned),
                "unowned": sorted(unowned),
            })
        result["tier_breakdown"] = tier_breakdown

    return result


def format_deal_report(bundle_title: str, eval_data: dict[str, Any]) -> str:
    """
    Formats deal evaluation data into a clean terminal report.

    Args:
        bundle_title: Display name of the bundle being evaluated.
        eval_data: Output from evaluate_deal() containing overlap statistics.

    Returns:
        Formatted string suitable for terminal display.
    """
    total_items = eval_data.get("total_items", 0)
    matched_count = eval_data.get("matched_count", 0)
    overlap_pct = eval_data.get("overlap_percentage", 0.0)
    matched_items = eval_data.get("matched_items", [])
    new_items = eval_data.get("new_items", [])
    pricing = eval_data.get("pricing", [])

    lines = [
        "=" * 60,
        "DEAL EVALUATION REPORT",
        "=" * 60,
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Bundle:      {bundle_title}",
        "-" * 60,
        "OVERVIEW",
        f"  Total items in bundle:  {total_items}",
        f"  Items already owned:    {matched_count}",
        f"  New items available:    {len(new_items)}",
        f"  Overlap percentage:     {overlap_pct}%",
        "-" * 60,
    ]

    tier_breakdown = eval_data.get("tier_breakdown", [])

    if tier_breakdown:
        lines.append("ITEMS BY TIER")
        lines.append("-" * 60)
        for tier in tier_breakdown:
            price_str = f"${tier['amount']:.2f} {tier['currency']}"
            bta_str = " (BTA)" if tier['is_bta'] else ""
            header = tier.get("header", "")
            lines.append(f"  {price_str}{bta_str}")
            if header:
                lines.append(f"    {header}")
            for title in tier.get("owned", []):
                lines.append(f"    [x] {title}")
            for title in tier.get("unowned", []):
                lines.append(f"    [+] {title}")
            lines.append("")
    else:
        if pricing:
            lines.append("PRICING TIERS")
            lines.append("-" * 60)
            for tier in pricing:
                price_str = f"${tier['amount']:.2f} {tier['currency']}"
                bta_str = " (BTA)" if tier['is_bta'] else ""
                header = tier.get("header", "")
                lines.append(f"  {price_str}{bta_str}")
                if header:
                    lines.append(f"    {header}")
            lines.append("")

        if matched_items:
            lines.append("ALREADY OWNED")
            lines.append("-" * 60)
            for title in matched_items:
                lines.append(f"  [x] {title}")
            lines.append("")

        if new_items:
            lines.append("NEW ITEMS (NOT YET OWNED)")
            lines.append("-" * 60)
            for title in new_items:
                lines.append(f"  [+] {title}")
            lines.append("")

        if not matched_items and not new_items:
            lines.append("No items found in this bundle.")

    lines.append("=" * 60)
    return "\n".join(lines)


# ── Evaluated bundles log (expired deals tracking) ──────────────────────


def load_evaluated_bundles_log() -> list[dict[str, Any]]:
    """
    Loads all evaluated bundle records from the database.

    Returns:
        List of dicts with keys: bundle_name, url, machine_name,
        end_date, evaluated_at, expired_at, evaluation.
    """
    init_db()
    db = SessionLocal()
    try:
        records = db.query(EvaluatedBundle).all()
        return [
            {
                "bundle_name": r.bundle_name,
                "url": r.url,
                "machine_name": r.machine_name,
                "end_date": r.end_date,
                "evaluated_at": r.evaluated_at,
                "expired_at": r.expired_at,
                "evaluation": r.evaluation,
            }
            for r in records
        ]
    finally:
        db.close()


def log_evaluated_bundle(
    bundle_name: str,
    bundle_url: str,
    machine_name: str,
    end_date: str,
    eval_data: dict[str, Any],
) -> None:
    """
    Records or updates a bundle evaluation in the database.

    If an entry with the same *bundle_url* already exists, its fields
    are updated (preserving any existing ``expired_at``).
    Otherwise a new ``EvaluatedBundle`` record is inserted.
    """
    now_str = datetime.now(timezone.utc).isoformat()

    # Strip large / non-serialisable fields from eval_data for the log.
    log_eval = {
        "total_items": eval_data.get("total_items"),
        "matched_count": eval_data.get("matched_count"),
        "overlap_percentage": eval_data.get("overlap_percentage"),
        "matched_items": eval_data.get("matched_items", []),
        "new_items": eval_data.get("new_items", []),
        "pricing": eval_data.get("pricing"),
    }

    init_db()
    db = SessionLocal()
    try:
        existing = db.query(EvaluatedBundle).filter(
            EvaluatedBundle.url == bundle_url
        ).first()

        if existing:
            existing.bundle_name = bundle_name
            existing.machine_name = machine_name
            existing.end_date = end_date
            existing.evaluated_at = now_str
            existing.evaluation = log_eval
        else:
            record = EvaluatedBundle(
                bundle_name=bundle_name,
                url=bundle_url,
                machine_name=machine_name,
                end_date=end_date,
                evaluated_at=now_str,
                expired_at=None,
                evaluation=log_eval,
            )
            db.add(record)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def mark_expired_entries() -> None:
    """
    Scans the database for unexpired entries whose ``end_date``
    is in the past and sets their ``expired_at`` to the current UTC time.
    """
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    init_db()
    db = SessionLocal()
    try:
        unexpired = db.query(EvaluatedBundle).filter(
            EvaluatedBundle.expired_at.is_(None)
        ).all()
        for record in unexpired:
            end_str = record.end_date
            if not end_str:
                continue
            try:
                end_dt = datetime.fromisoformat(end_str)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                if end_dt < now:
                    record.expired_at = now_str
            except (ValueError, TypeError):
                continue
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_expired_entries(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Returns only entries that have been marked as expired."""
    return [e for e in entries if e.get("expired_at") is not None]


# ── Bundle category grouping ────────────────────────────────────────────

_CATEGORY_GROUPS = {
    "books": "📚 Books",
    "games": "🎮 Games",
    "software": "💻 Software",
}


def _categorise_bundle_url(url: str) -> str:
    """Return the category key (books/games/software) from a bundle URL."""
    if "/books/" in url:
        return "books"
    if "/games/" in url:
        return "games"
    if "/software/" in url:
        return "software"
    return "books"


def group_bundles_by_category(bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Group bundles into books, games, and software categories.

    Args:
        bundles: List of bundle dicts (each expected to have a 'url' key).

    Returns:
        List of category dicts structured as:
        [{"key": k, "label": label, "bundles": [...]}, ...]
    """
    grouped: dict[str, list[dict]] = {"books": [], "games": [], "software": []}
    for b in bundles:
        cat = _categorise_bundle_url(b.get("url", ""))
        grouped.setdefault(cat, []).append(b)

    return [
        {"key": k, "label": _CATEGORY_GROUPS.get(k, k), "bundles": grouped.get(k, [])}
        for k in ("books", "games", "software")
    ]


def get_unexpired_entries(
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Returns entries that have not yet expired."""
    now = datetime.now(timezone.utc)
    result: list[dict[str, Any]] = []
    for e in entries:
        if e.get("expired_at") is not None:
            continue
        end_str = e.get("end_date", "")
        if not end_str:
            continue
        try:
            end_dt = datetime.fromisoformat(end_str)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            if end_dt >= now:
                result.append(e)
        except (ValueError, TypeError):
            continue
    return result


def format_expired_reading_list(entries: list[dict[str, Any]]) -> str:
    """
    Builds a deduplicated, sorted reading list of all *new* (unowned)
    titles from expired bundle evaluations.

    Args:
        entries: List of expired log entries (from get_expired_entries()).

    Returns:
        Formatted string ready for terminal display.
    """
    seen: set[str] = set()
    titles: list[str] = []

    for entry in entries:
        eval_data = entry.get("evaluation", {})
        new_items = eval_data.get("new_items", [])
        for title in new_items:
            norm = title.strip().lower()
            if norm not in seen:
                seen.add(norm)
                titles.append(title.strip())

    titles.sort(key=str.lower)

    lines = [
        "=" * 60,
        "EXPIRED DEAL READING LIST",
        "=" * 60,
    ]
    if not titles:
        lines.append("  No new items from expired deals recorded.")
    else:
        lines.append(f"  Total unique titles: {len(titles)}")
        lines.append("-" * 60)
        for title in titles:
            lines.append(f"  {title}")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_expired_deals_report(entries: list[dict[str, Any]]) -> str:
    """
    Prints a summary report of expired evaluated bundles.

    Args:
        entries: List of expired log entries.

    Returns:
        Formatted string suitable for terminal display.
    """
    lines = [
        "=" * 60,
        "EXPIRED EVALUATED DEALS",
        "=" * 60,
    ]
    if not entries:
        lines.append("  No expired evaluated deals recorded.")
        lines.append("=" * 60)
        return "\n".join(lines)

    lines.append(f"  Total expired bundles: {len(entries)}")
    lines.append("")

    for entry in entries:
        bundle_name = entry.get("bundle_name", "Unknown")
        end_date = entry.get("end_date", "?")[:10]
        expired_at = entry.get("expired_at", "?")[:10]
        eval_data = entry.get("evaluation", {})
        new_count = len(eval_data.get("new_items", []))
        total = eval_data.get("total_items", 0)
        overlap = eval_data.get("overlap_percentage", 0.0)

        lines.append(f"  {bundle_name}")
        lines.append(f"    Ended: {end_date}  |  Expired: {expired_at}")
        lines.append(f"    {new_count} new / {total} total  |  {overlap}% overlap")

    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    # Quick test: capture and display active bundles
    print("[*] Capturing active bundles...")
    try:
        bundles = capture_active_bundles()
        print(f"[*] Found {len(bundles)} active bundles:")
        for b in bundles[:5]:
            print(f"  - {b['title']} (ends {b['end_date'][:10]})")
    except RuntimeError as e:
        print(e)