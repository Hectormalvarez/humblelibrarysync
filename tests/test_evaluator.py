"""
Unit tests for humble_sync.services.evaluator module.
Tests title overlap percentage math, tier item mapping, and expired deal tracking.
"""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# Ensure test database is used
os.environ["DATABASE_URL"] = "sqlite:///./test_humble_library.db"

from humble_sync.db.database import Base, SessionLocal, engine
from humble_sync.db.models import EvaluatedBundle
from humble_sync.services.evaluator import (
    _build_tier_item_map,
    _parse_bundles_from_data,
    evaluate_deal,
    format_deal_report,
    format_expired_deals_report,
    format_expired_reading_list,
    get_expired_entries,
    get_unexpired_entries,
    load_evaluated_bundles_log,
    log_evaluated_bundle,
    mark_expired_entries,
    parse_bundles_dump,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="function", autouse=True)
def clean_test_database():
    """Drop and recreate the schema before every test function."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


# ── Overlap Percentage Math Tests ─────────────────────────────────────────


class TestEvaluateDeal:
    """Tests for evaluate_deal overlap calculation."""

    def test_zero_overlap(self):
        """Verify 0% overlap when no bundle items are in the library."""
        bundle_items = [{"title": "Book A"}, {"title": "Book B"}]
        library_items = [{"title": "Book C"}, {"title": "Book D"}]
        result = evaluate_deal(bundle_items, library_items)
        assert result["overlap_percentage"] == 0.0
        assert result["matched_count"] == 0
        assert result["total_items"] == 2
        assert sorted(result["new_items"]) == ["Book A", "Book B"]
        assert result["matched_items"] == []

    def test_full_overlap(self):
        """Verify 100% overlap when all bundle items are owned."""
        bundle_items = [{"title": "Book A"}, {"title": "Book B"}]
        library_items = [{"title": "Book A"}, {"title": "Book B"}]
        result = evaluate_deal(bundle_items, library_items)
        assert result["overlap_percentage"] == 100.0
        assert result["matched_count"] == 2
        assert result["new_items"] == []

    def test_partial_overlap(self):
        """Verify 50% overlap with half the items owned."""
        bundle_items = [{"title": "Book A"}, {"title": "Book B"}]
        library_items = [{"title": "Book A"}]
        result = evaluate_deal(bundle_items, library_items)
        assert result["overlap_percentage"] == 50.0
        assert result["matched_count"] == 1
        assert "Book A" in result["matched_items"]
        assert "Book B" in result["new_items"]

    def test_empty_bundle(self):
        """Verify 0% overlap for an empty bundle."""
        result = evaluate_deal([], [{"title": "Book A"}])
        assert result["overlap_percentage"] == 0.0
        assert result["total_items"] == 0
        assert result["matched_count"] == 0

    def test_normalized_title_matching(self):
        """Verify titles match after normalization (case, punctuation, whitespace)."""
        bundle_items = [{"title": "The Great Book!"}, {"title": "  A Story  "}]
        library_items = [{"title": "the great book"}, {"title": "a story"}]
        result = evaluate_deal(bundle_items, library_items)
        assert result["overlap_percentage"] == 100.0
        assert result["matched_count"] == 2

    def test_empty_titles_skipped(self):
        """Verify items with empty titles are skipped in matching."""
        bundle_items = [{"title": ""}, {"title": "Book A"}]
        library_items = [{"title": "Book A"}]
        result = evaluate_deal(bundle_items, library_items)
        # total_items counts all items including empty-title ones
        assert result["total_items"] == 2
        assert result["matched_count"] == 1

    def test_pricing_included(self):
        """Verify pricing data is passed through when provided."""
        pricing = [{"tier_id": "t1", "amount": 100, "currency": "USD", "is_bta": False, "header": "Tier 1"}]
        result = evaluate_deal(
            [{"title": "Book A"}],
            [{"title": "Book B"}],
            pricing=pricing,
        )
        assert result["pricing"] == pricing

    def test_tier_breakdown(self):
        """Verify tier_breakdown is computed when tier_item_map is provided."""
        items = [
            {"title": "Book A", "machine_name": "book_a"},
            {"title": "Book B", "machine_name": "book_b"},
            {"title": "Book C", "machine_name": "book_c"},
        ]
        pricing = [
            {"tier_id": "t1", "amount": 100, "currency": "USD", "is_bta": False, "header": "Tier 1", "item_machine_names": ["book_a"]},
            {"tier_id": "t2", "amount": 200, "currency": "USD", "is_bta": True, "header": "Tier 2", "item_machine_names": ["book_b", "book_c"]},
        ]
        tier_item_map = _build_tier_item_map(items, pricing)
        library_items = [{"title": "Book A"}]

        result = evaluate_deal(
            items,
            library_items,
            pricing=pricing,
            tier_item_map=tier_item_map,
        )

        assert "tier_breakdown" in result
        assert len(result["tier_breakdown"]) == 2
        t1 = result["tier_breakdown"][0]
        assert t1["tier_id"] == "t1"
        assert t1["owned"] == ["Book A"]
        assert t1["unowned"] == []
        t2 = result["tier_breakdown"][1]
        assert t2["tier_id"] == "t2"
        assert t2["owned"] == []
        assert sorted(t2["unowned"]) == ["Book B", "Book C"]


# ── Tier Item Mapping Tests ───────────────────────────────────────────────


class TestBuildTierItemMap:
    """Tests for _build_tier_item_map function."""

    def test_basic_mapping(self):
        """Verify items are mapped to correct tiers by machine_name."""
        items = [
            {"title": "Book A", "machine_name": "book_a"},
            {"title": "Book B", "machine_name": "book_b"},
        ]
        pricing = [
            {"tier_id": "t1", "item_machine_names": ["book_a"]},
            {"tier_id": "t2", "item_machine_names": ["book_b"]},
        ]
        result = _build_tier_item_map(items, pricing)
        assert len(result) == 2
        assert result["t1"][0]["title"] == "Book A"
        assert result["t2"][0]["title"] == "Book B"

    def test_missing_machine_name_ignored(self):
        """Verify items with unknown machine_names are excluded from tiers."""
        items = [
            {"title": "Book A", "machine_name": "book_a"},
        ]
        pricing = [
            {"tier_id": "t1", "item_machine_names": ["book_a", "nonexistent"]},
        ]
        result = _build_tier_item_map(items, pricing)
        assert len(result["t1"]) == 1
        assert result["t1"][0]["title"] == "Book A"

    def test_empty_tier(self):
        """Verify empty tier produces empty list."""
        items = [{"title": "Book A", "machine_name": "book_a"}]
        pricing = [{"tier_id": "t1", "item_machine_names": []}]
        result = _build_tier_item_map(items, pricing)
        assert result["t1"] == []

    def test_multiple_items_in_tier(self):
        """Verify multiple items can be in the same tier."""
        items = [
            {"title": "Book A", "machine_name": "book_a"},
            {"title": "Book B", "machine_name": "book_b"},
            {"title": "Book C", "machine_name": "book_c"},
        ]
        pricing = [
            {"tier_id": "t1", "item_machine_names": ["book_a", "book_b", "book_c"]},
        ]
        result = _build_tier_item_map(items, pricing)
        assert len(result["t1"]) == 3

    def test_item_without_machine_name_skipped(self):
        """Verify items without machine_name are not indexed."""
        items = [
            {"title": "Book A", "machine_name": ""},
            {"title": "Book B", "machine_name": "book_b"},
        ]
        pricing = [
            {"tier_id": "t1", "item_machine_names": ["book_b"]},
        ]
        result = _build_tier_item_map(items, pricing)
        assert len(result["t1"]) == 1
        assert result["t1"][0]["title"] == "Book B"


# ── Expired Deal Tracking Tests ───────────────────────────────────────────


class TestExpiredDealTracking:
    """Tests for log_evaluated_bundle, mark_expired_entries, and related helpers."""

    def test_log_and_load_evaluated_bundle(self):
        """Verify a bundle evaluation can be logged and retrieved."""
        eval_data = {
            "total_items": 5,
            "matched_count": 2,
            "overlap_percentage": 40.0,
            "matched_items": ["Book A", "Book B"],
            "new_items": ["Book C", "Book D", "Book E"],
            "pricing": [{"tier_id": "t1", "amount": 100, "currency": "USD"}],
        }
        log_evaluated_bundle(
            bundle_name="Test Bundle",
            bundle_url="https://www.humblebundle.com/books/test",
            machine_name="test_bundle",
            end_date=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            eval_data=eval_data,
        )

        entries = load_evaluated_bundles_log()
        assert len(entries) == 1
        assert entries[0]["bundle_name"] == "Test Bundle"
        assert entries[0]["evaluation"]["total_items"] == 5
        assert entries[0]["evaluation"]["overlap_percentage"] == 40.0

    def test_log_updates_existing_entry(self):
        """Verify logging the same URL updates the existing record."""
        eval_data = {"total_items": 3, "matched_count": 1, "overlap_percentage": 33.3}
        log_evaluated_bundle(
            bundle_name="Bundle V1",
            bundle_url="https://www.humblebundle.com/books/test",
            machine_name="test_bundle",
            end_date="2099-01-01T00:00:00+00:00",
            eval_data=eval_data,
        )
        # Update with new data
        eval_data_v2 = {"total_items": 10, "matched_count": 5, "overlap_percentage": 50.0}
        log_evaluated_bundle(
            bundle_name="Bundle V2",
            bundle_url="https://www.humblebundle.com/books/test",
            machine_name="test_bundle_v2",
            end_date="2099-01-01T00:00:00+00:00",
            eval_data=eval_data_v2,
        )

        entries = load_evaluated_bundles_log()
        assert len(entries) == 1
        assert entries[0]["bundle_name"] == "Bundle V2"
        assert entries[0]["evaluation"]["total_items"] == 10

    def test_mark_expired_entries(self):
        """Verify mark_expired_entries sets expired_at for past end_date."""
        past_end = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        eval_data = {"total_items": 1, "matched_count": 0, "overlap_percentage": 0.0}
        log_evaluated_bundle(
            bundle_name="Expired Bundle",
            bundle_url="https://www.humblebundle.com/books/expired",
            machine_name="expired_bundle",
            end_date=past_end,
            eval_data=eval_data,
        )

        mark_expired_entries()

        entries = load_evaluated_bundles_log()
        assert len(entries) == 1
        assert entries[0]["expired_at"] is not None

    def test_mark_does_not_expire_future_bundles(self):
        """Verify mark_expired_entries does not expire bundles with future end_date."""
        future_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        eval_data = {"total_items": 1, "matched_count": 0, "overlap_percentage": 0.0}
        log_evaluated_bundle(
            bundle_name="Future Bundle",
            bundle_url="https://www.humblebundle.com/books/future",
            machine_name="future_bundle",
            end_date=future_end,
            eval_data=eval_data,
        )

        mark_expired_entries()

        entries = load_evaluated_bundles_log()
        assert len(entries) == 1
        assert entries[0]["expired_at"] is None

    def test_get_expired_entries(self):
        """Verify get_expired_entries filters correctly."""
        entries = [
            {"bundle_name": "A", "expired_at": "2024-01-01T00:00:00+00:00"},
            {"bundle_name": "B", "expired_at": None},
            {"bundle_name": "C", "expired_at": "2024-06-01T00:00:00+00:00"},
        ]
        expired = get_expired_entries(entries)
        assert len(expired) == 2
        assert expired[0]["bundle_name"] == "A"
        assert expired[1]["bundle_name"] == "C"

    def test_get_unexpired_entries(self):
        """Verify get_unexpired_entries returns only non-expired, still-active bundles."""
        future_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        past_end = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        entries = [
            {"bundle_name": "Active", "expired_at": None, "end_date": future_end},
            {"bundle_name": "Expired", "expired_at": "2024-01-01T00:00:00+00:00", "end_date": past_end},
            {"bundle_name": "NoEnd", "expired_at": None, "end_date": ""},
        ]
        unexpired = get_unexpired_entries(entries)
        assert len(unexpired) == 1
        assert unexpired[0]["bundle_name"] == "Active"


# ── Format Report Tests ───────────────────────────────────────────────────


class TestFormatReports:
    """Tests for report formatting functions."""

    def test_format_deal_report_contains_key_sections(self):
        """Verify deal report contains overview and item sections."""
        eval_data = {
            "total_items": 3,
            "matched_count": 1,
            "overlap_percentage": 33.3,
            "matched_items": ["Book A"],
            "new_items": ["Book B", "Book C"],
        }
        report = format_deal_report("Test Bundle", eval_data)
        assert "DEAL EVALUATION REPORT" in report
        assert "Test Bundle" in report
        assert "33.3%" in report
        assert "Book A" in report
        assert "Book B" in report

    def test_format_expired_reading_list_deduplicates(self):
        """Verify reading list deduplicates titles across entries."""
        entries = [
            {
                "evaluation": {
                    "new_items": ["Book A", "Book B"],
                }
            },
            {
                "evaluation": {
                    "new_items": ["Book B", "Book C"],
                }
            },
        ]
        report = format_expired_reading_list(entries)
        assert "Total unique titles: 3" in report
        assert "Book A" in report
        assert "Book B" in report
        assert "Book C" in report

    def test_format_expired_deals_report_empty(self):
        """Verify empty report message when no expired deals."""
        report = format_expired_deals_report([])
        assert "No expired evaluated deals recorded" in report

    def test_format_expired_deals_report_with_entries(self):
        """Verify report includes bundle details."""
        entries = [
            {
                "bundle_name": "Test Bundle",
                "end_date": "2024-01-15T00:00:00+00:00",
                "expired_at": "2024-01-20T00:00:00+00:00",
                "evaluation": {
                    "total_items": 10,
                    "new_items": ["A", "B", "C"],
                    "overlap_percentage": 70.0,
                },
            }
        ]
        report = format_expired_deals_report(entries)
        assert "Test Bundle" in report
        assert "3 new / 10 total" in report
        assert "70.0% overlap" in report


# ── Parse Bundles From Data Tests ─────────────────────────────────────────


class TestParseBundlesFromData:
    """Tests for _parse_bundles_from_data with mock payloads."""

    def test_empty_data(self):
        """Verify empty data returns empty list."""
        result = _parse_bundles_from_data({})
        assert result == []

    def test_extracts_bundles_from_categories(self):
        """Verify bundles are extracted from books, games, software categories."""
        page_data = {
            "data": {
                "books": {
                    "mosaic": [
                        {
                            "products": [
                                {
                                    "tile_name": "Book Bundle",
                                    "product_url": "/books/test",
                                    "author": "Publisher",
                                    "end_date|datetime": "2099-01-01T00:00:00+00:00",
                                    "machine_name": "book_bundle",
                                }
                            ]
                        }
                    ]
                },
                "games": {
                    "mosaic": [
                        {
                            "products": [
                                {
                                    "tile_name": "Game Bundle",
                                    "product_url": "/games/test",
                                    "author": "Dev",
                                    "end_date|datetime": "2099-02-01T00:00:00+00:00",
                                    "machine_name": "game_bundle",
                                }
                            ]
                        }
                    ]
                },
                "software": {"mosaic": []},
            }
        }
        result = _parse_bundles_from_data(page_data)
        assert len(result) == 2
        assert result[0]["title"] == "Book Bundle"
        assert result[0]["url"] == "https://www.humblebundle.com/books/test"
        assert result[1]["title"] == "Game Bundle"

    def test_skips_empty_tile_name(self):
        """Verify products without tile_name are skipped."""
        page_data = {
            "data": {
                "books": {
                    "mosaic": [
                        {
                            "products": [
                                {
                                    "tile_name": "",
                                    "product_url": "/books/test",
                                }
                            ]
                        }
                    ]
                }
            }
        }
        result = _parse_bundles_from_data(page_data)
        assert result == []


# ── Parse Bundles Dump Tests ──────────────────────────────────────────────


class TestParseBundlesDump:
    """Tests for parse_bundles_dump with mock dump files."""

    def test_file_not_found(self):
        """Verify FileNotFoundError for missing dump."""
        with pytest.raises(FileNotFoundError):
            parse_bundles_dump(Path("nonexistent_dump.json"))

    def test_valid_dump(self, tmp_path):
        """Verify valid dump file is parsed correctly."""
        dump_data = {
            "captured_at": "2024-01-01T00:00:00+00:00",
            "data": {
                "data": {
                    "books": {
                        "mosaic": [
                            {
                                "products": [
                                    {
                                        "tile_name": "Test Bundle",
                                        "product_url": "/books/test",
                                        "author": "Author",
                                        "end_date|datetime": "2099-01-01T00:00:00+00:00",
                                        "machine_name": "test_bundle",
                                    }
                                ]
                            }
                        ]
                    }
                }
            },
        }
        dump_file = tmp_path / "test_dump.json"
        dump_file.write_text(
            __import__("json").dumps(dump_data),
            encoding="utf-8",
        )
        result = parse_bundles_dump(dump_file)
        assert len(result) == 1
        assert result[0]["title"] == "Test Bundle"