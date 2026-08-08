"""
Scraper module for Humble Library Sync.
Handles low-level HTTP fetching of Humble Bundle landing page data.
"""

import json
from typing import Any

import requests
from bs4 import BeautifulSoup


# Browser User-Agent to avoid bot detection
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Humble Bundle URLs
_BUNDLES_URL = "https://www.humblebundle.com/bundles"


def _fetch_landing_page_data() -> dict[str, Any]:
    """
    Fetches the raw landing page JSON data from Humble Bundle.

    GETs the bundles page and extracts the embedded JSON from
    the <script id="landingPage-json-data"> tag.

    Returns:
        The parsed JSON data dict.

    Raises:
        RuntimeError: If network request fails or data cannot be parsed.
    """
    try:
        response = requests.get(
            _BUNDLES_URL,
            headers={"User-Agent": _USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"[!] Network error fetching bundles: {e}") from e

    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find("script", id="landingPage-json-data")

    if not script_tag or not script_tag.string:
        raise RuntimeError("[!] Could not find bundle data script tag on page.")

    try:
        return json.loads(script_tag.string)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"[!] Failed to parse bundle JSON data: {e}") from e


def _parse_bundles_from_data(page_data: dict[str, Any]) -> list[dict[str, str]]:
    """
    Extracts active bundle listings from the raw landing page JSON.

    Iterates over books, games, and software categories, traverses
    mosaic sections, and extracts product information.

    Args:
        page_data: The full JSON data from the landing page script tag.

    Returns:
        List of dicts with keys: title, url, author, end_date, machine_name.
    """
    data = page_data.get("data", {})
    bundles: list[dict[str, str]] = []

    categories = ["books", "games", "software"]

    for category in categories:
        category_data = data.get(category, {})
        mosaic = category_data.get("mosaic", [])

        for section in mosaic:
            products = section.get("products", [])
            for product in products:
                tile_name = product.get("tile_name", "")
                product_url = product.get("product_url", "")
                author = product.get("author", "")
                end_date = product.get("end_date|datetime", "")
                machine_name = product.get("machine_name", "")

                if tile_name and product_url:
                    if product_url.startswith("/"):
                        product_url = f"https://www.humblebundle.com{product_url}"

                    bundles.append({
                        "title": tile_name,
                        "url": product_url,
                        "author": author,
                        "end_date": end_date,
                        "machine_name": machine_name,
                    })

    return bundles


def fetch_bundle_items(bundle_url: str) -> dict[str, Any]:
    """
    Fetches all items from a specific bundle page.

    GETs the bundle URL and parses the embedded webpack data to extract
    all tier items with their titles, machine names, and available formats.

    Args:
        bundle_url: Full URL to the bundle page (e.g., https://www.humblebundle.com/books/...).

    Returns:
        Dict with keys: bundle_name (str), items (list of dicts with title, machine_name, formats).

    Raises:
        RuntimeError: If network request fails or data cannot be parsed.
    """
    try:
        response = requests.get(
            bundle_url,
            headers={"User-Agent": _USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"[!] Network error fetching bundle: {e}") from e

    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find("script", id="webpack-bundle-page-data")

    if not script_tag or not script_tag.string:
        raise RuntimeError("[!] Could not find bundle data script tag on page.")

    try:
        page_data = json.loads(script_tag.string)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"[!] Failed to parse bundle JSON data: {e}") from e

    bundle_data = page_data.get("bundleData", {})
    bundle_name = (
        bundle_data.get("basic_data", {}).get("human_name")
        or bundle_data.get("machine_name", "Unknown Bundle")
    )

    # Extract pricing tiers with their item machine names
    tier_pricing = bundle_data.get("tier_pricing_data", {})
    tier_display = bundle_data.get("tier_display_data", {})
    pricing: list[dict[str, Any]] = []
    for tier_id in tier_pricing:
        price_info = tier_pricing[tier_id]
        display_info = tier_display.get(tier_id, {})
        amount = price_info.get("price|money", {}).get("amount", 0)
        currency = price_info.get("price|money", {}).get("currency", "USD")
        is_bta = price_info.get("is_bta", False)
        header = display_info.get("header", "")
        item_machine_names = display_info.get("tier_item_machine_names", [])
        pricing.append({
            "tier_id": tier_id,
            "amount": amount,
            "currency": currency,
            "is_bta": is_bta,
            "header": header,
            "item_machine_names": item_machine_names,
        })
    # Sort by price ascending
    pricing.sort(key=lambda t: t["amount"])

    items: list[dict[str, Any]] = []
    tier_item_data = bundle_data.get("tier_item_data", {})

    for machine_name, item_info in tier_item_data.items():
        human_name = item_info.get("human_name", "")
        if not human_name:
            continue

        # Extract available formats from downloads section
        formats: list[str] = []
        downloads = item_info.get("downloads", [])
        for download in downloads:
            download_name = download.get("platform", "")
            if download_name:
                formats.append(download_name)

        # Also check for URL-based formats
        url_data = item_info.get("url_data", {})
        for fmt_key in url_data:
            if fmt_key not in formats:
                formats.append(fmt_key)

        items.append({
            "title": human_name,
            "machine_name": machine_name,
            "formats": sorted(set(formats)),
        })

    tier_item_map = _build_tier_item_map(items, pricing)

    return {
        "bundle_name": bundle_name,
        "items": items,
        "pricing": pricing,
        "tier_item_map": tier_item_map,
    }


def _build_tier_item_map(
    items: list[dict[str, Any]],
    pricing: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Builds a mapping of tier_id to the list of item dicts in that tier.

    Uses the ``item_machine_names`` field from each pricing tier to
    look up items by their ``machine_name``.

    Args:
        items: Full item list from fetch_bundle_items().
        pricing: Pricing tier list from fetch_bundle_items().

    Returns:
        Dict of {tier_id: [item_dict, ...]} with items in tier order.
    """
    # Build a lookup from machine_name -> item
    item_by_machine: dict[str, dict[str, Any]] = {}
    for item in items:
        mn = item.get("machine_name", "")
        if mn:
            item_by_machine[mn] = item

    tier_item_map: dict[str, list[dict[str, Any]]] = {}
    for tier in pricing:
        tid = tier["tier_id"]
        machine_names = tier.get("item_machine_names", [])
        tier_items = []
        for mn in machine_names:
            item = item_by_machine.get(mn)
            if item:
                tier_items.append(item)
        tier_item_map[tid] = tier_items

    return tier_item_map
