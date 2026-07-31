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
