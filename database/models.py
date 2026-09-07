from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, declared_attr
from sqlmodel import Field, Relationship, SQLModel


class ListingStatus(str, Enum):
    NEW = "new"
    WATCHING = "watching"
    WON = "won"
    PURCHASED = "purchased"
    ARCHIVED = "archived"


class QueueStatus(str, Enum):
    """Lifecycle states for an opportunity awaiting human review."""

    NEW = "new"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class BaseTimestampModel(SQLModel):
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")},
    )

    version: ClassVar[int] = declared_attr(
        lambda cls: Column(Integer, server_default=text("1"), nullable=False)
    )

    __mapper_args__: ClassVar[dict] = declared_attr(
        lambda cls: {"version_id_col": cls.version}
    )


class Seller(BaseTimestampModel, table=True):
    __tablename__ = "sellers"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, min_length=1)
    username: Optional[str] = Field(default=None, index=True)
    rating: Optional[float] = Field(default=None)
    external_id: Optional[str] = Field(default=None, index=True)
    listings: Mapped[list["Listing"]] = Relationship(back_populates="seller")


class Search(BaseTimestampModel, table=True):
    __tablename__ = "searches"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    query: str = Field(index=True, min_length=1)
    source: str = Field(index=True, min_length=1)
    location: Optional[str] = Field(default=None, index=True)
    listings: Mapped[list["Listing"]] = Relationship(back_populates="search")


class Listing(BaseTimestampModel, table=True):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_listings_source_external_id"),
    )

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    title: str = Field(index=True, min_length=1)
    description: Optional[str] = Field(default=None)
    price: float = Field(ge=0)
    source: str = Field(index=True, min_length=1)
    external_id: Optional[str] = Field(default=None, index=True)
    url: Optional[str] = Field(default=None)
    status: ListingStatus = Field(default=ListingStatus.NEW, index=True)
    seller_id: Optional[UUID] = Field(default=None, foreign_key="sellers.id")
    search_id: Optional[UUID] = Field(default=None, foreign_key="searches.id")

    seller: Optional[Seller] = Relationship(back_populates="listings")
    search: Optional[Search] = Relationship(back_populates="listings")
    images: Mapped[list["Image"]] = Relationship(back_populates="listing")
    price_history: Mapped[list["PriceHistory"]] = Relationship(back_populates="listing")
    opportunities: Mapped[list["Opportunity"]] = Relationship(back_populates="listing")
    purchase: Optional["Purchase"] = Relationship(back_populates="listing")


class Image(BaseTimestampModel, table=True):
    __tablename__ = "images"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    url: str = Field(index=True, min_length=1)
    caption: Optional[str] = Field(default=None)
    listing_id: Optional[UUID] = Field(
        default=None, foreign_key="listings.id", index=True
    )

    listing: Optional[Listing] = Relationship(back_populates="images")


class PriceHistory(BaseTimestampModel, table=True):
    __tablename__ = "price_history"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    price: float = Field(ge=0)
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    listing_id: Optional[UUID] = Field(
        default=None, foreign_key="listings.id", index=True
    )

    listing: Optional[Listing] = Relationship(back_populates="price_history")


class Opportunity(BaseTimestampModel, table=True):
    __tablename__ = "opportunities"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    potential_profit: float = Field(ge=0)
    confidence_score: float = Field(ge=0, le=1)
    notes: Optional[str] = Field(default=None)
    listing_id: Optional[UUID] = Field(
        default=None, foreign_key="listings.id", index=True
    )

    listing: Optional[Listing] = Relationship(back_populates="opportunities")
    queue_item: Optional["Queue"] = Relationship(back_populates="opportunity")


class Queue(BaseTimestampModel, table=True):
    """A manually reviewed opportunity before it can be notified."""

    __tablename__ = "queues"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    status: QueueStatus = Field(default=QueueStatus.NEW, index=True)
    review_notes: Optional[str] = Field(default=None)
    reviewed_at: Optional[datetime] = Field(default=None, index=True)
    opportunity_id: UUID = Field(
        foreign_key="opportunities.id", unique=True, index=True
    )

    opportunity: Optional[Opportunity] = Relationship(back_populates="queue_item")


class NotificationDelivery(BaseTimestampModel, table=True):
    """Durable record of a successfully delivered opportunity notification."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "dedupe_key", "provider", name="uq_notification_delivery_key_provider"
        ),
    )

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    dedupe_key: str = Field(index=True, min_length=1)
    provider: str = Field(index=True, min_length=1)
    opportunity_id: Optional[UUID] = Field(default=None, index=True)


class Purchase(BaseTimestampModel, table=True):
    __tablename__ = "purchases"

    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    price_paid: float = Field(ge=0)
    purchased_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    notes: Optional[str] = Field(default=None)
    listing_id: Optional[UUID] = Field(
        default=None, foreign_key="listings.id", unique=True, index=True
    )

    listing: Optional[Listing] = Relationship(back_populates="purchase")


class DeletedRecord(SQLModel, table=True):
    """Tracks records deleted from the operational database to sync with analytics."""

    __tablename__ = "deleted_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    table_name: str = Field(index=True)
    record_id: str = Field(index=True)  # UUID string
    deleted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
        sa_column_kwargs={"server_default": "CURRENT_TIMESTAMP"},
    )
