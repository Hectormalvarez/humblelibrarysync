"""
Test configuration and shared fixtures.
"""

import os

# Isolate the test suite to a dedicated database so real library data is
# never read or modified during tests. This must be set before importing
# app.main (which imports database.py and binds the engine).
os.environ["DATABASE_URL"] = "sqlite:///./test_humble_library.db"

from fastapi.testclient import TestClient
from app.main import app
from database import Base, engine
import pytest


@pytest.fixture(scope="function", autouse=True)
def clean_test_database():
    """Drop and recreate the schema before every test function so each test
    starts from a clean slate, preventing data pollution between tests."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    """
    Fixture that provides a reusable test client for all endpoint tests.

    Yields a TestClient instance bound to the FastAPI application, allowing
    test functions to simulate HTTP requests without running a live server.
    """
    with TestClient(app) as test_client:
        yield test_client