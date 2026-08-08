"""
Bundle cache validation helpers for Humble Library Sync.
Provides staleness and expiry checks for cached bundle data,
plus functions to capture, parse, and load active bundles.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from humble_sync.services.scraper import (
    _fetch_landing_page_data,
    _parse_bundles_from_data,
)


# Default paths and TTL
_BUNDLES_DUMP_PATH = Path("raw_bundles_dump.json")
_CACHE_TTL_SECONDS = 3600  # 1 hour


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