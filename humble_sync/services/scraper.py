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
