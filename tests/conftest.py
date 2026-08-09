"""
Test configuration and shared fixtures.
"""

import os
import uuid

# Isolate the test suite to a dedicated database so real library data is
# never read or modified during tests. This must be set before importing
# app.main (which imports database.py and binds the engine).
os.environ["DATABASE_URL"] = "sqlite:///./test_humble_library.db"

from fastapi import Depends
from fastapi.testclient import TestClient
from app.main import app
from humble_sync.db.database import Base, engine
from humble_sync.db.models import User
import pytest

# Fixed UUID used as the authenticated user identity in all tests so that
# test data with ``user_id=TEST_USER_ID`` is visible to the scoped queries.
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _override_current_user():
    """Return a stub ``User`` instance used to satisfy auth dependencies in
    tests without needing a real authentication flow."""
    user = User(
        id=TEST_USER_ID,
        email="test@example.com",
        hashed_password="fake",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    return user


@pytest.fixture(scope="function", autouse=True)
def clean_test_database():
    """Drop and recreate the schema before every test function so each test
    starts from a clean slate, preventing data pollution between tests."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Override the auth dependency so all endpoints accept a stub user.
    from app.routers.dashboard import current_active_user as dashboard_user
    from app.routers.library import current_active_user as library_user
    from app.routers.deals import current_active_user as deals_user
    from app.routers.sync import current_active_user as sync_user
    from app.routers.booklog import current_active_user as booklog_user
    app.dependency_overrides[dashboard_user] = _override_current_user
    app.dependency_overrides[library_user] = _override_current_user
    app.dependency_overrides[deals_user] = _override_current_user
    app.dependency_overrides[sync_user] = _override_current_user
    app.dependency_overrides[booklog_user] = _override_current_user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """
    Fixture that provides a reusable test client for all endpoint tests.

    Yields a TestClient instance bound to the FastAPI application, allowing
    test functions to simulate HTTP requests without running a live server.
    """
    with TestClient(app) as test_client:
        yield test_client
