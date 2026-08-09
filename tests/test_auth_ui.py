"""
Integration tests for the frontend auth UI: redirection on 401 and
login / register page rendering.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from humble_sync.auth import fastapi_users


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# The auth dependency callable used by the dashboard router to resolve
# the current user.  We need a reference to remove / restore overrides.
_dashboard_user_dep = None


def _get_dashboard_user_dep():
    """Lazily resolve the dashboard's current_active_user dependency."""
    global _dashboard_user_dep
    if _dashboard_user_dep is None:
        from app.routers.dashboard import current_active_user
        _dashboard_user_dep = current_active_user
    return _dashboard_user_dep


@pytest.fixture()
def unauthenticated_client():
    """Yield a TestClient with auth overrides removed so that endpoints
    behave as they would for an unauthenticated visitor."""
    dep = _get_dashboard_user_dep()
    # Save the current override (set by the autouse conftest fixture)
    saved = app.dependency_overrides.get(dep)
    # Remove the override so the real auth check runs
    app.dependency_overrides.pop(dep, None)
    with TestClient(app, follow_redirects=False) as c:
        yield c
    # Restore the override for any subsequent tests
    if saved is not None:
        app.dependency_overrides[dep] = saved


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUnauthenticatedRedirection:
    """Browser visits to protected pages should redirect to /login when
    the Accept header indicates an HTML response is expected."""

    def test_root_redirects_to_login(self, unauthenticated_client: TestClient):
        resp = unauthenticated_client.get(
            "/",
            headers={"Accept": "text/html"},
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

    def test_root_returns_json_401_for_api_clients(
        self, unauthenticated_client: TestClient
    ):
        resp = unauthenticated_client.get(
            "/",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Unauthorized"


class TestLoginPage:
    """The login page should render successfully for unauthenticated
    visitors."""

    def test_login_returns_200(self, client: TestClient):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "Sign In" in resp.text

    def test_login_contains_form_elements(self, client: TestClient):
        resp = client.get("/login")
        assert 'id="login-form"' in resp.text
        assert 'id="login-email"' in resp.text
        assert 'id="login-password"' in resp.text
        assert "/auth/jwt/login" in resp.text


class TestRegisterPage:
    """The register page should render successfully for unauthenticated
    visitors."""

    def test_register_returns_200(self, client: TestClient):
        resp = client.get("/register")
        assert resp.status_code == 200
        assert "Create Account" in resp.text

    def test_register_contains_form_elements(self, client: TestClient):
        resp = client.get("/register")
        assert 'id="register-form"' in resp.text
        assert 'id="reg-email"' in resp.text
        assert 'id="reg-password"' in resp.text
        assert 'id="reg-confirm"' in resp.text
        assert "/auth/register" in resp.text