"""
Async HTTP client for direct Humble Bundle API access using session cookies.
Provides methods to fetch user orders and sync library data to the database.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from humble_sync.db.database import SessionLocal
from humble_sync.services.parser import extract_items_from_bundle, sync_catalog_to_db


# Standard browser headers to avoid bot detection
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.humblebundle.com/home/library",
    "Origin": "https://www.humblebundle.com",
    "Connection": "keep-alive",
}

BASE_URL = "https://www.humblebundle.com"


class HumbleAPIClient:
    """Async HTTP client for Humble Bundle API using session-based authentication."""

    def __init__(self, session_cookie: str) -> None:
        """Initialize the client with a session cookie.

        Args:
            session_cookie: The `_simpleauth_sess` cookie value or full cookie header string.
        """
        self._session_cookie = session_cookie
        self._cookies = self._parse_cookies(session_cookie)
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=DEFAULT_HEADERS,
            cookies=self._cookies,
            timeout=30.0,
        )

    @staticmethod
    def _parse_cookies(cookie_string: str) -> dict[str, str]:
        """Parse a cookie string into a dictionary.

        Handles both raw cookie header format ("key=value; key2=value2")
        and just the value portion for _simpleauth_sess.
        """
        cookies: dict[str, str] = {}

        # If it looks like a full cookie header with multiple key=value pairs
        if "=" in cookie_string and ";" in cookie_string:
            for part in cookie_string.split(";"):
                part = part.strip()
                if "=" in part:
                    key, value = part.split("=", 1)
                    cookies[key.strip()] = value.strip()
        elif "=" in cookie_string:
            # Single key=value pair
            key, value = cookie_string.split("=", 1)
            cookies[key.strip()] = value.strip()
        else:
            # Just the value - assume it's for _simpleauth_sess
            cookies["_simpleauth_sess"] = cookie_string

        return cookies

    async def get_gamekeys(self) -> list[str]:
        """Fetch all order gamekeys for the authenticated user.

        Attempts /api/v1/user/order first, falls back to /api/v1/orders.

        Returns:
            List of gamekey strings.

        Raises:
            httpx.HTTPStatusError: If both endpoints fail.
        """
        # Try primary endpoint
        try:
            response = await self._client.get("/api/v1/user/order")
            response.raise_for_status()
            data = response.json()
            return self._extract_gamekeys(data)
        except httpx.HTTPStatusError:
            # Fallback to alternative endpoint
            response = await self._client.get("/api/v1/orders")
            response.raise_for_status()
            data = response.json()
            return self._extract_gamekeys(data)

    @staticmethod
    def _extract_gamekeys(data: Any) -> list[str]:
        """Extract gamekeys from various API response formats.

        Handles:
        - List of dicts with 'gamekey' key
        - Dict with 'orders' key containing list of dicts
        - List of strings (raw gamekeys)
        """
        gamekeys: list[str] = []

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    if "gamekey" in item:
                        gamekeys.append(item["gamekey"])
                    elif "key" in item:
                        gamekeys.append(item["key"])
                elif isinstance(item, str):
                    gamekeys.append(item)
        elif isinstance(data, dict):
            orders = data.get("orders", [])
            for item in orders:
                if isinstance(item, dict):
                    if "gamekey" in item:
                        gamekeys.append(item["gamekey"])
                    elif "key" in item:
                        gamekeys.append(item["key"])

        return gamekeys

    async def get_order_details(self, gamekey: str) -> dict[str, Any]:
        """Fetch full order details for a specific gamekey.

        Args:
            gamekey: The unique identifier for the order.

        Returns:
            Order details dictionary.

        Raises:
            httpx.HTTPStatusError: If the request fails.
        """
        response = await self._client.get(f"/api/v1/order/{gamekey}")
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "HumbleAPIClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


def normalize_orders_to_catalog(
    orders: list[dict[str, Any]], captured_at: Optional[str] = None
) -> dict[str, Any]:
    """Normalize a list of order payloads into the standard catalog format.

    This produces the same structure as parser.parse_dump() so the data
    can be passed directly to sync_catalog_to_db().

    Args:
        orders: List of order detail dictionaries from the API.
        captured_at: ISO timestamp for when data was captured. Defaults to now.

    Returns:
        Catalog dictionary with 'metadata' and 'items' keys.
    """
    if captured_at is None:
        captured_at = datetime.now(timezone.utc).isoformat()

    catalog_map: dict[tuple[str, str], dict] = {}

    for order in orders:
        if not isinstance(order, dict):
            continue

        # Extract items using the existing parser function
        items = extract_items_from_bundle(order, captured_at)

        for item in items:
            key = (item["title"], item["bundle"])
            if key not in catalog_map:
                catalog_map[key] = item

    sorted_items = sorted(
        catalog_map.values(),
        key=lambda x: (x["title"].lower(), x["bundle"].lower()),
    )

    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dump_captured_at": captured_at,
            "total_items": len(sorted_items),
        },
        "items": sorted_items,
    }


async def sync_account_library(
    session_cookie: str, db_session=None
) -> dict[str, Any]:
    """Orchestrate a full library sync from the Humble API to the database.

    Fetches all user orders, normalizes them into catalog format, and
    persists them to the database.

    Args:
        session_cookie: The `_simpleauth_sess` cookie value.
        db_session: Optional SQLAlchemy session. If None, a new session is created.

    Returns:
        The normalized catalog dictionary that was synced.
    """
    async with HumbleAPIClient(session_cookie) as client:
        # Fetch all gamekeys
        gamekeys = await client.get_gamekeys()

        if not gamekeys:
            # No orders found - return empty catalog
            catalog = normalize_orders_to_catalog([])
            if db_session is None:
                sync_catalog_to_db(catalog)
            else:
                sync_catalog_to_db(catalog, db_session=db_session)
            return catalog

        # Fetch all order details concurrently
        order_tasks = [client.get_order_details(gk) for gk in gamekeys]
        orders = await asyncio.gather(*order_tasks, return_exceptions=True)

        # Filter out any failed requests
        valid_orders = [o for o in orders if isinstance(o, dict)]

        # Normalize to catalog format
        catalog = normalize_orders_to_catalog(valid_orders)

        # Sync to database
        if db_session is None:
            sync_catalog_to_db(catalog)
        else:
            sync_catalog_to_db(catalog, db_session=db_session)

        return catalog