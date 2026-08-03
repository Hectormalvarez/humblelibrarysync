"""
Unit tests for humble_sync.services.client module.
Tests HumbleAPIClient methods and response parsing using httpx.MockTransport.
All tests are fully offline with no real network calls.
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Ensure test database is used
os.environ["DATABASE_URL"] = "sqlite:///./test_humble_library.db"

from humble_sync.db.database import Base, SessionLocal, engine
from humble_sync.db.models import Bundle, Item
from humble_sync.services.client import (
    BASE_URL,
    DEFAULT_HEADERS,
    HumbleAPIClient,
    normalize_orders_to_catalog,
    sync_account_library,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="function", autouse=True)
def clean_test_database():
    """Drop and recreate the schema before every test function."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def make_mock_handler(responses: dict) -> httpx.MockTransport:
    """Create a mock transport handler that returns predefined responses.

    Args:
        responses: Dict mapping URL paths to (status_code, json_data) tuples.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in responses:
            status_code, data = responses[path]
            return httpx.Response(status_code, json=data)
        return httpx.Response(404, json={"error": "Not found"})

    return httpx.MockTransport(handler)


# ── Cookie Parsing Tests ──────────────────────────────────────────────────


class TestCookieParsing:
    """Tests for cookie string parsing in HumbleAPIClient."""

    def test_parse_full_cookie_header(self):
        """Verify full cookie header with multiple key=value pairs is parsed."""
        cookie_str = "_simpleauth_sess=abc123; other_cookie=xyz"
        cookies = HumbleAPIClient._parse_cookies(cookie_str)
        assert cookies["_simpleauth_sess"] == "abc123"
        assert cookies["other_cookie"] == "xyz"

    def test_parse_single_key_value(self):
        """Verify single key=value pair is parsed."""
        cookie_str = "_simpleauth_sess=abc123"
        cookies = HumbleAPIClient._parse_cookies(cookie_str)
        assert cookies["_simpleauth_sess"] == "abc123"

    def test_parse_value_only(self):
        """Verify value-only string is assigned to _simpleauth_sess."""
        cookie_str = "abc123xyz"
        cookies = HumbleAPIClient._parse_cookies(cookie_str)
        assert cookies["_simpleauth_sess"] == "abc123xyz"

    def test_parse_empty_value(self):
        """Verify empty string results in empty _simpleauth_sess."""
        cookie_str = ""
        cookies = HumbleAPIClient._parse_cookies(cookie_str)
        assert cookies["_simpleauth_sess"] == ""


# ── Client Initialization Tests ───────────────────────────────────────────


class TestClientInitialization:
    """Tests for HumbleAPIClient initialization."""

    def test_client_sets_cookies(self):
        """Verify cookies are set on the underlying httpx client."""
        client = HumbleAPIClient("_simpleauth_sess=test123")
        assert client._cookies["_simpleauth_sess"] == "test123"
        assert client._client.cookies.get("_simpleauth_sess") == "test123"

    def test_client_sets_base_url(self):
        """Verify base URL is set correctly."""
        client = HumbleAPIClient("test_cookie")
        assert str(client._client.base_url) == BASE_URL

    def test_client_sets_browser_headers(self):
        """Verify browser-like headers are set."""
        client = HumbleAPIClient("test_cookie")
        headers = client._client.headers
        assert "Mozilla" in headers.get("User-Agent", "")
        assert "application/json" in headers.get("Accept", "")


# ── get_gamekeys Tests ────────────────────────────────────────────────────


class TestGetGamekeys:
    """Tests for get_gamekeys method."""

    @pytest.mark.asyncio
    async def test_get_gamekeys_from_list_of_dicts(self):
        """Verify gamekeys extracted from list of dicts with 'gamekey' key."""
        responses = {
            "/api/v1/user/order": (
                200,
                [
                    {"gamekey": "key1", "created": "2024-01-01"},
                    {"gamekey": "key2", "created": "2024-01-02"},
                ],
            )
        }
        transport = make_mock_handler(responses)

        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as mock_client:
            client = HumbleAPIClient("test_cookie")
            client._client = mock_client

            gamekeys = await client.get_gamekeys()
            assert gamekeys == ["key1", "key2"]

    @pytest.mark.asyncio
    async def test_get_gamekeys_from_dict_with_orders_key(self):
        """Verify gamekeys extracted from dict with 'orders' key."""
        responses = {
            "/api/v1/user/order": (
                200,
                {
                    "orders": [
                        {"gamekey": "keyA"},
                        {"gamekey": "keyB"},
                    ]
                },
            )
        }
        transport = make_mock_handler(responses)

        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as mock_client:
            client = HumbleAPIClient("test_cookie")
            client._client = mock_client

            gamekeys = await client.get_gamekeys()
            assert gamekeys == ["keyA", "keyB"]

    @pytest.mark.asyncio
    async def test_get_gamekeys_from_list_of_strings(self):
        """Verify gamekeys extracted from list of raw strings."""
        responses = {
            "/api/v1/user/order": (200, ["keyX", "keyY", "keyZ"])
        }
        transport = make_mock_handler(responses)

        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as mock_client:
            client = HumbleAPIClient("test_cookie")
            client._client = mock_client

            gamekeys = await client.get_gamekeys()
            assert gamekeys == ["keyX", "keyY", "keyZ"]

    @pytest.mark.asyncio
    async def test_get_gamekeys_fallback_to_orders_endpoint(self):
        """Verify fallback to /api/v1/orders when primary endpoint fails."""
        responses = {
            "/api/v1/user/order": (404, {"error": "Not found"}),
            "/api/v1/orders": (200, [{"gamekey": "fallback_key"}]),
        }
        transport = make_mock_handler(responses)

        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as mock_client:
            client = HumbleAPIClient("test_cookie")
            client._client = mock_client

            gamekeys = await client.get_gamekeys()
            assert gamekeys == ["fallback_key"]

    @pytest.mark.asyncio
    async def test_get_gamekeys_empty_response(self):
        """Verify empty list returned for empty response."""
        responses = {"/api/v1/user/order": (200, [])}
        transport = make_mock_handler(responses)

        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as mock_client:
            client = HumbleAPIClient("test_cookie")
            client._client = mock_client

            gamekeys = await client.get_gamekeys()
            assert gamekeys == []

    @pytest.mark.asyncio
    async def test_get_gamekeys_with_key_field(self):
        """Verify gamekeys extracted from items with 'key' field instead of 'gamekey'."""
        responses = {
            "/api/v1/user/order": (200, [{"key": "alt_key1"}, {"key": "alt_key2"}])
        }
        transport = make_mock_handler(responses)

        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as mock_client:
            client = HumbleAPIClient("test_cookie")
            client._client = mock_client

            gamekeys = await client.get_gamekeys()
            assert gamekeys == ["alt_key1", "alt_key2"]


# ── get_order_details Tests ───────────────────────────────────────────────


class TestGetOrderDetails:
    """Tests for get_order_details method."""

    @pytest.mark.asyncio
    async def test_get_order_details_success(self):
        """Verify order details are returned correctly."""
        order_data = {
            "gamekey": "test_key",
            "product": {"human_name": "Test Bundle"},
            "subproducts": [
                {
                    "human_name": "Test Book",
                    "payee": {"human_name": "Publisher"},
                    "downloads": [],
                }
            ],
        }
        responses = {"/api/v1/order/test_key": (200, order_data)}
        transport = make_mock_handler(responses)

        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as mock_client:
            client = HumbleAPIClient("test_cookie")
            client._client = mock_client

            result = await client.get_order_details("test_key")
            assert result["gamekey"] == "test_key"
            assert result["product"]["human_name"] == "Test Bundle"

    @pytest.mark.asyncio
    async def test_get_order_details_not_found(self):
        """Verify HTTPStatusError raised for non-existent order."""
        responses = {"/api/v1/order/missing_key": (404, {"error": "Not found"})}
        transport = make_mock_handler(responses)

        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as mock_client:
            client = HumbleAPIClient("test_cookie")
            client._client = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                await client.get_order_details("missing_key")


# ── _extract_gamekeys Tests ───────────────────────────────────────────────


class TestExtractGamekeys:
    """Tests for _extract_gamekeys static method."""

    def test_extract_from_list_of_dicts(self):
        """Verify extraction from list of dicts."""
        data = [{"gamekey": "a"}, {"gamekey": "b"}]
        assert HumbleAPIClient._extract_gamekeys(data) == ["a", "b"]

    def test_extract_from_dict_with_orders(self):
        """Verify extraction from dict with orders key."""
        data = {"orders": [{"gamekey": "x"}, {"gamekey": "y"}]}
        assert HumbleAPIClient._extract_gamekeys(data) == ["x", "y"]

    def test_extract_from_list_of_strings(self):
        """Verify extraction from list of strings."""
        data = ["key1", "key2"]
        assert HumbleAPIClient._extract_gamekeys(data) == ["key1", "key2"]

    def test_extract_empty_list(self):
        """Verify empty list returns empty list."""
        assert HumbleAPIClient._extract_gamekeys([]) == []

    def test_extract_empty_dict(self):
        """Verify empty dict returns empty list."""
        assert HumbleAPIClient._extract_gamekeys({}) == []

    def test_extract_with_key_field(self):
        """Verify extraction using 'key' field."""
        data = [{"key": "alt1"}, {"key": "alt2"}]
        assert HumbleAPIClient._extract_gamekeys(data) == ["alt1", "alt2"]


# ── normalize_orders_to_catalog Tests ─────────────────────────────────────


class TestNormalizeOrdersToCatalog:
    """Tests for normalize_orders_to_catalog function."""

    def test_empty_orders(self):
        """Verify empty orders list produces empty catalog."""
        catalog = normalize_orders_to_catalog([])
        assert catalog["metadata"]["total_items"] == 0
        assert catalog["items"] == []

    def test_single_order_with_subproducts(self):
        """Verify single order with subproducts is normalized correctly."""
        orders = [
            {
                "product": {"human_name": "Test Bundle"},
                "created": "2024-01-01",
                "subproducts": [
                    {
                        "human_name": "Test Book",
                        "payee": {"human_name": "Publisher"},
                        "downloads": [],
                    }
                ],
            }
        ]
        catalog = normalize_orders_to_catalog(orders, captured_at="2024-01-01T00:00:00+00:00")
        assert catalog["metadata"]["total_items"] == 1
        assert catalog["items"][0]["title"] == "Test Book"
        assert catalog["items"][0]["bundle"] == "Test Bundle"

    def test_multiple_orders(self):
        """Verify multiple orders are combined and sorted."""
        orders = [
            {
                "product": {"human_name": "Bundle A"},
                "created": "2024-01-01",
                "subproducts": [
                    {"human_name": "Zebra Book", "payee": {"human_name": "Pub"}, "downloads": []}
                ],
            },
            {
                "product": {"human_name": "Bundle B"},
                "created": "2024-01-02",
                "subproducts": [
                    {"human_name": "Alpha Book", "payee": {"human_name": "Pub"}, "downloads": []}
                ],
            },
        ]
        catalog = normalize_orders_to_catalog(orders)
        assert catalog["metadata"]["total_items"] == 2
        # Items should be sorted alphabetically
        assert catalog["items"][0]["title"] == "Alpha Book"
        assert catalog["items"][1]["title"] == "Zebra Book"

    def test_order_with_third_party_keys(self):
        """Verify third-party keys are extracted."""
        orders = [
            {
                "product": {"human_name": "Key Bundle"},
                "created": "2024-01-01",
                "subproducts": [],
                "tpkd_dict": {
                    "all_tpks": [
                        {"human_name": "Steam Key", "key_type_human_name": "Steam Key"}
                    ]
                },
            }
        ]
        catalog = normalize_orders_to_catalog(orders)
        assert catalog["metadata"]["total_items"] == 1
        assert catalog["items"][0]["type"] == "redemption_key"
        assert catalog["items"][0]["available_formats"] == ["KEY"]

    def test_duplicate_items_deduplicated(self):
        """Verify duplicate items across orders are deduplicated."""
        orders = [
            {
                "product": {"human_name": "Bundle 1"},
                "created": "2024-01-01",
                "subproducts": [
                    {"human_name": "Same Book", "payee": {"human_name": "Pub"}, "downloads": []}
                ],
            },
            {
                "product": {"human_name": "Bundle 1"},
                "created": "2024-01-01",
                "subproducts": [
                    {"human_name": "Same Book", "payee": {"human_name": "Pub"}, "downloads": []}
                ],
            },
        ]
        catalog = normalize_orders_to_catalog(orders)
        # Same title + same bundle = deduplicated
        assert catalog["metadata"]["total_items"] == 1

    def test_captured_at_default(self):
        """Verify captured_at defaults to current time if not provided."""
        catalog = normalize_orders_to_catalog([])
        assert "T" in catalog["metadata"]["dump_captured_at"]


# ── sync_account_library Tests ────────────────────────────────────────────


class TestSyncAccountLibrary:
    """Tests for sync_account_library orchestrator function."""

    @pytest.mark.asyncio
    async def test_sync_empty_library(self):
        """Verify sync with no orders creates empty catalog."""
        responses = {"/api/v1/user/order": (200, [])}
        transport = make_mock_handler(responses)

        with patch("humble_sync.services.client.HumbleAPIClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.get_gamekeys = AsyncMock(return_value=[])
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            catalog = await sync_account_library("test_cookie")

            assert catalog["metadata"]["total_items"] == 0
            assert catalog["items"] == []

    @pytest.mark.asyncio
    async def test_sync_with_orders(self):
        """Verify sync with orders populates database."""
        orders = [
            {
                "gamekey": "key1",
                "product": {"human_name": "Test Bundle"},
                "created": "2024-01-01",
                "subproducts": [
                    {
                        "human_name": "Test Book",
                        "payee": {"human_name": "Publisher"},
                        "downloads": [],
                    }
                ],
            }
        ]

        with patch("humble_sync.services.client.HumbleAPIClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.get_gamekeys = AsyncMock(return_value=["key1"])
            mock_instance.get_order_details = AsyncMock(return_value=orders[0])
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            catalog = await sync_account_library("test_cookie")

            assert catalog["metadata"]["total_items"] == 1
            assert catalog["items"][0]["title"] == "Test Book"

            # Verify database was populated
            db = SessionLocal()
            try:
                bundle = db.query(Bundle).filter_by(title="Test Bundle").first()
                assert bundle is not None
                item = db.query(Item).filter_by(title="Test Book").first()
                assert item is not None
                assert item.bundle_id == bundle.id
            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_sync_with_db_session_injection(self):
        """Verify sync works with injected db_session."""
        with patch("humble_sync.services.client.HumbleAPIClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.get_gamekeys = AsyncMock(return_value=[])
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            db = SessionLocal()
            try:
                catalog = await sync_account_library("test_cookie", db_session=db)
                assert catalog["metadata"]["total_items"] == 0
            finally:
                db.close()

    @pytest.mark.asyncio
    async def test_sync_handles_failed_order_fetches(self):
        """Verify sync handles partial failures in order fetching."""
        with patch("humble_sync.services.client.HumbleAPIClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.get_gamekeys = AsyncMock(return_value=["key1", "key2"])

            # First order succeeds, second raises exception
            async def get_order_side_effect(gamekey):
                if gamekey == "key1":
                    return {
                        "gamekey": "key1",
                        "product": {"human_name": "Good Bundle"},
                        "created": "2024-01-01",
                        "subproducts": [
                            {
                                "human_name": "Good Book",
                                "payee": {"human_name": "Pub"},
                                "downloads": [],
                            }
                        ],
                    }
                raise httpx.HTTPStatusError("Not found", request=MagicMock(), response=MagicMock())

            mock_instance.get_order_details = AsyncMock(side_effect=get_order_side_effect)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            catalog = await sync_account_library("test_cookie")

            # Only the successful order should be in catalog
            assert catalog["metadata"]["total_items"] == 1
            assert catalog["items"][0]["title"] == "Good Book"


# ── Async Context Manager Tests ───────────────────────────────────────────


class TestAsyncContextManager:
    """Tests for async context manager protocol."""

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self):
        """Verify client is closed when exiting context."""
        client = HumbleAPIClient("test_cookie")
        original_close = client.close
        close_called = False

        async def mock_close():
            nonlocal close_called
            close_called = True
            await original_close()

        client.close = mock_close

        async with client:
            pass

        assert close_called