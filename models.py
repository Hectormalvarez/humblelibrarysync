from sqlalchemy import Integer, String, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Bundle(Base):
    __tablename__ = "bundles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String, index=True, nullable=False)
    purchase_date: Mapped[str | None] = mapped_column(String, nullable=True)
    captured_at: Mapped[str | None] = mapped_column(String, nullable=True)

    items: Mapped[list["Item"]] = relationship(
        back_populates="bundle", cascade="all, delete-orphan"
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    bundle_name: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    machine_name: Mapped[str | None] = mapped_column(String, nullable=True)
    end_date: Mapped[str | None] = mapped_column(String, nullable=True)
    evaluated_at: Mapped[str | None] = mapped_column(String, nullable=True)
    expired_at: Mapped[str | None] = mapped_column(String, nullable=True)
    evaluation: Mapped[dict] = mapped_column(JSON, default=dict)
