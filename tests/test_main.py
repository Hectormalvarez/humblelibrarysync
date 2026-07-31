"""
Tests for the main FastAPI application endpoints.
"""


def test_health_check(client):
    """Verify the /health endpoint returns the expected status payload."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "GUI active"}


def test_home_page_renders(client):
    """Verify the / endpoint renders the Jinja2 template successfully."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Humble Library Sync" in response.text