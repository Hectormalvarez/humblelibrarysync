"""
Tests for the library search feature endpoints.
"""

from app.routers.library import get_sort_key
from humble_sync.db.models import Bundle, Item
from humble_sync.db.database import SessionLocal, Base, engine, reset_database


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

        # offset > 0 → returns item_rows partial (no aggregations in context)
        resp = client.get("/library/search?limit=1&offset=1")
        assert resp.status_code == 200
        # The item_rows partial does not include aggregation context keys
        assert "publishers_summary" not in resp.context or resp.context.get("publishers_summary") is None
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


def test_search_results_render_active_filter_badge(client):
    """Verify that filtering by publisher renders a clearable filter pill
    at the top of the search results showing the active filter value."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Filter Badge Bundle")
        db.add(bundle)
        db.flush()

        db.add(
            Item(
                bundle_id=bundle.id,
                title="Filter Badge Item",
                publisher="Filter Badge Publisher",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.commit()

        # Filter by publisher - should render the filter pill
        resp = client.get("/library/search?publisher=Filter+Badge+Publisher")
        assert resp.status_code == 200
        assert "filter-bar" in resp.text
        assert "filter-pill" in resp.text
        assert "Filtered by: Filter Badge Publisher" in resp.text
        assert "filter-clear-btn" in resp.text
        # Clear button should target /library/search to reset the filter
        assert 'hx-get="/library/search"' in resp.text

        # Filter by bundle_id - should render the filter pill with bundle title
        resp_bundle = client.get(f"/library/search?bundle_id={bundle.id}")
        assert resp_bundle.status_code == 200
        assert "filter-bar" in resp_bundle.text
        assert "Filtered by: Filter Badge Bundle" in resp_bundle.text

        # No filter - should NOT render the filter bar
        resp_no_filter = client.get("/library/search")
        assert resp_no_filter.status_code == 200
        assert "filter-bar" not in resp_no_filter.text
    finally:
        db.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(Item.title == "Filter Badge Item").delete()
            cleanup.query(Bundle).filter(Bundle.title == "Filter Badge Bundle").delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_category_row_htmx_drilldown_attributes(client):
    """Verify that publisher and bundle list partials contain the expected
    HTMX drilldown attributes on each .category-row, targeting /library/search
    with the appropriate filter parameter and swapping into #master-stream."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Drilldown Test Bundle")
        db.add(bundle)
        db.flush()

        db.add(
            Item(
                bundle_id=bundle.id,
                title="Drilldown Test Item",
                publisher="Drilldown Publisher",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.commit()

        # Test publisher list partial
        resp_publishers = client.get("/library/publishers")
        assert resp_publishers.status_code == 200
        assert 'hx-get="/library/search?publisher=Drilldown+Publisher"' in resp_publishers.text or \
               'hx-get="/library/search?publisher=Drilldown%20Publisher"' in resp_publishers.text
        assert 'hx-target="#master-stream"' in resp_publishers.text
        assert 'hx-swap="innerHTML"' in resp_publishers.text

        # Test bundle list partial
        resp_bundles = client.get("/library/bundles")
        assert resp_bundles.status_code == 200
        assert f'hx-get="/library/search?bundle_id={bundle.id}"' in resp_bundles.text
        assert 'hx-target="#master-stream"' in resp_bundles.text
        assert 'hx-swap="innerHTML"' in resp_bundles.text
    finally:
        db.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(Item.title == "Drilldown Test Item").delete()
            cleanup.query(Bundle).filter(Bundle.title == "Drilldown Test Bundle").delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_search_pagination_preserves_publisher_filter(client):
    """Verify that the infinite-scroll trigger on the last page of results
    includes the active publisher filter parameter so that subsequent pages
    maintain the filter."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Pagination Filter Bundle")
        db.add(bundle)
        db.flush()

        for i in range(6):
            db.add(
                Item(
                    bundle_id=bundle.id,
                    title=f"Pagination Filter Item {i}",
                    publisher="Pagination Filter Publisher",
                    item_type="download",
                    available_formats=["PDF"],
                    downloads={},
                )
            )
        db.commit()

        # Request first page with publisher filter (limit=3 so has_more=True)
        resp = client.get(
            "/library/search?publisher=Pagination+Filter+Publisher&limit=3&offset=0"
        )
        assert resp.status_code == 200
        # The infinite-scroll hx-get on the last row must include the publisher param
        # Jinja2 renders the value without URL encoding, so spaces remain as spaces
        assert "publisher=Pagination Filter Publisher" in resp.text
        # bundle_id should NOT be present when no bundle filter is active
        assert "bundle_id" not in resp.text
        # Verify has_more triggered the scroll trigger article
        assert resp.text.count('<article class="result-row"') == 3

        # Request second page – should still have publisher filter in scroll trigger
        resp2 = client.get(
            "/library/search?publisher=Pagination+Filter+Publisher&limit=3&offset=3"
        )
        assert resp2.status_code == 200
        # This page has 3 items and has_more=False, so no infinite scroll trigger
        # But the items should still be rendered
        assert "Pagination Filter Item 3" in resp2.text
    finally:
        db.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(Item.title.like("Pagination Filter Item%")).delete()
            cleanup.query(Bundle).filter(Bundle.title == "Pagination Filter Bundle").delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_search_pagination_returns_appended_items(client):
    """Verify that page 2 requests (offset > 0) return only item rows
    with the next sentinel row, without the filter bar or outer wrapper.
    The sentinel should have hx-swap="outerHTML" and hx-target="this".
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Append Test Bundle")
        db.add(bundle)
        db.flush()

        for i in range(7):
            db.add(
                Item(
                    bundle_id=bundle.id,
                    title=f"Append Test Item {i}",
                    publisher="Append Test Publisher",
                    item_type="download",
                    available_formats=["PDF"],
                    downloads={},
                )
            )
        db.commit()

        # Request second page (offset=3, limit=3) – should return item_rows partial
        # 7 items total: page 1 has items 0-2, page 2 has items 3-5 (has_more=True), page 3 has item 6
        resp = client.get(
            "/library/search?q=Append&limit=3&offset=3"
        )
        assert resp.status_code == 200
        # Should NOT contain the filter bar or result-list wrapper
        assert "filter-bar" not in resp.text
        assert 'id="item-list-container"' not in resp.text
        # Should contain the 3 items from page 2
        assert "Append Test Item 3" in resp.text
        assert "Append Test Item 4" in resp.text
        assert "Append Test Item 5" in resp.text
        # Should have exactly 3 result-row articles (items + sentinel counts as one)
        assert resp.text.count('<article class="result-row"') == 3
        # The sentinel should be a .scroll-sentinel div with hx-trigger
        # targeting the actual scroll container (#master-stream)
        assert 'class="scroll-sentinel"' in resp.text
        assert 'hx-trigger="intersect once root:#master-stream rootMargin:200px"' in resp.text
        assert 'hx-swap="outerHTML"' in resp.text
        assert 'hx-target="this"' in resp.text
        # The sentinel should have the next offset (6) in its hx-get
        assert "offset=6" in resp.text

        # Request third page (offset=6, limit=3) – has_more=False, no sentinel
        resp2 = client.get(
            "/library/search?q=Append&limit=3&offset=6"
        )
        assert resp2.status_code == 200
        assert "Append Test Item 6" in resp2.text  # Last item
        # No sentinel when has_more is False
        assert 'class="scroll-sentinel"' not in resp2.text
    finally:
        db.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(Item.title.like("Append Test Item%")).delete()
            cleanup.query(Bundle).filter(Bundle.title == "Append Test Bundle").delete()
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


def test_library_publishers_filtered_by_q(client):
    """Verify that /library/publishers?q=... returns only publisher rows
    whose name matches the search query (case-insensitive substring)."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Publisher Filter Bundle")
        db.add(bundle)
        db.flush()

        db.add(
            Item(
                bundle_id=bundle.id,
                title="Item Alpha",
                publisher="Alpha Press",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.add(
            Item(
                bundle_id=bundle.id,
                title="Item Beta",
                publisher="Beta Books",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.commit()

        # Filter for "Alpha" – should return only Alpha Press
        resp = client.get("/library/publishers?q=Alpha")
        assert resp.status_code == 200
        publishers = resp.context["publishers"]
        names = [p["name"] for p in publishers]
        assert names == ["Alpha Press"]

        # Filter for "beta" (case-insensitive) – should return only Beta Books
        resp = client.get("/library/publishers?q=beta")
        assert resp.status_code == 200
        publishers = resp.context["publishers"]
        names = [p["name"] for p in publishers]
        assert names == ["Beta Books"]

        # Empty query – should return all publishers
        resp = client.get("/library/publishers")
        assert resp.status_code == 200
        publishers = resp.context["publishers"]
        names = [p["name"] for p in publishers]
        assert "Alpha Press" in names
        assert "Beta Books" in names

        # No match – should return empty list
        resp = client.get("/library/publishers?q=Nonexistent")
        assert resp.status_code == 200
        assert resp.context["publishers"] == []
    finally:
        db.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(
                Item.title.in_(["Item Alpha", "Item Beta"])
            ).delete()
            cleanup.query(Bundle).filter(
                Bundle.title == "Publisher Filter Bundle"
            ).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_home_page_escape_key_cascade(client):
    """Verify that the home page contains a global Escape key listener
    implementing a 3-tier cancellation cascade: clear search, close
    inspector drawer, and clear active filter."""
    response = client.get("/")
    assert response.status_code == 200
    # The global keydown listener must be present
    assert "document.addEventListener('keydown'" in response.text
    # Escape key check
    assert "'Escape'" in response.text
    # Tier 1: references #library-search
    assert "getElementById('library-search')" in response.text
    # Tier 2: references .drawer-close inside #inspector-drawer
    assert "#inspector-drawer .drawer-close" in response.text
    # Tier 3: references .filter-clear-btn
    assert ".filter-clear-btn" in response.text


def test_library_bundles_filtered_by_q(client):
    """Verify that /library/bundles?q=... returns only bundle rows
    whose title matches the search query (case-insensitive substring)."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle_x = Bundle(title="Xenon Bundle")
        bundle_y = Bundle(title="Yttrium Bundle")
        db.add_all([bundle_x, bundle_y])
        db.flush()

        db.add(
            Item(
                bundle_id=bundle_x.id,
                title="Xenon Item",
                publisher="Publisher X",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.add(
            Item(
                bundle_id=bundle_y.id,
                title="Yttrium Item",
                publisher="Publisher Y",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.commit()

        # Filter for "xenon" (case-insensitive) – should return only Xenon Bundle
        resp = client.get("/library/bundles?q=xenon")
        assert resp.status_code == 200
        bundles = resp.context["bundles"]
        names = [b["name"] for b in bundles]
        assert names == ["Xenon Bundle"]

        # Filter for "Yttrium" – should return only Yttrium Bundle
        resp = client.get("/library/bundles?q=Yttrium")
        assert resp.status_code == 200
        bundles = resp.context["bundles"]
        names = [b["name"] for b in bundles]
        assert names == ["Yttrium Bundle"]

        # Empty query – should return all bundles
        resp = client.get("/library/bundles")
        assert resp.status_code == 200
        bundles = resp.context["bundles"]
        names = [b["name"] for b in bundles]
        assert "Xenon Bundle" in names
        assert "Yttrium Bundle" in names

        # No match – should return empty list
        resp = client.get("/library/bundles?q=Nonexistent")
        assert resp.status_code == 200
        assert resp.context["bundles"] == []
    finally:
        db.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(
                Item.title.in_(["Xenon Item", "Yttrium Item"])
            ).delete()
            cleanup.query(Bundle).filter(
                Bundle.title.in_(["Xenon Bundle", "Yttrium Bundle"])
            ).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_get_sort_key_prefix_stripping():
    """Verify that get_sort_key strips common Humble Bundle prefixes
    and returns a lowercase, trimmed title for smart A-Z sorting."""
    # "Humble Book Bundle: Foo" → "foo"
    assert get_sort_key("Humble Book Bundle: Foo") == "foo"
    # "Humble Foo" → "foo"
    assert get_sort_key("Humble Foo") == "foo"
    # "The Foo" → "foo"
    assert get_sort_key("The Foo") == "foo"
    # Case-insensitive prefix stripping
    assert get_sort_key("HUMBLE BOOK BUNDLE: Bar") == "bar"
    assert get_sort_key("the baz") == "baz"
    # Plain title unchanged (but lowercased)
    assert get_sort_key("Plain Title") == "plain title"
    # Whitespace is trimmed
    assert get_sort_key("  Spaced  ") == "spaced"


def test_search_results_hidden_filter_inputs(client):
    """Verify that search_results.html renders hidden <input> elements for
    active publisher and bundle_id filters so the sort select's hx-include
    can read them."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Hidden Input Bundle")
        db.add(bundle)
        db.flush()

        db.add(
            Item(
                bundle_id=bundle.id,
                title="Hidden Input Item",
                publisher="Hidden Input Publisher",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.commit()

        # Filter by publisher — hidden publisher input must be present
        resp = client.get("/library/search?publisher=Hidden+Input+Publisher")
        assert resp.status_code == 200
        assert 'name="publisher"' in resp.text
        assert 'value="Hidden Input Publisher"' in resp.text
        # No bundle_id input when not filtering by bundle
        assert 'name="bundle_id"' not in resp.text

        # Filter by bundle_id — hidden bundle_id input must be present
        resp = client.get(f"/library/search?bundle_id={bundle.id}")
        assert resp.status_code == 200
        assert 'name="bundle_id"' in resp.text
        assert f'value="{bundle.id}"' in resp.text
        # No publisher input when not filtering by publisher
        assert 'name="publisher"' not in resp.text

        # No filter — neither hidden input should be present
        resp = client.get("/library/search")
        assert resp.status_code == 200
        assert 'name="publisher"' not in resp.text
        assert 'name="bundle_id"' not in resp.text
    finally:
        db.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(Item.title == "Hidden Input Item").delete()
            cleanup.query(Bundle).filter(Bundle.title == "Hidden Input Bundle").delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_library_search_publisher_filter_and_sort_desc(client):
    """Verify that /library/search with publisher filter and sort=title_desc
    retains both the filter and the descending title sort."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Sort Filter Bundle")
        db.add(bundle)
        db.flush()

        db.add(
            Item(
                bundle_id=bundle.id,
                title="Alpha Book",
                publisher="Sort Publisher",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.add(
            Item(
                bundle_id=bundle.id,
                title="Zeta Book",
                publisher="Sort Publisher",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.add(
            Item(
                bundle_id=bundle.id,
                title="Middle Book",
                publisher="Sort Publisher",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
        )
        db.commit()

        # Request with publisher filter and title_desc sort
        resp = client.get(
            "/library/search?publisher=Sort+Publisher&sort=title_desc"
        )
        assert resp.status_code == 200
        # All three items should be present
        assert resp.text.count('<article class="result-row"') == 3
        # Verify descending order: Zeta before Middle before Alpha
        zeta_pos = resp.text.index("Zeta Book")
        middle_pos = resp.text.index("Middle Book")
        alpha_pos = resp.text.index("Alpha Book")
        assert zeta_pos < middle_pos < alpha_pos
    finally:
        db.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(
                Item.title.in_(["Alpha Book", "Zeta Book", "Middle Book"])
            ).delete()
            cleanup.query(Bundle).filter(
                Bundle.title == "Sort Filter Bundle"
            ).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_scroll_sentinel_includes_sort_parameter(client):
    """Verify that the infinite-scroll sentinel includes the active sort
    parameter so that subsequent pages maintain the sort order."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle = Bundle(title="Sentinel Sort Bundle")
        db.add(bundle)
        db.flush()

        for i in range(6):
            db.add(
                Item(
                    bundle_id=bundle.id,
                    title=f"Sentinel Sort Item {i}",
                    publisher="Sentinel Sort Publisher",
                    item_type="download",
                    available_formats=["PDF"],
                    downloads={},
                )
            )
        db.commit()

        # Request first page with sort=title_desc (limit=3 so has_more=True)
        resp = client.get(
            "/library/search?sort=title_desc&limit=3&offset=0"
        )
        assert resp.status_code == 200
        # The sentinel hx-get must include the sort parameter
        assert "sort=title_desc" in resp.text
        # Verify has_more triggered the scroll sentinel
        assert 'class="scroll-sentinel"' in resp.text
        assert resp.text.count('<article class="result-row"') == 3
    finally:
        db.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(
                Item.title.like("Sentinel Sort Item%")
            ).delete()
            cleanup.query(Bundle).filter(
                Bundle.title == "Sentinel Sort Bundle"
            ).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_home_page_sync_sort_dropdown(client):
    """Verify that home.html includes context-aware sort option definitions
    and the syncSortDropdown JavaScript function so the sort dropdown
    dynamically adapts to the active view (books vs. publishers/bundles)."""
    response = client.get("/")
    assert response.status_code == 200

    # The syncSortDropdown function must be defined
    assert "function syncSortDropdown(viewType)" in response.text

    # Books view sort options
    assert '<option value="title_asc">Title (A to Z)</option>' in response.text
    assert '<option value="title_desc">Title (Z to A)</option>' in response.text
    assert '<option value="publisher_asc">Publisher (A to Z)</option>' in response.text

    # Category (publishers/bundles) view sort options (Name-based + counts)
    assert '<option value="count_desc">Most Items</option>' in response.text
    assert '<option value="count_asc">Least Items</option>' in response.text

    # Bundles view date sort options
    assert '<option value="date_desc">Newest Purchase</option>' in response.text
    assert '<option value="date_asc">Oldest Purchase</option>' in response.text

    # The function should handle the books viewType branch
    assert "viewType === 'books'" in response.text
    # The function should handle the publishers/bundles viewType branch
    assert "viewType === 'publishers'" in response.text
    assert "viewType === 'bundles'" in response.text

    # The dropdown reset logic: count desc/asc → title_asc for books
    assert "currentValue === 'count_desc'" in response.text
    # The dropdown reset logic: publisher_asc → title_asc for categories
    assert "currentValue === 'publisher_asc'" in response.text
    # The dropdown reset logic: date desc/asc → title_asc for publishers
    assert "currentValue === 'date_desc'" in response.text


def test_library_bundles_date_desc_sort(client):
    """Verify that /library/bundles?sort=date_desc returns bundles ordered
    by purchase_date descending, with nulls sorted last."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bundle_old = Bundle(title="Oldest Bundle", purchase_date="2020-01-15")
        bundle_new = Bundle(title="Newest Bundle", purchase_date="2024-06-01")
        bundle_none = Bundle(title="No Date Bundle", purchase_date=None)
        db.add_all([bundle_old, bundle_new, bundle_none])
        db.flush()

        for b in [bundle_old, bundle_new, bundle_none]:
            db.add(
                Item(
                    bundle_id=b.id,
                    title=f"{b.title} Item",
                    publisher="Date Sort Publisher",
                    item_type="download",
                    available_formats=["PDF"],
                    downloads={},
                )
            )
        db.commit()
    finally:
        db.close()

    try:
        resp = client.get("/library/bundles?sort=date_desc")
        assert resp.status_code == 200
        bundles = resp.context["bundles"]
        names = [b["name"] for b in bundles]
        # Newest first, oldest second, null last
        assert names[0] == "Newest Bundle"
        assert names[1] == "Oldest Bundle"
        assert names[2] == "No Date Bundle"
        # Verify purchase_date is present in context
        assert bundles[0]["purchase_date"] == "2024-06-01"
        assert bundles[1]["purchase_date"] == "2020-01-15"
        assert bundles[2]["purchase_date"] is None
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(Item).filter(
                Item.title.in_([
                    "Oldest Bundle Item",
                    "Newest Bundle Item",
                    "No Date Bundle Item",
                ])
            ).delete()
            cleanup.query(Bundle).filter(
                Bundle.title.in_(["Oldest Bundle", "Newest Bundle", "No Date Bundle"])
            ).delete()
            cleanup.commit()
        finally:
            cleanup.close()
