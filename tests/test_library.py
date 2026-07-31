"""
Tests for the library search feature endpoints.
"""

from models import Bundle, Item
from database import SessionLocal, Base, engine, reset_database


def test_library_search_endpoint(client):
    """Verify the /library/search endpoint returns a successful response."""
    response = client.get("/library/search?q=test")
    assert response.status_code == 200


def test_library_search_pagination(client):
    """Verify that limit and offset pagination work correctly."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Test Bundle")
        db.add(bundle)
        db.flush()

        for i in range(8):
            db.add(
                Item(
                    bundle_id=bundle.id,
                    title=f"Paginated Item {i}",
                    publisher="Test",
                    item_type="download",
                    available_formats=["PDF"],
                    downloads={},
                )
            )
        db.commit()

        # First page: limit=5, offset=0 → should return 5 items, has_more=True
        resp = client.get("/library/search?q=Paginated&limit=5&offset=0")
        assert resp.status_code == 200
        # Count <article class="result-row" elements specifically
        assert resp.text.count('<article class="result-row"') == 5
        assert "Paginated Item 0" in resp.text
        assert "Paginated Item 4" in resp.text
        assert "Paginated Item 5" not in resp.text

        # Second page: limit=5, offset=5 → should return 3 items, has_more=False
        resp = client.get("/library/search?q=Paginated&limit=5&offset=5")
        assert resp.status_code == 200
        assert resp.text.count('<article class="result-row"') == 3
        assert "Paginated Item 5" in resp.text
        assert "Paginated Item 7" in resp.text
    finally:
        db.close()
        # Clean up test data
        db_cleanup = SessionLocal()
        try:
            db_cleanup.query(Item).filter(Item.title.like("Paginated%")).delete()
            db_cleanup.query(Bundle).filter(Bundle.title == "Test Bundle").delete()
            db_cleanup.commit()
        finally:
            db_cleanup.close()


def test_library_search_initial_load_aggregations(client):
    """Verify that an empty search at offset=0 returns top publisher and
    bundle aggregations in the template context."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle_a = Bundle(title="Bundle A")
        bundle_b = Bundle(title="Bundle B")
        db.add_all([bundle_a, bundle_b])
        db.flush()

        for i in range(3):
            db.add(
                Item(
                    bundle_id=bundle_a.id,
                    title=f"Bundle A Item {i}",
                    publisher="Publisher One",
                    item_type="download",
                    available_formats=["PDF"],
                    downloads={},
                )
            )
        for i in range(2):
            db.add(
                Item(
                    bundle_id=bundle_b.id,
                    title=f"Bundle B Item {i}",
                    publisher="Publisher Two",
                    item_type="ebook",
                    available_formats=["EPUB"],
                    downloads={},
                )
            )
        db.commit()

        # Initial load state (empty query, offset=0) → aggregations present
        resp = client.get("/library/search")
        assert resp.status_code == 200
        assert resp.context["publishers_summary"][0] == {
            "name": "Publisher One",
            "count": 3,
        }
        assert resp.context["bundles_summary"][0] == {"name": "Bundle A", "count": 3}
        assert len(resp.context["publishers_summary"]) == 2
        assert len(resp.context["bundles_summary"]) == 2

        # Non-empty query → aggregations empty
        resp = client.get("/library/search?q=Bundle")
        assert resp.status_code == 200
        assert resp.context["publishers_summary"] == []
        assert resp.context["bundles_summary"] == []

        # offset > 0 → aggregations empty
        resp = client.get("/library/search?limit=1&offset=1")
        assert resp.status_code == 200
        assert resp.context["publishers_summary"] == []
        assert resp.context["bundles_summary"] == []
    finally:
        db.close()
        # Clean up test data
        db_cleanup = SessionLocal()
        try:
            db_cleanup.query(Item).filter(
                Item.title.like("Bundle % Item%")
            ).delete()
            db_cleanup.query(Bundle).filter(
                Bundle.title.in_(["Bundle A", "Bundle B"])
            ).delete()
            db_cleanup.commit()
        finally:
            db_cleanup.close()


def test_home_page_contains_mode_switcher(client):
    """Verify that the home page renders a .mode-switcher pill bar with
    three buttons targeting /library/search, /library/publishers, and
    /library/bundles via HTMX."""
    response = client.get("/")
    assert response.status_code == 200
    # The mode-switcher container and three pills must be present
    assert "mode-switcher" in response.text
    assert response.text.count("mode-pill") >= 3
    # Books pill → /library/search (active by default)
    assert 'hx-get="/library/search"' in response.text
    # Publishers pill → /library/publishers
    assert 'hx-get="/library/publishers"' in response.text
    # Bundles pill → /library/bundles
    assert 'hx-get="/library/bundles"' in response.text
    # All pills target #master-stream with innerHTML swap
    assert response.text.count('hx-target="#master-stream"') >= 3
    assert response.text.count('hx-swap="innerHTML"') >= 3
    # Exactly one pill carries the .active class
    assert response.text.count("mode-pill active") == 1


def test_home_page_search_uses_input_event(client):
    """Verify the home page search input uses the 'input' event for
    HTMX triggers so that deletions, cuts, pastes, and clear-button
    clicks all fire a search request."""
    response = client.get("/")
    assert response.status_code == 200
    assert 'hx-trigger="input changed delay:300ms, search"' in response.text


def test_library_overview_endpoint(client):
    """Verify the /library/overview endpoint returns HTTP 200 and passes
    aggregate library metrics (total items, publishers, bundles, and
    per-format counts) into the template context."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Overview Test Bundle")
        db.add(bundle)
        db.flush()

        for i in range(3):
            db.add(
                Item(
                    bundle_id=bundle.id,
                    title=f"Overview Item {i}",
                    publisher="Overview Press",
                    item_type="download",
                    available_formats=["PDF", "EPUB"],
                    downloads={},
                )
            )
        db.add(
            Item(
                bundle_id=bundle.id,
                title="Overview eBook",
                publisher="Another Press",
                item_type="ebook",
                available_formats=["EPUB"],
                downloads={},
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        resp = client.get("/library/overview")
        assert resp.status_code == 200
        assert resp.context["total_items"] == 4
        assert resp.context["total_publishers"] == 2
        assert resp.context["total_bundles"] == 1
        # Format counts: 3 PDFs, 4 EPUBs
        formats = {f["format"]: f["count"] for f in resp.context["format_breakdown"]}
        assert formats["PDF"] == 3
        assert formats["EPUB"] == 4
        assert "Library Overview" in resp.text
        assert "stat-card" in resp.text
        assert "format-breakdown" in resp.text
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(Item.title.like("Overview%")).delete()
            cleanup.query(Bundle).filter(
                Bundle.title == "Overview Test Bundle"
            ).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_reset_database():
    """Verify that reset_database() cleanly clears all rows across all tables."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Add some test data
        bundle = Bundle(title="Reset Test Bundle")
        db.add(bundle)
        db.flush()

        db.add(
            Item(
                bundle_id=bundle.id,
                title="Reset Test Item",
                publisher="Reset Press",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.commit()

        # Verify data exists
        assert db.query(Bundle).count() > 0
        assert db.query(Item).count() > 0
    finally:
        db.close()

    # Call reset_database()
    reset_database()

    # Verify all tables are empty
    db = SessionLocal()
    try:
        assert db.query(Bundle).count() == 0
        assert db.query(Item).count() == 0
    finally:
        db.close()

def test_get_publishers_stream(client):
    """Verify the /library/publishers endpoint returns HTTP 200 and
    renders aggregated item counts grouped by publisher."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Publishers Test Bundle")
        db.add(bundle)
        db.flush()

        for _ in range(3):
            db.add(
                Item(
                    bundle_id=bundle.id,
                    title="Publisher Row A",
                    publisher="No Starch Press",
                    item_type="download",
                    available_formats=["PDF"],
                    downloads={},
                )
            )
        for _ in range(2):
            db.add(
                Item(
                    bundle_id=bundle.id,
                    title="Publisher Row B",
                    publisher="O'Reilly Media",
                    item_type="ebook",
                    available_formats=["EPUB"],
                    downloads={},
                )
            )
        db.commit()
    finally:
        db.close()

    try:
        resp = client.get("/library/publishers")
        assert resp.status_code == 200
        publishers = resp.context["publishers"]
        names = [p["name"] for p in publishers]
        counts = {p["name"]: p["count"] for p in publishers}
        assert "No Starch Press" in names
        assert "O'Reilly Media" in names
        assert counts["No Starch Press"] == 3
        assert counts["O'Reilly Media"] == 2
        # Ordered descending by count
        assert counts[names[0]] >= counts[names[1]]
        # HTMX wiring: each row should target /library/search with the
        # publisher's name and swap into #master-stream.
        assert "category-row" in resp.text
        assert "No Starch Press" in resp.text
        assert "3 items" in resp.text
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(
                Item.title.in_(["Publisher Row A", "Publisher Row B"])
            ).delete()
            cleanup.query(Bundle).filter(
                Bundle.title == "Publishers Test Bundle"
            ).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_get_bundles_stream(client):
    """Verify the /library/bundles endpoint returns HTTP 200 and
    renders aggregated item counts grouped by bundle."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle_x = Bundle(title="Bundle X")
        bundle_y = Bundle(title="Bundle Y")
        db.add_all([bundle_x, bundle_y])
        db.flush()

        for _ in range(4):
            db.add(
                Item(
                    bundle_id=bundle_x.id,
                    title="Bundle X Item",
                    publisher="Publisher X",
                    item_type="download",
                    available_formats=["PDF"],
                    downloads={},
                )
            )
        for _ in range(1):
            db.add(
                Item(
                    bundle_id=bundle_y.id,
                    title="Bundle Y Item",
                    publisher="Publisher Y",
                    item_type="ebook",
                    available_formats=["EPUB"],
                    downloads={},
                )
            )
        db.commit()
    finally:
        db.close()

    try:
        resp = client.get("/library/bundles")
        assert resp.status_code == 200
        bundles = resp.context["bundles"]
        names = [b["name"] for b in bundles]
        counts = {b["name"]: b["count"] for b in bundles}
        assert "Bundle X" in names
        assert "Bundle Y" in names
        assert counts["Bundle X"] == 4
        assert counts["Bundle Y"] == 1
        # Ordered descending by count
        assert counts[names[0]] >= counts[names[1]]
        # HTMX wiring: each row should target /library/search with the
        # bundle's name and swap into #master-stream.
        assert "category-row" in resp.text
        assert "Bundle X" in resp.text
        assert "4 items" in resp.text
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(
                Item.title.in_(["Bundle X Item", "Bundle Y Item"])
            ).delete()
            cleanup.query(Bundle).filter(
                Bundle.title.in_(["Bundle X", "Bundle Y"])
            ).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_get_item_inspector_detail(client):
    """Verify the /library/items/{item_id} endpoint returns HTTP 200
    and renders the full item detail partial, including the title,
    publisher, bundle, item type, the available format badges, and
    structured download cards with direct action buttons.
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Inspector Test Bundle")
        db.add(bundle)
        db.flush()

        # Downloads are now structured objects with url and human_size keys
        item = Item(
            bundle_id=bundle.id,
            title="Inspector Test Book",
            publisher="Inspector Press",
            item_type="ebook",
            available_formats=["PDF", "EPUB"],
            downloads={
                "pdf": {"url": "https://example.com/test.pdf", "human_size": "12.3 MB"},
                "epub": {"url": "https://example.com/test.epub", "human_size": "4.5 MB"},
            },
        )
        db.add(item)
        db.commit()
        item_id = item.id
        bundle_title = bundle.title
    finally:
        db.close()

    try:
        resp = client.get(f"/library/items/{item_id}")
        assert resp.status_code == 200
        # Metadata fields rendered into the partial
        assert "Inspector Test Book" in resp.text
        assert "Inspector Press" in resp.text
        assert bundle_title in resp.text
        assert "ebook" in resp.text
        # Format availability badges
        assert "PDF" in resp.text
        assert "EPUB" in resp.text
        assert "badge-list" in resp.text
        # Drawer close button wiring
        assert "drawer-close" in resp.text
        assert 'hx-get="/library/overview"' in resp.text
        assert 'hx-target="#inspector-drawer"' in resp.text
        # Structured download cards with direct action buttons
        assert "download-card" in resp.text
        assert "download-btn" in resp.text
        # URLs are rendered in href attributes, not as raw JSON
        assert 'href="https://example.com/test.pdf"' in resp.text
        assert 'href="https://example.com/test.epub"' in resp.text
        # Human-readable file sizes are displayed
        assert "12.3 MB" in resp.text
        assert "4.5 MB" in resp.text
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(
                Item.title == "Inspector Test Book"
            ).delete()
            cleanup.query(Bundle).filter(
                Bundle.title == "Inspector Test Bundle"
            ).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_library_search_exact_publisher_and_bundle_filter(client):
    """Verify that filtering by publisher or bundle_id returns only exact
    matches for those fields, demonstrating strict equality filter behavior."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle_a = Bundle(title="Filter Bundle A")
        bundle_b = Bundle(title="Filter Bundle B")
        db.add_all([bundle_a, bundle_b])
        db.flush()

        # Items with different publishers and bundles
        db.add(
            Item(
                bundle_id=bundle_a.id,
                title="Filter Test Item 1",
                publisher="Publisher Alpha",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.add(
            Item(
                bundle_id=bundle_a.id,
                title="Filter Test Item 2",
                publisher="Publisher Beta",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.add(
            Item(
                bundle_id=bundle_b.id,
                title="Filter Test Item 3",
                publisher="Publisher Alpha",
                item_type="ebook",
                available_formats=["EPUB"],
                downloads={},
            )
        )
        db.commit()

        # Filter by publisher only - should return items from both bundles
        # but only with the exact publisher match
        resp = client.get("/library/search?publisher=Publisher Alpha")
        assert resp.status_code == 200
        assert resp.text.count('<article class="result-row"') == 2
        assert "Filter Test Item 1" in resp.text
        assert "Filter Test Item 3" in resp.text
        assert "Filter Test Item 2" not in resp.text

        # Filter by bundle_id only - should return items only from that bundle
        resp = client.get(f"/library/search?bundle_id={bundle_a.id}")
        assert resp.status_code == 200
        assert resp.text.count('<article class="result-row"') == 2
        assert "Filter Test Item 1" in resp.text
        assert "Filter Test Item 2" in resp.text
        assert "Filter Test Item 3" not in resp.text

        # Filter by both publisher and bundle_id - should return only items
        # matching both criteria
        resp = client.get(
            f"/library/search?publisher=Publisher Alpha&bundle_id={bundle_a.id}"
        )
        assert resp.status_code == 200
        assert resp.text.count('<article class="result-row"') == 1
        assert "Filter Test Item 1" in resp.text

        # Filter by publisher with no matches
        resp = client.get("/library/search?publisher=Nonexistent Publisher")
        assert resp.status_code == 200
        assert resp.text.count('<article class="result-row"') == 0

        # Combine q search with publisher filter
        resp = client.get("/library/search?q=Item 1&publisher=Publisher Alpha")
        assert resp.status_code == 200
        assert resp.text.count('<article class="result-row"') == 1
        assert "Filter Test Item 1" in resp.text
    finally:
        db.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(
                Item.title.in_([
                    "Filter Test Item 1",
                    "Filter Test Item 2",
                    "Filter Test Item 3",
                ])
            ).delete()
            cleanup.query(Bundle).filter(
                Bundle.title.in_(["Filter Bundle A", "Filter Bundle B"])
            ).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_search_results_contain_inspector_htmx_triggers(client):
    """Verify that search result rows contain HTMX attributes that load
    item details into #inspector-drawer on click.  Each .result-row (or
    inner .result-row-click for infinite-scroll rows) should have
    hx-get targeting /library/items/{id} and hx-target="#inspector-drawer".
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="HTMX Trigger Bundle")
        db.add(bundle)
        db.flush()

        db.add(
            Item(
                bundle_id=bundle.id,
                title="HTMX Trigger Item",
                publisher="HTMX Press",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.commit()

        resp = client.get("/library/search?q=HTMX")
        assert resp.status_code == 200
        # The row must contain an hx-get pointing to the item detail endpoint
        assert 'hx-get="/library/items/' in resp.text
        # The HTMX target must be the inspector drawer
        assert 'hx-target="#inspector-drawer"' in resp.text
        # The swap method should be innerHTML
        assert 'hx-swap="innerHTML"' in resp.text
    finally:
        db.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(Item.title == "HTMX Trigger Item").delete()
            cleanup.query(Bundle).filter(Bundle.title == "HTMX Trigger Bundle").delete()
            cleanup.commit()
        finally:
            cleanup.close()
