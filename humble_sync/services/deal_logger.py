"""
Deal Logger module for Humble Library Sync.
Handles persistence of evaluated bundle data to the database.
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