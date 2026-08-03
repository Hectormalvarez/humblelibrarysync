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
        assert "[+]</span> <span class=\"sr-only\">New:</span> Book One" in response.text
        assert "[+]</span> <span class=\"sr-only\">New:</span> Book Two" in response.text
        assert "[+]</span> <span class=\"sr-only\">New:</span> Book Three" in response.text

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
        from humble_sync.db.database import SessionLocal
        from humble_sync.db.models import Bundle, Item

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
        assert "[x]</span> <span class=\"sr-only\">Owned:</span> Book One" in response.text
        assert "[+]</span> <span class=\"sr-only\">New:</span> Book Two" in response.text
        assert "[+]</span> <span class=\"sr-only\">New:</span> Book Three" in response.text

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
        assert "Select a live or expired bundle" in response.text
        assert "Bundle Inspector" in response.text


class TestDealsExpired:
    """GET /deals/expired renders expired bundle list rows without reading list."""

    def test_deals_expired_returns_200_with_data(self, client: TestClient):
        mock_entries = [
            {
                "bundle_name": "Expired Bundle One",
                "url": "https://www.humblebundle.com/books/expired-one",
                "machine_name": "expired-one",
                "end_date": "2024-01-15T23:59:59+00:00",
                "evaluated_at": "2024-01-10T12:00:00+00:00",
                "expired_at": "2024-01-16T00:00:00+00:00",
                "evaluation": {
                    "total_items": 10,
                    "matched_count": 3,
                    "overlap_percentage": 30.0,
                    "matched_items": ["Owned Book A", "Owned Book B", "Owned Book C"],
                    "new_items": ["New Title Alpha", "New Title Beta"],
                    "pricing": [],
                },
            },
            {
                "bundle_name": "Expired Bundle Two",
                "url": "https://www.humblebundle.com/games/expired-two",
                "machine_name": "expired-two",
                "end_date": "2024-02-20T23:59:59+00:00",
                "evaluated_at": "2024-02-15T12:00:00+00:00",
                "expired_at": "2024-02-21T00:00:00+00:00",
                "evaluation": {
                    "total_items": 5,
                    "matched_count": 1,
                    "overlap_percentage": 20.0,
                    "matched_items": ["Owned Game X"],
                    "new_items": ["New Title Gamma"],
                    "pricing": [],
                },
            },
        ]

        with patch(
            "app.routers.deals.mark_expired_entries"
        ) as mock_mark, patch(
            "app.routers.deals.load_evaluated_bundles_log", return_value=mock_entries
        ), patch(
            "app.routers.deals.get_expired_entries", return_value=mock_entries
        ):
            response = client.get("/deals/expired")

        assert response.status_code == 200
        # Verify mark_expired_entries was called
        mock_mark.assert_called_once()
        # Verify expired bundle names are rendered
        assert "Expired Bundle One" in response.text
        assert "Expired Bundle Two" in response.text
        # Verify stats are rendered
        assert "30.0% overlap" in response.text
        assert "20.0% overlap" in response.text
        # Verify HTMX attributes for clickable rows
        assert "hx-get" in response.text
        assert "/deals/inspect_expired" in response.text
        # Verify reading list is NOT present (refactored out)
        assert "Unowned Reading List" not in response.text

    def test_deals_expired_empty_state(self, client: TestClient):
        """When no expired entries exist, empty state message should appear."""
        with patch(
            "app.routers.deals.mark_expired_entries"
        ), patch(
            "app.routers.deals.load_evaluated_bundles_log", return_value=[]
        ), patch(
            "app.routers.deals.get_expired_entries", return_value=[]
        ):
            response = client.get("/deals/expired")

        assert response.status_code == 200
        assert "No expired bundle evaluations recorded" in response.text


class TestDealsInspectExpired:
    """GET /deals/inspect_expired loads saved evaluation into deal_inspector.html."""

    def test_deals_inspect_expired_returns_200_with_data(self, client: TestClient):
        """Verify inspect_expired loads saved evaluation data into the inspector."""
        from humble_sync.db.database import SessionLocal
        from humble_sync.db.models import EvaluatedBundle

        # Insert a test EvaluatedBundle record
        db = SessionLocal()
        record_id = None
        try:
            record = EvaluatedBundle(
                bundle_name="Test Expired Bundle",
                url="https://www.humblebundle.com/books/test-expired-bundle",
                machine_name="test-expired-bundle",
                end_date="2024-01-15T23:59:59+00:00",
                evaluated_at="2024-01-10T12:00:00+00:00",
                expired_at="2024-01-16T00:00:00+00:00",
                evaluation={
                    "total_items": 8,
                    "matched_count": 2,
                    "overlap_percentage": 25.0,
                    "matched_items": ["Owned Item A", "Owned Item B"],
                    "new_items": ["New Item X", "New Item Y", "New Item Z"],
                    "pricing": [
                        {
                            "tier_id": "tier1",
                            "amount": 1.0,
                            "currency": "USD",
                            "is_bta": False,
                            "header": "Pay $1 or more",
                        },
                    ],
                    "tier_breakdown": [
                        {
                            "tier_id": "tier1",
                            "amount": 1.0,
                            "currency": "USD",
                            "is_bta": False,
                            "header": "Pay $1 or more",
                            "owned": ["Owned Item A"],
                            "unowned": ["New Item X", "New Item Y"],
                        },
                    ],
                },
            )
            db.add(record)
            db.flush()
            record_id = record.id
            db.commit()
        finally:
            db.close()

        try:
            response = client.get(
                "/deals/inspect_expired",
                params={"url": "https://www.humblebundle.com/books/test-expired-bundle"},
            )

            assert response.status_code == 200
            # Verify bundle name is displayed
            assert "Test Expired Bundle" in response.text
            # Verify evaluation stats are rendered
            assert "25.0% Owned" in response.text
            assert "8" in response.text  # total_items
            # Verify tier breakdown is rendered
            assert "[x]</span> <span class=\"sr-only\">Owned:</span> Owned Item A" in response.text
            assert "[+]</span> <span class=\"sr-only\">New:</span> New Item X" in response.text
            assert "[+]</span> <span class=\"sr-only\">New:</span> New Item Y" in response.text
        finally:
            # Clean up
            db = SessionLocal()
            try:
                if record_id is not None:
                    db.query(EvaluatedBundle).filter(EvaluatedBundle.id == record_id).delete()
                db.commit()
            finally:
                db.close()

    def test_deals_inspect_expired_not_found(self, client: TestClient):
        """Verify inspect_expired returns error when bundle not found."""
        response = client.get(
            "/deals/inspect_expired",
            params={"url": "https://www.humblebundle.com/books/nonexistent-bundle"},
        )

        assert response.status_code == 200
        assert "Expired bundle not found" in response.text
