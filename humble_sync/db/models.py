import uuid
from datetime import datetime, timezone

from sqlalchemy import Float, Integer, String, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from fastapi_users.db import SQLAlchemyBaseUserTableUUID

from humble_sync.db.database import Base


class Bundle(Base):
    __tablename__ = "bundles"
    __table_args__ = (UniqueConstraint("user_id", "title", name="uq_user_bundle_title"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String, index=True, nullable=False)
    purchase_date: Mapped[str | None] = mapped_column(String, nullable=True)
    captured_at: Mapped[str | None] = mapped_column(String, nullable=True)

    items: Mapped[list["Item"]] = relationship(
        back_populates="bundle", cascade="all, delete-orphan"
    )


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("user_id", "bundle_id", "title", name="uq_user_item_bundle_title"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    bundle_id: Mapped[int] = mapped_column(
        ForeignKey("bundles.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String, index=True, nullable=False)
    publisher: Mapped[str] = mapped_column(String, index=True, default="Unknown")
    item_type: Mapped[str] = mapped_column(String, default="download")
    available_formats: Mapped[list] = mapped_column(JSON, default=list)
    downloads: Mapped[dict] = mapped_column(JSON, default=dict)

    bundle: Mapped["Bundle"] = relationship(back_populates="items")


class EvaluatedBundle(Base):
    __tablename__ = "evaluated_bundles"
    __table_args__ = (UniqueConstraint("user_id", "url", name="uq_user_evaluated_bundle_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    bundle_name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, index=True, nullable=False)
    machine_name: Mapped[str | None] = mapped_column(String, nullable=True)
    end_date: Mapped[str | None] = mapped_column(String, nullable=True)
    evaluated_at: Mapped[str | None] = mapped_column(String, nullable=True)
    expired_at: Mapped[str | None] = mapped_column(String, nullable=True)
    evaluation: Mapped[dict] = mapped_column(JSON, default=dict)


class UserBookLog(Base):
    __tablename__ = "user_book_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "norm_title", "status", name="uq_user_booklog_entry"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    norm_title: Mapped[str] = mapped_column(String, index=True, nullable=False)
    volume_info: Mapped[str | None] = mapped_column(String, nullable=True)
    author_or_publisher: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, index=True, default="wishlist")
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )
    updated_at: Mapped[str] = mapped_column(
        String,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"