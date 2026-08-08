"""Service modules for Humble Library Sync business logic."""

from humble_sync.services import parser, duplicates, status, evaluator, client
from humble_sync.services.bundle_cache import (
    capture_active_bundles,
    load_active_bundles,
    parse_bundles_dump,
)
from humble_sync.services.deal_logger import (
    format_expired_deals_report,
    format_expired_reading_list,
    get_expired_entries,
    get_unexpired_entries,
    load_evaluated_bundles_log,
    log_evaluated_bundle,
    mark_expired_entries,
)
from humble_sync.services.evaluator import (
    evaluate_deal,
    fetch_bundle_items,
    format_deal_report,
)
from humble_sync.services.client import (
    HumbleAPIClient,
    normalize_orders_to_catalog,
    sync_account_library,
)

__all__ = [
    "parser",
    "duplicates",
    "status",
    "evaluator",
    "client",
    "capture_active_bundles",
    "evaluate_deal",
    "fetch_bundle_items",
    "format_deal_report",
    "format_expired_deals_report",
    "format_expired_reading_list",
    "get_expired_entries",
    "get_unexpired_entries",
    "load_active_bundles",
    "load_evaluated_bundles_log",
    "log_evaluated_bundle",
    "mark_expired_entries",
    "parse_bundles_dump",
    "HumbleAPIClient",
    "normalize_orders_to_catalog",
    "sync_account_library",
]
