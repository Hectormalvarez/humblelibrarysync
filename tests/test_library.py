"""
Tests for the library search feature endpoints.
"""

from models import Bundle, Item
from database import SessionLocal, Base, engine


def test_library_search_endpoint(client):
    """Verify the /library/search endpoint returns a successful response."""
    response = client.get("/library/search?q=test")
    assert response.status_code == 200


def test_library_search_pagination(client):
    """Verify that limit and offset pagination work correctly."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Test Bundle")
        db.add(bundle)
        db.flush()

        for i in range(8):
            db.add(
                Item(
                    bundle_id=bundle.id,
                    title=f"Paginated Item {i}",
                    publisher="Test",
                    item_type="download",
                    available_formats=["PDF"],
                    downloads={},
                )
            )
        db.commit()

        # First page: limit=5, offset=0 → should return 5 items, has_more=True
        resp = client.get("/library/search?q=Paginated&limit=5&offset=0")
        assert resp.status_code == 200
        assert resp.text.count("result-row") == 5
        assert "Paginated Item 0" in resp.text
        assert "Paginated Item 4" in resp.text
        assert "Paginated Item 5" not in resp.text

        # Second page: limit=5, offset=5 → should return 3 items, has_more=False
        resp = client.get("/library/search?q=Paginated&limit=5&offset=5")
        assert resp.status_code == 200
        assert resp.text.count("result-row") == 3
        assert "Paginated Item 5" in resp.text
        assert "Paginated Item 7" in resp.text
    finally:
        db.close()
        # Clean up test data
        db_cleanup = SessionLocal()
        try:
            db_cleanup.query(Item).filter(Item.title.like("Paginated%")).delete()
            db_cleanup.query(Bundle).filter(Bundle.title == "Test Bundle").delete()
            db_cleanup.commit()
        finally:
            db_cleanup.close()


def test_library_search_initial_load_aggregations(client):
    """Verify that an empty search at offset=0 returns top publisher and
    bundle aggregations in the template context."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle_a = Bundle(title="Bundle A")
        bundle_b = Bundle(title="Bundle B")
        db.add_all([bundle_a, bundle_b])
        db.flush()

        for i in range(3):
            db.add(
                Item(
                    bundle_id=bundle_a.id,
                    title=f"Bundle A Item {i}",
                    publisher="Publisher One",
                    item_type="download",
                    available_formats=["PDF"],
                    downloads={},
                )
            )
        for i in range(2):
            db.add(
                Item(
                    bundle_id=bundle_b.id,
                    title=f"Bundle B Item {i}",
                    publisher="Publisher Two",
                    item_type="ebook",
                    available_formats=["EPUB"],
                    downloads={},
                )
            )
        db.commit()

        # Initial load state (empty query, offset=0) → aggregations present
        resp = client.get("/library/search")
        assert resp.status_code == 200
        assert resp.context["publishers_summary"][0] == {
            "name": "Publisher One",
            "count": 3,
        }
        assert resp.context["bundles_summary"][0] == {"name": "Bundle A", "count": 3}
        assert len(resp.context["publishers_summary"]) == 2
        assert len(resp.context["bundles_summary"]) == 2

        # Non-empty query → aggregations empty
        resp = client.get("/library/search?q=Bundle")
        assert resp.status_code == 200
        assert resp.context["publishers_summary"] == []
        assert resp.context["bundles_summary"] == []

        # offset > 0 → aggregations empty
        resp = client.get("/library/search?limit=1&offset=1")
        assert resp.status_code == 200
        assert resp.context["publishers_summary"] == []
        assert resp.context["bundles_summary"] == []
    finally:
        db.close()
        # Clean up test data
        db_cleanup = SessionLocal()
        try:
            db_cleanup.query(Item).filter(
                Item.title.like("Bundle % Item%")
            ).delete()
            db_cleanup.query(Bundle).filter(
                Bundle.title.in_(["Bundle A", "Bundle B"])
            ).delete()
            db_cleanup.commit()
        finally:
            db_cleanup.close()


def test_home_page_contains_mode_switcher(client):
    """Verify that the home page renders a .mode-switcher pill bar with
    three buttons targeting /library/search, /library/publishers, and
    /library/bundles via HTMX."""
    response = client.get("/")
    assert response.status_code == 200
    # The mode-switcher container and three pills must be present
    assert "mode-switcher" in response.text
    assert response.text.count("mode-pill") >= 3
    # Books pill → /library/search (active by default)
    assert 'hx-get="/library/search"' in response.text
    # Publishers pill → /library/publishers
    assert 'hx-get="/library/publishers"' in response.text
    # Bundles pill → /library/bundles
    assert 'hx-get="/library/bundles"' in response.text
    # All pills target #master-stream with innerHTML swap
    assert response.text.count('hx-target="#master-stream"') >= 3
    assert response.text.count('hx-swap="innerHTML"') >= 3
    # Exactly one pill carries the .active class
    assert response.text.count("mode-pill active") == 1


def test_home_page_search_uses_input_event(client):
    """Verify the home page search input uses the 'input' event for
    HTMX triggers so that deletions, cuts, pastes, and clear-button
    clicks all fire a search request."""
    response = client.get("/")
    assert response.status_code == 200
    assert 'hx-trigger="input changed delay:300ms"' in response.text
