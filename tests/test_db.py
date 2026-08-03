"""Tests for the humble_sync.db package – session lifecycle, schema reset,
and ORM relationship semantics (cascade delete, queries)."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from humble_sync.db.database import (
    Base,
    SessionLocal,
    engine,
    get_db,
    init_db,
    reset_database,
)
from humble_sync.db.models import Bundle, Item


class TestSessionCreation:
    """Verify SessionLocal produces a usable SQLAlchemy session."""

    def test_session_local_returns_session(self):
        """SessionLocal() should return an open Session bound to the engine."""
        db = SessionLocal()
        try:
            assert isinstance(db, Session)
            result = db.execute(text("SELECT 1")).scalar()
            assert result == 1
        finally:
            db.close()

    def test_get_db_yields_session(self):
        """get_db() should yield a Session and close it after the block."""
        gen = get_db()
        db = next(gen)
        try:
            assert isinstance(db, Session)
            assert db.query(Bundle).count() >= 0
        finally:
            try:
                next(gen)
            except StopIteration:
                pass


class TestDatabaseReset:
    """Verify init_db and reset_database manage the schema correctly."""

    def test_init_db_creates_tables(self):
        """init_db should create all tables if they don't exist."""
        Base.metadata.drop_all(bind=engine)
        init_db()
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "bundles" in tables
        assert "items" in tables
        assert "evaluated_bundles" in tables

    def test_reset_database_drops_and_recreates(self):
        """reset_database should drop all tables and recreate them empty."""
        db = SessionLocal()
        try:
            bundle = Bundle(title="Reset Test Bundle")
            db.add(bundle)
            db.commit()
            bundle_id = bundle.id
        finally:
            db.close()

        reset_database()

        db = SessionLocal()
        try:
            assert db.query(Bundle).filter(Bundle.id == bundle_id).first() is None
            assert db.query(Bundle).count() == 0
        finally:
            db.close()

        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "bundles" in tables
        assert "items" in tables


class TestORMRelationships:
    """Verify Bundle/Item relationships and cascade delete semantics."""

    def test_create_bundle_with_items(self):
        """Creating a Bundle with Item children should persist both."""
        db = SessionLocal()
        try:
            bundle = Bundle(title="Test Bundle", purchase_date="2024-01-01")
            item1 = Item(
                title="Item One", publisher="Publisher A",
                item_type="download", available_formats=["PDF"], downloads={},
            )
            item2 = Item(
                title="Item Two", publisher="Publisher B",
                item_type="download", available_formats=["EPUB"], downloads={},
            )
            bundle.items.append(item1)
            bundle.items.append(item2)
            db.add(bundle)
            db.commit()

            db.refresh(bundle)
            assert bundle.id is not None
            assert len(bundle.items) == 2
            assert {i.title for i in bundle.items} == {"Item One", "Item Two"}

            items = db.query(Item).filter(Item.bundle_id == bundle.id).all()
            assert len(items) == 2
        finally:
            db.close()

    def test_cascade_delete_removes_children(self):
        """Deleting a Bundle should cascade-delete its Items."""
        db = SessionLocal()
        try:
            bundle = Bundle(title="Cascade Delete Bundle")
            item = Item(
                title="Cascade Child", publisher="Publisher X",
                item_type="download", available_formats=[], downloads={},
            )
            bundle.items.append(item)
            db.add(bundle)
            db.commit()

            bundle_id = bundle.id
            item_id = item.id

            assert db.query(Bundle).filter(Bundle.id == bundle_id).first() is not None
            assert db.query(Item).filter(Item.id == item_id).first() is not None

            db.delete(bundle)
            db.commit()

            assert db.query(Bundle).filter(Bundle.id == bundle_id).first() is None
            assert db.query(Item).filter(Item.id == item_id).first() is None
        finally:
            db.close()

    def test_item_requires_bundle_id(self):
        """An Item without a valid bundle_id should fail to persist."""
        db = SessionLocal()
        try:
            item = Item(
                title="Orphan Item", publisher="Nobody",
                item_type="download", available_formats=[], downloads={},
            )
            db.add(item)
            with pytest.raises(Exception):
                db.commit()
        finally:
            db.rollback()
            db.close()

    def test_multiple_bundles_independent(self):
        """Items in one bundle should not appear in another bundle's items."""
        db = SessionLocal()
        try:
            b1 = Bundle(title="Bundle Alpha")
            b2 = Bundle(title="Bundle Beta")
            db.add_all([b1, b2])
            db.flush()

            db.add(Item(bundle_id=b1.id, title="Alpha Item", publisher="P", item_type="download"))
            db.add(Item(bundle_id=b2.id, title="Beta Item", publisher="P", item_type="download"))
            db.commit()

            db.refresh(b1)
            db.refresh(b2)
            assert len(b1.items) == 1
            assert b1.items[0].title == "Alpha Item"
            assert len(b2.items) == 1
            assert b2.items[0].title == "Beta Item"
        finally:
            db.close()
