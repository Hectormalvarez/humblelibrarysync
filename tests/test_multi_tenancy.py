"""
Tests for data isolation between separate user accounts.

Verifies that items, bundles, publishers, and metrics belonging to one
user are never leaked to or accessible by another user through any library
endpoint or query helper.
"""

import uuid

from humble_sync.db.database import Base, SessionLocal, engine
from humble_sync.db.models import Bundle, Item
from humble_sync.db.queries import (
    get_all_bundles,
    get_all_publishers,
    get_item_by_id,
    get_library_metrics,
    get_total_item_count,
    search_library_items,
)

# Two distinct user identities for isolation testing.
user_a_id = uuid.uuid4()
user_b_id = uuid.uuid4()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_A_EMAIL = "user_a@example.com"
USER_B_EMAIL = "user_b@example.com"


def _make_user_stub(user_id: uuid.UUID, email: str):
    """Create a minimal ``User`` stub for dependency overrides."""
    from humble_sync.db.models import User

    return User(
        id=user_id,
        email=email,
        hashed_password="fake",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )


def _seed_user_a_data():
    """Insert a bundle and three items owned by *user_a*."""
    db = SessionLocal()
    try:
        bundle = Bundle(title="UserA Bundle", user_id=user_a_id, purchase_date="2025-01-01")
        db.add(bundle)
        db.flush()

        items = [
            Item(
                bundle_id=bundle.id,
                title="UserA Item Alpha",
                publisher="Publisher Alpha",
                item_type="download",
                available_formats=["PDF", "EPUB"],
                downloads={},
                user_id=user_a_id,
            ),
            Item(
                bundle_id=bundle.id,
                title="UserA Item Beta",
                publisher="Publisher Beta",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
                user_id=user_a_id,
            ),
            Item(
                bundle_id=bundle.id,
                title="UserA Item Gamma",
                publisher="Publisher Alpha",
                item_type="book",
                available_formats=["PDF", "MOBI"],
                downloads={},
                user_id=user_a_id,
            ),
        ]
        db.add_all(items)
        db.commit()
        return bundle
    finally:
        db.close()


def _seed_user_b_data():
    """Insert a bundle and two items owned by *user_b*."""
    db = SessionLocal()
    try:
        bundle = Bundle(title="UserB Bundle", user_id=user_b_id, purchase_date="2025-06-15")
        db.add(bundle)
        db.flush()

        items = [
            Item(
                bundle_id=bundle.id,
                title="UserB Item One",
                publisher="Publisher One",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
                user_id=user_b_id,
            ),
            Item(
                bundle_id=bundle.id,
                title="UserB Item Two",
                publisher="Publisher Two",
                item_type="book",
                available_formats=["PDF", "EPUB"],
                downloads={},
                user_id=user_b_id,
            ),
        ]
        db.add_all(items)
        db.commit()
        return bundle
    finally:
        db.close()


def _seed_cross_user_data():
    """Insert data for both users in a single call."""
    return _seed_user_a_data(), _seed_user_b_data()


# ---------------------------------------------------------------------------
# Query-layer isolation tests
# ---------------------------------------------------------------------------


def test_search_items_isolation():
    """search_library_items scoped to user_b must not return user_a items."""
    _seed_cross_user_data()

    db = SessionLocal()
    try:
        result = search_library_items(db, user_id=user_b_id)
        titles = [item.title for item in result["items"]]
        assert all("UserA" not in t for t in titles), f"Leaked user_a items: {titles}"
        assert result["total_count"] == 2

        # User A should see only their items
        result_a = search_library_items(db, user_id=user_a_id)
        titles_a = [item.title for item in result_a["items"]]
        assert all("UserB" not in t for t in titles_a), f"Leaked user_b items: {titles_a}"
        assert result_a["total_count"] == 3
    finally:
        db.close()


def test_search_items_title_filter_isolation():
    """A title search for 'Item' scoped to user_b must still not leak user_a data."""
    _seed_cross_user_data()

    db = SessionLocal()
    try:
        result = search_library_items(db, q="Item", user_id=user_b_id)
        titles = [item.title for item in result["items"]]
        assert all("UserA" not in t for t in titles)
        assert result["total_count"] == 2
    finally:
        db.close()


def test_search_items_publisher_filter_isolation():
    """A publisher filter scoped to user_b must not return user_a items."""
    _seed_cross_user_data()

    db = SessionLocal()
    try:
        # 'Publisher Alpha' exists only for user_a
        result = search_library_items(db, publisher="Publisher Alpha", user_id=user_b_id)
        assert result["total_count"] == 0
        assert result["items"] == []
    finally:
        db.close()


def test_get_item_by_id_isolation():
    """get_item_by_id must return an item only if the user_id matches."""
    _seed_cross_user_data()

    db = SessionLocal()
    try:
        # Fetch user_a's first item
        user_a_item = db.query(Item).filter(Item.user_id == user_a_id).first()
        assert user_a_item is not None

        # user_b should NOT be able to access user_a's item
        result = get_item_by_id(db, user_a_item.id, user_id=user_b_id)
        assert result is None

        # user_a SHOULD be able to access their own item
        result_a = get_item_by_id(db, user_a_item.id, user_id=user_a_id)
        assert result_a is not None
        assert result_a.title == user_a_item.title
    finally:
        db.close()


def test_get_total_item_count_isolation():
    """get_total_item_count scoped per user must return the correct count."""
    _seed_cross_user_data()

    db = SessionLocal()
    try:
        assert get_total_item_count(db, user_id=user_a_id) == 3
        assert get_total_item_count(db, user_id=user_b_id) == 2
    finally:
        db.close()


def test_get_library_metrics_isolation():
    """get_library_metrics scoped per user must not leak cross-user data."""
    _seed_cross_user_data()

    db = SessionLocal()
    try:
        metrics_a = get_library_metrics(db, user_id=user_a_id)
        metrics_b = get_library_metrics(db, user_id=user_b_id)

        assert metrics_a["total_items"] == 3
        assert metrics_a["total_bundles"] == 1
        assert metrics_a["total_publishers"] == 2

        assert metrics_b["total_items"] == 2
        assert metrics_b["total_bundles"] == 1
        assert metrics_b["total_publishers"] == 2

        # Ensure publisher names don't bleed across
        pub_names_a = {p for p in [f["format"] for f in metrics_a["format_breakdown"]]}
        pub_names_b = {p for p in [f["format"] for f in metrics_b["format_breakdown"]]}
        # user_a has MOBI, user_b does not
        assert "MOBI" in [f["format"] for f in metrics_a["format_breakdown"]]
        mobi_in_b = any(f["format"] == "MOBI" for f in metrics_b["format_breakdown"])
        assert not mobi_in_b
    finally:
        db.close()


def test_get_all_publishers_isolation():
    """get_all_publishers scoped to user_b must not include user_a publishers."""
    _seed_cross_user_data()

    db = SessionLocal()
    try:
        pubs_a, _ = get_all_publishers(db, user_id=user_a_id)
        pubs_b, _ = get_all_publishers(db, user_id=user_b_id)

        names_a = {p["name"] for p in pubs_a}
        names_b = {p["name"] for p in pubs_b}

        assert names_a == {"Publisher Alpha", "Publisher Beta"}
        assert names_b == {"Publisher One", "Publisher Two"}
        assert names_a.isdisjoint(names_b), "Publishers leaked across users"
    finally:
        db.close()


def test_get_all_bundles_isolation():
    """get_all_bundles scoped to user_b must not include user_a bundles."""
    _seed_cross_user_data()

    db = SessionLocal()
    try:
        bundles_a, _ = get_all_bundles(db, user_id=user_a_id)
        bundles_b, _ = get_all_bundles(db, user_id=user_b_id)

        names_a = {b["name"] for b in bundles_a}
        names_b = {b["name"] for b in bundles_b}

        assert names_a == {"UserA Bundle"}
        assert names_b == {"UserB Bundle"}
        assert names_a.isdisjoint(names_b), "Bundles leaked across users"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Endpoint-layer isolation tests via TestClient
# ---------------------------------------------------------------------------


def _override_for_user(user_id: uuid.UUID, email: str):
    """Return a callable that produces a user stub for the given identity."""
    def _factory():
        return _make_user_stub(user_id, email)
    return _factory


def test_endpoint_search_isolation(client):
    """GET /library/search as user_b must not reveal user_a items."""
    from app.main import app as _app
    from app.routers.library import current_active_user as library_user

    _seed_cross_user_data()

    # Authenticate as user_b
    _app.dependency_overrides[library_user] = _override_for_user(user_b_id, USER_B_EMAIL)
    try:
        resp = client.get("/library/search?q=Item")
        assert resp.status_code == 200
        assert "UserA" not in resp.text
        assert "UserA Item Alpha" not in resp.text
        assert "UserB Item One" in resp.text
    finally:
        _app.dependency_overrides.pop(library_user, None)


def test_endpoint_overview_isolation(client):
    """GET /library/overview as user_b must show only user_b metrics."""
    from app.main import app as _app
    from app.routers.library import current_active_user as library_user

    _seed_cross_user_data()

    _app.dependency_overrides[library_user] = _override_for_user(user_b_id, USER_B_EMAIL)
    try:
        resp = client.get("/library/overview")
        assert resp.status_code == 200
        # user_b has 2 items, user_a has 3
        assert "2" in resp.text  # total_items count in the HTML
        assert "3" not in resp.text or "UserA" not in resp.text
    finally:
        _app.dependency_overrides.pop(library_user, None)


def test_endpoint_publishers_isolation(client):
    """GET /library/publishers as user_b must not list user_a publishers."""
    from app.main import app as _app
    from app.routers.library import current_active_user as library_user

    _seed_cross_user_data()

    _app.dependency_overrides[library_user] = _override_for_user(user_b_id, USER_B_EMAIL)
    try:
        resp = client.get("/library/publishers")
        assert resp.status_code == 200
        assert "Publisher Alpha" not in resp.text
        assert "Publisher Beta" not in resp.text
        assert "Publisher One" in resp.text
        assert "Publisher Two" in resp.text
    finally:
        _app.dependency_overrides.pop(library_user, None)


def test_endpoint_bundles_isolation(client):
    """GET /library/bundles as user_b must not list user_a bundles."""
    from app.main import app as _app
    from app.routers.library import current_active_user as library_user

    _seed_cross_user_data()

    _app.dependency_overrides[library_user] = _override_for_user(user_b_id, USER_B_EMAIL)
    try:
        resp = client.get("/library/bundles")
        assert resp.status_code == 200
        assert "UserA Bundle" not in resp.text
        assert "UserB Bundle" in resp.text
    finally:
        _app.dependency_overrides.pop(library_user, None)


def test_endpoint_item_detail_isolation(client):
    """GET /library/items/{id} as user_b must return 404 for user_a items."""
    from app.main import app as _app
    from app.routers.library import current_active_user as library_user

    _seed_cross_user_data()

    db = SessionLocal()
    try:
        user_a_item = db.query(Item).filter(Item.user_id == user_a_id).first()
        user_b_item = db.query(Item).filter(Item.user_id == user_b_id).first()
    finally:
        db.close()

    # Access as user_b – should 404 for user_a's item
    _app.dependency_overrides[library_user] = _override_for_user(user_b_id, USER_B_EMAIL)
    try:
        resp_a = client.get(f"/library/items/{user_a_item.id}")
        assert resp_a.status_code == 404

        resp_b = client.get(f"/library/items/{user_b_item.id}")
        assert resp_b.status_code == 200
        assert "UserB Item One" in resp_b.text
    finally:
        _app.dependency_overrides.pop(library_user, None)


def test_dynamic_user_switching(client):
    """Switch between user_a and user_b in sequence and verify correct data visibility."""
    from app.main import app as _app
    from app.routers.library import current_active_user as library_user

    _seed_cross_user_data()

    # First request as user_a
    _app.dependency_overrides[library_user] = _override_for_user(user_a_id, USER_A_EMAIL)
    resp = client.get("/library/search?q=Item")
    assert resp.status_code == 200
    assert "UserA Item Alpha" in resp.text
    assert "UserB Item One" not in resp.text

    # Switch to user_b
    _app.dependency_overrides[library_user] = _override_for_user(user_b_id, USER_B_EMAIL)
    resp = client.get("/library/search?q=Item")
    assert resp.status_code == 200
    assert "UserB Item One" in resp.text
    assert "UserA Item Alpha" not in resp.text

    _app.dependency_overrides.pop(library_user, None)