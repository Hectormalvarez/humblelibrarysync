"""
Deal Logger module for Humble Library Sync.
Handles persistence of evaluated bundle data to the database and
deal expiration tracking / report formatting.
"""

from datetime import datetime, timezone
from typing import Any

from humble_sync.db.database import SessionLocal, init_db
from humble_sync.db.models import EvaluatedBundle


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


# ── Expiration Tracking ─────────────────────────────────────────────────


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


# ── Expired Deal Report Formatting ──────────────────────────────────────


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