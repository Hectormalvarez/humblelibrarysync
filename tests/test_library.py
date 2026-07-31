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


def test_home_page_search_uses_input_event(client):
    """Verify the home page search input uses the 'input' event for
    HTMX triggers so that deletions, cuts, pastes, and clear-button
    clicks all fire a search request."""
    response = client.get("/")
    assert response.status_code == 200
    assert 'hx-trigger="input changed delay:300ms"' in response.text
