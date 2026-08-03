"""
Unit tests for humble_sync.services modules.
Tests title normalization, duplicate grouping, catalog parsing, and status calculation.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure test database is used
os.environ["DATABASE_URL"] = "sqlite:///./test_humble_library.db"

from humble_sync.db.database import Base, SessionLocal, engine
from humble_sync.db.models import Bundle, Item
from humble_sync.services.duplicates import (
    find_duplicates,
    format_duplicate_report,
    normalize_title,
)
from humble_sync.services.parser import (
    extract_downloads,
    extract_expiration_from_url,
    extract_items_from_bundle,
    parse_dump,
)
from humble_sync.services.status import check_status, format_status_report


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="function", autouse=True)
def clean_test_database():
    """Drop and recreate the schema before every test function."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


# ── Title Normalization Tests ─────────────────────────────────────────────


class TestNormalizeTitle:
    """Tests for normalize_title function."""

    def test_lowercase_conversion(self):
        """Verify titles are converted to lowercase."""
        assert normalize_title("The Great Book") == "the great book"

    def test_punctuation_removal(self):
        """Verify punctuation is stripped."""
        assert normalize_title("Book: A Story!") == "book a story"

    def test_whitespace_collapse(self):
        """Verify multiple spaces are collapsed to single space."""
        assert normalize_title("The   Great   Book") == "the great book"

    def test_combined_normalization(self):
        """Verify lowercase, punctuation removal, and whitespace collapse work together."""
        assert normalize_title("  The Great Book: A Story!  ") == "the great book a story"

    def test_empty_string(self):
        """Verify empty string returns empty string."""
        assert normalize_title("") == ""

    def test_special_characters(self):
        """Verify special characters like quotes and dashes are removed."""
        assert normalize_title("Book's \"Great\" Adventure") == "books great adventure"

    def test_numbers_preserved(self):
        """Verify numbers are preserved (they are word characters)."""
        assert normalize_title("Book 2: The Sequel") == "book 2 the sequel"

    def test_underscores_preserved(self):
        """Verify underscores are preserved (they are word characters)."""
        assert normalize_title("book_title") == "book_title"


# ── Duplicate Detection Tests ─────────────────────────────────────────────


class TestFindDuplicates:
    """Tests for find_duplicates function."""

    def test_no_duplicates(self):
        """Verify no duplicates returned when all titles are unique."""
        items = [
            {"title": "Book A", "bundle": "Bundle 1", "purchase_date": "2024-01-01"},
            {"title": "Book B", "bundle": "Bundle 2", "purchase_date": "2024-01-02"},
        ]
        result = find_duplicates(items)
        assert result == {}

    def test_exact_duplicates(self):
        """Verify exact duplicate titles are grouped."""
        items = [
            {"title": "Same Book", "bundle": "Bundle 1", "purchase_date": "2024-01-01"},
            {"title": "Same Book", "bundle": "Bundle 2", "purchase_date": "2024-01-02"},
        ]
        result = find_duplicates(items)
        assert len(result) == 1
        assert "same book" in result
        assert len(result["same book"]) == 2

    def test_fuzzy_duplicates(self):
        """Verify titles that differ only in case/punctuation are grouped."""
        items = [
            {"title": "The Great Book", "bundle": "Bundle 1", "purchase_date": "2024-01-01"},
            {"title": "the great book!", "bundle": "Bundle 2", "purchase_date": "2024-01-02"},
        ]
        result = find_duplicates(items)
        assert len(result) == 1
        assert "the great book" in result

    def test_single_item_not_duplicate(self):
        """Verify single occurrence is not reported as duplicate."""
        items = [
            {"title": "Unique Book", "bundle": "Bundle 1", "purchase_date": "2024-01-01"},
        ]
        result = find_duplicates(items)
        assert result == {}

    def test_empty_items_list(self):
        """Verify empty list returns empty dict."""
        result = find_duplicates([])
        assert result == {}

    def test_multiple_duplicate_clusters(self):
        """Verify multiple duplicate clusters are returned."""
        items = [
            {"title": "Book A", "bundle": "Bundle 1", "purchase_date": "2024-01-01"},
            {"title": "Book A", "bundle": "Bundle 2", "purchase_date": "2024-01-02"},
            {"title": "Book B", "bundle": "Bundle 3", "purchase_date": "2024-01-03"},
            {"title": "Book B", "bundle": "Bundle 4", "purchase_date": "2024-01-04"},
        ]
        result = find_duplicates(items)
        assert len(result) == 2

    def test_empty_title_skipped(self):
        """Verify items with empty titles are skipped."""
        items = [
            {"title": "", "bundle": "Bundle 1", "purchase_date": "2024-01-01"},
            {"title": "  ", "bundle": "Bundle 2", "purchase_date": "2024-01-02"},
        ]
        result = find_duplicates(items)
        assert result == {}


class TestFormatDuplicateReport:
    """Tests for format_duplicate_report function."""

    def test_no_duplicates_report(self):
        """Verify report indicates no duplicates found."""
        report = format_duplicate_report({}, total_items=10, source_file="test.json")
        assert "No duplicates found" in report
        assert "Total items scanned:  10" in report

    def test_with_duplicates_report(self):
        """Verify report includes duplicate entries."""
        duplicates = {
            "same book": [
                {"display_title": "Same Book", "bundle": "Bundle 1", "purchase_date": "2024-01-01"},
                {"display_title": "Same Book", "bundle": "Bundle 2", "purchase_date": "2024-01-02"},
            ]
        }
        report = format_duplicate_report(duplicates, total_items=5, source_file="test.json")
        assert "Duplicate clusters:   1 titles" in report
        assert "Same Book" in report
        assert "Bundle 1" in report
        assert "Bundle 2" in report


# ── Catalog Parsing Tests ─────────────────────────────────────────────────


class TestExtractExpirationFromUrl:
    """Tests for extract_expiration_from_url function."""

    def test_valid_expiration(self):
        """Verify expiration timestamp is extracted from valid URL."""
        url = "https://example.com/file.pdf?t=exp=1700000000~acl=/*"
        result = extract_expiration_from_url(url)
        assert result is not None
        # Should be an ISO format datetime string
        assert "T" in result

    def test_no_expiration(self):
        """Verify None returned when no exp= parameter exists."""
        url = "https://example.com/file.pdf?t=other=value"
        result = extract_expiration_from_url(url)
        assert result is None

    def test_empty_url(self):
        """Verify None returned for empty URL."""
        result = extract_expiration_from_url("")
        assert result is None

    def test_invalid_url(self):
        """Verify None returned for malformed URL."""
        result = extract_expiration_from_url("not a url")
        assert result is None


class TestExtractDownloads:
    """Tests for extract_downloads function."""

    def test_empty_subproduct(self):
        """Verify empty dict returned for subproduct with no downloads."""
        result = extract_downloads({})
        assert result == {}

    def test_single_format(self):
        """Verify single download format is extracted."""
        subproduct = {
            "downloads": [
                {
                    "download_struct": [
                        {
                            "name": "PDF",
                            "url": {"web": "https://example.com/file.pdf"},
                            "file_size": 1024,
                            "human_size": "1 KB",
                        }
                    ]
                }
            ]
        }
        result = extract_downloads(subproduct)
        assert "PDF" in result
        assert result["PDF"]["url"] == "https://example.com/file.pdf"
        assert result["PDF"]["file_size_bytes"] == 1024

    def test_multiple_formats(self):
        """Verify multiple download formats are extracted."""
        subproduct = {
            "downloads": [
                {
                    "download_struct": [
                        {"name": "PDF", "url": {"web": "https://example.com/file.pdf"}},
                        {"name": "EPUB", "url": {"web": "https://example.com/file.epub"}},
                    ]
                }
            ]
        }
        result = extract_downloads(subproduct)
        assert "PDF" in result
        assert "EPUB" in result

    def test_missing_url_skipped(self):
        """Verify entries without web URL are skipped."""
        subproduct = {
            "downloads": [
                {
                    "download_struct": [
                        {"name": "PDF", "url": {}},  # No web key
                    ]
                }
            ]
        }
        result = extract_downloads(subproduct)
        assert result == {}


class TestExtractItemsFromBundle:
    """Tests for extract_items_from_bundle function."""

    def test_empty_bundle(self):
        """Verify empty list returned for empty bundle."""
        result = extract_items_from_bundle({}, "2024-01-01T00:00:00+00:00")
        assert result == []

    def test_subproduct_extraction(self):
        """Verify subproducts are extracted as download items."""
        bundle = {
            "product": {"human_name": "Test Bundle"},
            "created": "2024-01-01",
            "subproducts": [
                {
                    "human_name": "Test Book",
                    "payee": {"human_name": "Test Publisher"},
                    "downloads": [],
                }
            ],
        }
        result = extract_items_from_bundle(bundle, "2024-01-01T00:00:00+00:00")
        assert len(result) == 1
        assert result[0]["title"] == "Test Book"
        assert result[0]["publisher"] == "Test Publisher"
        assert result[0]["type"] == "download"

    def test_third_party_key_extraction(self):
        """Verify third-party keys are extracted."""
        bundle = {
            "product": {"human_name": "Test Bundle"},
            "created": "2024-01-01",
            "subproducts": [],
            "tpkd_dict": {
                "all_tpks": [
                    {
                        "human_name": "Steam Key",
                        "key_type_human_name": "Steam Activation Key",
                    }
                ]
            },
        }
        result = extract_items_from_bundle(bundle, "2024-01-01T00:00:00+00:00")
        assert len(result) == 1
        assert result[0]["title"] == "Steam Key"
        assert result[0]["type"] == "redemption_key"
        assert result[0]["available_formats"] == ["KEY"]

    def test_discount_items_skipped(self):
        """Verify items with 'Discount' in title are skipped."""
        bundle = {
            "product": {"human_name": "Test Bundle"},
            "created": "2024-01-01",
            "subproducts": [
                {"human_name": "Discount Item", "downloads": []},
            ],
        }
        result = extract_items_from_bundle(bundle, "2024-01-01T00:00:00+00:00")
        assert result == []


class TestParseDump:
    """Tests for parse_dump function."""

    def test_file_not_found(self):
        """Verify FileNotFoundError raised for missing dump file."""
        with pytest.raises(FileNotFoundError):
            parse_dump("nonexistent_file.json")

    def test_empty_dump_file(self):
        """Verify empty dump returns empty items list."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("")
            f.flush()
            try:
                result = parse_dump(f.name)
                assert result["metadata"]["total_items"] == 0
                assert result["items"] == []
            finally:
                Path(f.name).unlink()

    def test_valid_dump_file(self):
        """Verify valid dump file is parsed correctly."""
        dump_data = {
            "data": {
                "bundle1": {
                    "product": {"human_name": "Test Bundle"},
                    "created": "2024-01-01",
                    "subproducts": [
                        {
                            "human_name": "Test Book",
                            "payee": {"human_name": "Publisher"},
                            "downloads": [],
                        }
                    ],
                }
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(json.dumps(dump_data) + "\n")
            f.flush()
            try:
                result = parse_dump(f.name)
                assert result["metadata"]["total_items"] == 1
                assert result["items"][0]["title"] == "Test Book"
            finally:
                Path(f.name).unlink()


# ── Status Calculation Tests ──────────────────────────────────────────────


class TestCheckStatus:
    """Tests for check_status function."""

    def test_empty_database_returns_missing(self):
        """Verify MISSING status returned when database is empty."""
        result = check_status()
        assert result["status"] == "MISSING"

    def test_status_with_items(self):
        """Verify status calculation with items in database."""
        db = SessionLocal()
        try:
            bundle = Bundle(
                title="Test Bundle",
                purchase_date="2024-01-01",
                captured_at=datetime.now(timezone.utc).isoformat(),
            )
            db.add(bundle)
            db.flush()

            item = Item(
                bundle_id=bundle.id,
                title="Test Item",
                publisher="Test Publisher",
                item_type="download",
                available_formats=["PDF"],
                downloads={},
            )
            db.add(item)
            db.commit()

            result = check_status()
            assert result["status"] == "NO_DOWNLOADS"
            assert result["total_items"] == 1
            assert result["total_bundles"] == 1
        finally:
            db.close()

    def test_status_with_active_links(self):
        """Verify ACTIVE status when download links are valid."""
        db = SessionLocal()
        try:
            bundle = Bundle(
                title="Test Bundle",
                purchase_date="2024-01-01",
                captured_at=datetime.now(timezone.utc).isoformat(),
            )
            db.add(bundle)
            db.flush()

            # Create item with future expiration
            future_expiration = datetime.now(timezone.utc).replace(year=2099).isoformat()
            item = Item(
                bundle_id=bundle.id,
                title="Test Item",
                publisher="Test Publisher",
                item_type="download",
                available_formats=["PDF"],
                downloads={
                    "PDF": {
                        "url": "https://example.com/file.pdf",
                        "url_expires_at": future_expiration,
                    }
                },
            )
            db.add(item)
            db.commit()

            result = check_status()
            assert result["status"] == "ACTIVE"
            assert result["active_links"] == 1
            assert result["expired_links"] == 0
        finally:
            db.close()

    def test_status_with_expired_links(self):
        """Verify EXPIRED status when all download links are expired."""
        db = SessionLocal()
        try:
            bundle = Bundle(
                title="Test Bundle",
                purchase_date="2024-01-01",
                captured_at=datetime.now(timezone.utc).isoformat(),
            )
            db.add(bundle)
            db.flush()

            # Create item with past expiration
            past_expiration = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
            item = Item(
                bundle_id=bundle.id,
                title="Test Item",
                publisher="Test Publisher",
                item_type="download",
                available_formats=["PDF"],
                downloads={
                    "PDF": {
                        "url": "https://example.com/file.pdf",
                        "url_expires_at": past_expiration,
                    }
                },
            )
            db.add(item)
            db.commit()

            result = check_status()
            assert result["status"] == "EXPIRED"
            assert result["active_links"] == 0
            assert result["expired_links"] == 1
        finally:
            db.close()

    def test_key_only_items_counted(self):
        """Verify redemption keys are counted separately."""
        db = SessionLocal()
        try:
            bundle = Bundle(
                title="Test Bundle",
                purchase_date="2024-01-01",
                captured_at=datetime.now(timezone.utc).isoformat(),
            )
            db.add(bundle)
            db.flush()

            item = Item(
                bundle_id=bundle.id,
                title="Steam Key",
                publisher="Test Publisher",
                item_type="redemption_key",
                available_formats=["KEY"],
                downloads={},
            )
            db.add(item)
            db.commit()

            result = check_status()
            assert result["key_only_items"] == 1
        finally:
            db.close()


class TestFormatStatusReport:
    """Tests for format_status_report function."""

    def test_missing_status_report(self):
        """Verify MISSING status report format."""
        data = {"status": "MISSING", "file_path": "test.db"}
        report = format_status_report(data)
        assert "MISSING" in report
        assert "Catalog file not found" in report

    def test_active_status_report(self):
        """Verify ACTIVE status report format."""
        data = {
            "status": "ACTIVE",
            "file_path": "test.db",
            "total_items": 10,
            "total_bundles": 2,
            "key_only_items": 1,
            "sync_age": "1d 2h ago",
            "active_links": 5,
            "expired_links": 0,
            "link_time_remaining": "24h 30m",
        }
        report = format_status_report(data)
        assert "ACTIVE" in report
        assert "Total Items:         10" in report
        assert "Active CDN Links:    5" in report

    def test_expired_status_report(self):
        """Verify EXPIRED status report format."""
        data = {
            "status": "EXPIRED",
            "file_path": "test.db",
            "total_items": 10,
            "total_bundles": 2,
            "key_only_items": 0,
            "sync_age": "5d 0h ago",
            "active_links": 0,
            "expired_links": 5,
            "link_time_remaining": "None",
        }
        report = format_status_report(data)
        assert "EXPIRED" in report
        assert "All download URLs expired" in report