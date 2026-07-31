"""
Test configuration and shared fixtures.
"""

from fastapi.testclient import TestClient
from app.main import app
import pytest


@pytest.fixture
def client():
    """
    Fixture that provides a reusable test client for all endpoint tests.

    Yields a TestClient instance bound to the FastAPI application, allowing
    test functions to simulate HTTP requests without running a live server.
    """
    with TestClient(app) as test_client:
        yield test_client