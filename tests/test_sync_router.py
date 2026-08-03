"""
Tests for the sync router endpoints.
"""

from unittest.mock import patch, AsyncMock

import pytest


def test_sync_modal_loads(client):
    """Verify the sync modal endpoint returns the form HTML."""
    response = client.get("/library/sync/modal")
    assert response.status_code == 200
    assert "sync-modal-overlay" in response.text
    assert "session_cookie" in response.text
    assert "Sync Now" in response.text


@patch("app.routers.sync.sync_account_library", new_callable=AsyncMock)
def test_sync_success(mock_sync, client):
    """Verify successful sync returns item/bundle counts."""
    mock_sync.return_value = {
        "metadata": {"total_items": 42},
        "items": [
            {"title": "Book 1", "bundle": "Bundle A"},
            {"title": "Book 2", "bundle": "Bundle A"},
            {"title": "Book 3", "bundle": "Bundle B"},
        ],
    }

    response = client.post(
        "/library/sync",
        data={"session_cookie": "test_cookie_value"},
    )

    assert response.status_code == 200
    assert "42" in response.text  # total_items
    assert "2" in response.text  # unique bundles (A and B)
    assert "synced successfully" in response.text
    mock_sync.assert_called_once()


@patch("app.routers.sync.sync_account_library", new_callable=AsyncMock)
def test_sync_error(mock_sync, client):
    """Verify sync failure returns error message."""
    mock_sync.side_effect = Exception("API connection failed")

    response = client.post(
        "/library/sync",
        data={"session_cookie": "test_cookie_value"},
    )

    assert response.status_code == 200
    assert "Sync failed" in response.text
    assert "API connection failed" in response.text


def test_sync_empty_cookie(client):
    """Verify empty session cookie returns error."""
    response = client.post(
        "/library/sync",
        data={"session_cookie": ""},
    )

    assert response.status_code == 200
    assert "Session cookie is required" in response.text


def test_sync_whitespace_cookie(client):
    """Verify whitespace-only session cookie returns error."""
    response = client.post(
        "/library/sync",
        data={"session_cookie": "   "},
    )

    assert response.status_code == 200
    assert "Session cookie is required" in response.text