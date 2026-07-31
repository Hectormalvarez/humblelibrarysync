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


@pytest.fixture(scope="session", autouse=True)
def clean_test_database():
    """Remove the test database file before the session starts so each run
    begins from a clean slate, then create the schema."""
    db_path = os.path.abspath("test_humble_library.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    Base.metadata.create_all(bind=engine)
    yield
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def client():
    """
    Fixture that provides a reusable test client for all endpoint tests.

    Yields a TestClient instance bound to the FastAPI application, allowing
    test functions to simulate HTTP requests without running a live server.
    """
    with TestClient(app) as test_client:
        yield test_client