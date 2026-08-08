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