"""
Deal Evaluator module for Humble Library Sync.
Fetches live bundle data from Humble Bundle and evaluates overlap against owned library.
"""

from datetime import datetime, timezone
from typing import Any

from humble_sync.services.bundle_cache import (
    capture_active_bundles,
    load_active_bundles,
)
from humble_sync.services.deal_logger import (  # noqa: F401 – re-exported
    format_expired_deals_report,
    format_expired_reading_list,
    get_expired_entries,
    get_unexpired_entries,
    load_evaluated_bundles_log,
    log_evaluated_bundle,
    mark_expired_entries,
)
from humble_sync.services.duplicates import normalize_title
from humble_sync.services.scraper import (
    _USER_AGENT,
    fetch_bundle_items,
)


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