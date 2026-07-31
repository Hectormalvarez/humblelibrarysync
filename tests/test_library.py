"""
Tests for the library search feature endpoints.
"""


def test_library_page_renders(client):
    """Verify the /library endpoint renders the Library Search template."""
    response = client.get("/library")
    assert response.status_code == 200
    assert b"Library Search" in response.text.encode()


def test_library_search_endpoint(client):
    """Verify the /library/search endpoint returns a successful response."""
    response = client.get("/library/search?q=test")
    assert response.status_code == 200


def test_home_page_search_uses_input_event(client):
    """Verify the home page search input uses the 'input' event for
    HTMX triggers so that deletions, cuts, pastes, and clear-button
    clicks all fire a search request."""
    response = client.get("/")
    assert response.status_code == 200
    assert 'hx-trigger="input changed delay:300ms"' in response.text
