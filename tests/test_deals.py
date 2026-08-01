"""
Tests for the Deal Inspector router – /deals endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestDealsPage:
    """GET /deals returns the full page template."""

    def test_deals_page_returns_200(self, client: TestClient):
        response = client.get("/deals")
        assert response.status_code == 200
        assert "Deal Inspector" in response.text
        assert "deal-stream" in response.text


class TestDealsLive:
    """GET /deals/live loads bundles and renders deal cards by category."""

    def test_deals_live_returns_200_with_bundles(self, client: TestClient):
        mock_bundles = [
            {
                "title": "Python Programming Bundle",
                "url": "https://www.humblebundle.com/books/python-programming-bundle",
                "author": "Test Publisher",
                "end_date": "2099-12-31T23:59:59+00:00",
                "machine_name": "python-bundle",
            },
            {
                "title": "Game Dev Mega Pack",
                "url": "https://www.humblebundle.com/games/game-dev-mega-pack",
                "author": "",
                "end_date": "2099-12-31T23:59:59+00:00",
                "machine_name": "gamedev-pack",
            },
            {
                "title": "Design Software Suite",
                "url": "https://www.humblebundle.com/software/design-software-suite",
                "author": "DesignCo",
                "end_date": "2099-12-31T23:59:59+00:00",
                "machine_name": "design-suite",
            },
        ]

        with patch("app.routers.deals.load_active_bundles", return_value=mock_bundles):
            response = client.get("/deals/live")

        assert response.status_code == 200
        # Bundle titles should appear in the response
        assert "Python Programming Bundle" in response.text
        assert "Game Dev Mega Pack" in response.text
        assert "Design Software Suite" in response.text
        # Category labels should be present
        assert "📚 Books" in response.text
        assert "🎮 Games" in response.text
        assert "💻 Software" in response.text

    def test_deals_live_handles_error(self, client: TestClient):
        with patch(
            "app.routers.deals.load_active_bundles",
            side_effect=RuntimeError("Network timeout"),
        ):
            response = client.get("/deals/live")

        assert response.status_code == 200
        assert "Network timeout" in response.text


class TestDealsInspect:
    """GET /deals/inspect fetches and evaluates a bundle against the library."""

    def test_deals_inspect_no_library_items(self, client: TestClient):
        mock_bundle_data = {
            "bundle_name": "Test Bundle",
            "machine_name": "test-bundle",
            "items": [
                {"title": "Book One", "machine_name": "book-one", "formats": ["PDF"]},
                {"title": "Book Two", "machine_name": "book-two", "formats": ["EPUB"]},
                {"title": "Book Three", "machine_name": "book-three", "formats": ["PDF"]},
            ],
            "pricing": [
                {
                    "tier_id": "tier1",
                    "amount": 1.0,
                    "currency": "USD",
                    "is_bta": False,
                    "header": "Pay $1 or more",
                    "item_machine_names": ["book-one", "book-two"],
                },
                {
                    "tier_id": "tier2",
                    "amount": 18.0,
                    "currency": "USD",
                    "is_bta": False,
                    "header": "Pay $18 or more",
                    "item_machine_names": ["book-three"],
                },
            ],
            "tier_item_map": {
                "tier1": [
                    {"title": "Book One", "machine_name": "book-one", "formats": ["PDF"]},
                    {"title": "Book Two", "machine_name": "book-two", "formats": ["EPUB"]},
                ],
                "tier2": [
                    {"title": "Book Three", "machine_name": "book-three", "formats": ["PDF"]},
                ],
            },
        }

        with patch(
            "app.routers.deals.fetch_bundle_items", return_value=mock_bundle_data
        ), patch("app.routers.deals.log_evaluated_bundle"):
            response = client.get(
                "/deals/inspect",
                params={"url": "https://www.humblebundle.com/books/test-bundle"},
            )

        assert response.status_code == 200
        # No library items exist, so overlap should be 0%
        assert "Test Bundle" in response.text
        assert "0.0% Owned" in response.text
        assert "Pricing Tiers" in response.text
        # Check tier breakdown: all items unowned
        assert "[+] Book One" in response.text
        assert "[+] Book Two" in response.text
        assert "[+] Book Three" in response.text

    def test_deals_inspect_handles_fetch_error(self, client: TestClient):
        with patch(
            "app.routers.deals.fetch_bundle_items",
            side_effect=RuntimeError("Network timeout fetching bundle"),
        ):
            response = client.get(
                "/deals/inspect",
                params={"url": "https://www.humblebundle.com/books/bad-bundle"},
            )

        assert response.status_code == 200
        assert "Network timeout fetching bundle" in response.text

    def test_deals_inspect_with_partial_overlap(self, client: TestClient):
        """With library items loaded, test overlap calculation."""
        from database import SessionLocal
        from models import Bundle, Item

        # Insert a library item that matches one of the bundle items
        db = SessionLocal()
        bundle_id = None
        item_id = None
        try:
            bundle = Bundle(title="Existing Bundle", purchase_date="2024-01-01")
            db.add(bundle)
            db.flush()
            bundle_id = bundle.id

            item = Item(
                bundle_id=bundle.id,
                title="Book One",
                publisher="Test Publisher",
                item_type="ebook",
                available_formats=["PDF"],
                downloads={},
            )
            db.add(item)
            db.flush()
            item_id = item.id
            db.commit()
        finally:
            db.close()

        mock_bundle_data = {
            "bundle_name": "Test Bundle",
            "machine_name": "test-bundle",
            "items": [
                {"title": "Book One", "machine_name": "book-one", "formats": ["PDF"]},
                {"title": "Book Two", "machine_name": "book-two", "formats": ["EPUB"]},
                {"title": "Book Three", "machine_name": "book-three", "formats": ["PDF"]},
            ],
            "pricing": [
                {
                    "tier_id": "tier1",
                    "amount": 1.0,
                    "currency": "USD",
                    "is_bta": False,
                    "header": "Pay $1 or more",
                    "item_machine_names": ["book-one", "book-two"],
                },
                {
                    "tier_id": "tier2",
                    "amount": 18.0,
                    "currency": "USD",
                    "is_bta": False,
                    "header": "Pay $18 or more",
                    "item_machine_names": ["book-three"],
                },
            ],
            "tier_item_map": {
                "tier1": [
                    {"title": "Book One", "machine_name": "book-one", "formats": ["PDF"]},
                    {"title": "Book Two", "machine_name": "book-two", "formats": ["EPUB"]},
                ],
                "tier2": [
                    {"title": "Book Three", "machine_name": "book-three", "formats": ["PDF"]},
                ],
            },
        }

        with patch(
            "app.routers.deals.fetch_bundle_items", return_value=mock_bundle_data
        ), patch("app.routers.deals.log_evaluated_bundle"):
            response = client.get(
                "/deals/inspect",
                params={"url": "https://www.humblebundle.com/books/test-bundle"},
            )

        assert response.status_code == 200
        # 1 out of 3 = 33.3% owned
        assert "33.3% Owned" in response.text
        # Book One should be owned
        assert "[x] Book One" in response.text
        assert "[+] Book Two" in response.text
        assert "[+] Book Three" in response.text

        # Clean up the test data to avoid leaking into other tests
        db = SessionLocal()
        try:
            if item_id is not None:
                db.query(Item).filter(Item.id == item_id).delete()
            if bundle_id is not None:
                db.query(Bundle).filter(Bundle.id == bundle_id).delete()
            db.commit()
        finally:
            db.close()


class TestDealsReset:
    """GET /deals/reset returns the placeholder drawer state."""

    def test_deals_reset_returns_placeholder(self, client: TestClient):
        response = client.get("/deals/reset")
        assert response.status_code == 200
        assert "Select a live bundle" in response.text
        assert "Bundle Inspector" in response.text