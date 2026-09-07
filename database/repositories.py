from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Generic, Optional, TypeVar
from uuid import UUID

from sqlalchemy import func, update as sqlalchemy_update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from sqlmodel import Session, SQLModel, select

from database.database import get_session
from database.models import (
    Listing,
    ListingStatus,
    NotificationDelivery,
    Opportunity,
    PriceHistory,
    Purchase,
    Queue,
    QueueStatus,
    Search,
    Seller,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class QueueTransitionError(ValueError):
    """Raised when a queue item cannot take the requested lifecycle transition."""


class StaleQueueUpdateError(QueueTransitionError):
    """Raised when a reviewer submits an old queue version."""

ModelType = TypeVar("ModelType", bound=SQLModel)


def _coerce_uuid(value: UUID | str | None) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    return UUID(value)


class DatabaseRepository(Generic[ModelType]):
    def __init__(
        self,
        model_type: type[ModelType],
        database_url: Optional[str] = None,
        *,
        session: Optional[Session] = None,
        session_factory: Optional[Callable[[], Session]] = None,
    ) -> None:
        self.model_type = model_type
        self.database_url = database_url
        self._session = session
        self._session_factory = session_factory or (
            lambda: get_session(database_url, expire_on_commit=False)
        )

    @contextmanager
    def session(self) -> Session:
        if self._session is not None:
            yield self._session
            return

        managed_session = self._session_factory()
        try:
            yield managed_session
            managed_session.commit()
        except SQLAlchemyError as exc:
            managed_session.rollback()
            logger.exception(
                "Database operation failed for %s", self.model_type.__name__
            )
            raise exc
        finally:
            managed_session.close()

    def create(self, instance: ModelType, *, refresh: bool = True) -> ModelType:
        logger.debug("Creating %s", self.model_type.__name__)
        with self.session() as session:
            session.add(instance)
            session.flush()
            if refresh:
                session.refresh(instance)
            return instance

    def bulk_create(self, instances: list[ModelType]) -> list[ModelType]:
        if not instances:
            return []
        logger.debug("Bulk creating %d %s records", len(instances), self.model_type.__name__)
        with self.session() as session:
            session.add_all(instances)
            session.flush()
            return instances

    def get_by_id(self, instance_id: UUID | str | None) -> Optional[ModelType]:
        normalized_id = _coerce_uuid(instance_id)
        if normalized_id is None:
            return None
        with self.session() as session:
            return session.get(self.model_type, normalized_id)

    def list(self) -> list[ModelType]:
        logger.debug("Listing %s records", self.model_type.__name__)
        with self.session() as session:
            statement = select(self.model_type)
            return list(session.exec(statement).all())

    def list_page(self, *, offset: int, limit: int) -> tuple[list[ModelType], int]:
        """Return a bounded, deterministic page for API consumers."""
        with self.session() as session:
            total = session.exec(
                select(func.count()).select_from(self.model_type)
            ).one()
            statement = select(self.model_type).order_by(
                self.model_type.created_at.desc(), self.model_type.id.desc()
            ).offset(offset).limit(limit)
            return list(session.exec(statement).all()), total

    def update(
        self,
        instance_id: UUID | str | None,
        values: dict[str, Any],
        *,
        refresh: bool = True,
    ) -> Optional[ModelType]:
        normalized_id = _coerce_uuid(instance_id)
        if normalized_id is None:
            return None
        logger.debug("Updating %s %s", self.model_type.__name__, instance_id)
        try:
            with self.session() as session:
                instance = session.get(self.model_type, normalized_id)
                if instance is None:
                    return None
                for key, value in values.items():
                    setattr(instance, key, value)
                # update the updated_at timestamp if it exists
                if hasattr(instance, "updated_at"):
                    instance.updated_at = datetime.now(timezone.utc)
                session.add(instance)
                session.flush()
                if refresh:
                    session.refresh(instance)
                return instance
        except StaleDataError as exc:
            logger.error(
                "Optimistic locking failure for %s %s",
                self.model_type.__name__,
                instance_id,
            )
            raise exc

    def delete(self, instance_id: UUID | str | None) -> bool:
        normalized_id = _coerce_uuid(instance_id)
        if normalized_id is None:
            return False
        logger.debug("Deleting %s %s", self.model_type.__name__, instance_id)
        try:
            with self.session() as session:
                instance = session.get(self.model_type, normalized_id)
                if instance is None:
                    return False
                session.delete(instance)
                session.flush()
                return True
        except StaleDataError as exc:
            logger.error(
                "Optimistic locking failure during delete for %s %s",
                self.model_type.__name__,
                instance_id,
            )
            raise exc

    def commit(self) -> None:
        if self._session is not None:
            self._session.commit()


class SellerRepository(DatabaseRepository[Seller]):
    def __init__(
        self, database_url: Optional[str] = None, *, session: Optional[Session] = None
    ) -> None:
        super().__init__(Seller, database_url=database_url, session=session)


class SearchRepository(DatabaseRepository[Search]):
    def __init__(
        self, database_url: Optional[str] = None, *, session: Optional[Session] = None
    ) -> None:
        super().__init__(Search, database_url=database_url, session=session)


class ListingRepository(DatabaseRepository[Listing]):
    def __init__(
        self, database_url: Optional[str] = None, *, session: Optional[Session] = None
    ) -> None:
        super().__init__(Listing, database_url=database_url, session=session)

    def list_by_status(self, status: ListingStatus) -> list[Listing]:
        logger.debug(
            "Listing %s records for status %s", self.model_type.__name__, status
        )
        with self.session() as session:
            statement = select(Listing).where(Listing.status == status)
            return list(session.exec(statement).all())

    def list_page(
        self,
        *,
        offset: int,
        limit: int,
        status: ListingStatus | None = None,
        source: str | None = None,
        category: str | None = None,
    ) -> tuple[list[Listing], int]:
        with self.session() as session:
            filters = []
            if status is not None:
                filters.append(Listing.status == status)
            if source is not None:
                filters.append(Listing.source == source)
            if category is not None:
                filters.append(Listing.category == category)
            total = session.exec(
                select(func.count()).select_from(Listing).where(*filters)
            ).one()
            statement = (
                select(Listing)
                .where(*filters)
                .order_by(Listing.created_at.desc(), Listing.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(session.exec(statement).all()), total

    def get_by_external_id(
        self, external_id: str | None, source: str | None = None
    ) -> Optional[Listing]:
        if external_id is None:
            return None
        with self.session() as session:
            statement = select(Listing).where(Listing.external_id == external_id)
            if source is not None:
                statement = statement.where(Listing.source == source)
            return session.exec(statement).first()

    def update_from_observation(self, listing: Listing) -> Listing:
        """Update mutable observed facts while preserving source identity and status."""
        if listing.id is None:
            raise ValueError("listing.id is required")
        values = {
            "title": listing.title,
            "description": listing.description,
            "price": listing.price,
            "url": listing.url,
            "category": listing.category,
            "flip_score": listing.flip_score,
            "keyword_score": listing.keyword_score,
            "seller_id": listing.seller_id,
            "search_id": listing.search_id,
        }
        updated = self.update(listing.id, values)
        if updated is None:
            raise LookupError(f"Listing {listing.id} no longer exists")
        return updated


class PriceHistoryRepository(DatabaseRepository[PriceHistory]):
    def __init__(
        self, database_url: Optional[str] = None, *, session: Optional[Session] = None
    ) -> None:
        super().__init__(PriceHistory, database_url=database_url, session=session)

    def list_for_listing(self, listing_id: UUID | str | None) -> list[PriceHistory]:
        normalized_id = _coerce_uuid(listing_id)
        if normalized_id is None:
            return []
        logger.info("Listing price history for listing %s", listing_id)
        with self.session() as session:
            statement = (
                select(PriceHistory)
                .where(PriceHistory.listing_id == normalized_id)
                .order_by(PriceHistory.observed_at, PriceHistory.created_at)
            )
            return list(session.exec(statement).all())

    def record_observation(self, listing_id: UUID, price: float) -> PriceHistory:
        """Record a price only when it differs from the latest observation."""
        with self.session() as session:
            statement = (
                select(PriceHistory)
                .where(PriceHistory.listing_id == listing_id)
                .order_by(PriceHistory.observed_at.desc(), PriceHistory.created_at.desc())
            )
            latest = session.exec(statement).first()
            if latest is not None and latest.price == price:
                return latest
            entry = PriceHistory(price=price, listing_id=listing_id)
            session.add(entry)
            session.flush()
            session.refresh(entry)
            return entry


class NotificationDeliveryRepository(DatabaseRepository[NotificationDelivery]):
    def __init__(
        self, database_url: Optional[str] = None, *, session: Optional[Session] = None
    ) -> None:
        super().__init__(NotificationDelivery, database_url=database_url, session=session)

    def get(self, dedupe_key: str, provider: str) -> Optional[NotificationDelivery]:
        with self.session() as session:
            statement = select(NotificationDelivery).where(
                NotificationDelivery.dedupe_key == dedupe_key,
                NotificationDelivery.provider == provider,
            )
            return session.exec(statement).first()

    def claim(self, delivery: NotificationDelivery) -> NotificationDelivery | None:
        """Claim a provider delivery once; failed claims are retryable."""
        existing = self.get(delivery.dedupe_key, delivery.provider)
        if existing is not None:
            if existing.status != "failed":
                return None
            with self.session() as session:
                result = session.execute(
                    sqlalchemy_update(NotificationDelivery)
                    .where(
                        NotificationDelivery.id == existing.id,
                        NotificationDelivery.status == "failed",
                    )
                    .values(status="pending", error=None)
                )
                if result.rowcount != 1:
                    return None
                session.flush()
                return session.get(NotificationDelivery, existing.id)
        try:
            return self.create(delivery)
        except IntegrityError:
            if self._session is not None:
                self._session.rollback()
            return None

    def mark_succeeded(self, delivery_id: UUID | str) -> Optional[NotificationDelivery]:
        return self.update(
            delivery_id,
            {
                "status": "succeeded",
                "error": None,
                "delivered_at": datetime.now(timezone.utc),
            },
        )

    def mark_failed(
        self, delivery_id: UUID | str, error: str
    ) -> Optional[NotificationDelivery]:
        return self.update(delivery_id, {"status": "failed", "error": error})


class OpportunityRepository(DatabaseRepository[Opportunity]):
    def __init__(
        self, database_url: Optional[str] = None, *, session: Optional[Session] = None
    ) -> None:
        super().__init__(Opportunity, database_url=database_url, session=session)

    def create(self, instance: Opportunity) -> Opportunity:
        """Persist an opportunity and place it in manual review immediately."""
        opportunity = super().create(instance)
        if opportunity.id is not None:
            QueueRepository(self.database_url, session=self._session).enqueue(
                opportunity.id
            )
        return opportunity

    def get_or_create_for_listing(self, instance: Opportunity) -> Opportunity:
        """Return the existing opportunity or persist one for this listing."""
        if instance.listing_id is None:
            return self.create(instance)
        existing = self.list_for_listing(instance.listing_id)
        if existing:
            return existing[0]
        return self.create(instance)

    def list_for_listing(self, listing_id: UUID | str | None) -> list[Opportunity]:
        normalized_id = _coerce_uuid(listing_id)
        if normalized_id is None:
            return []
        logger.info("Listing opportunities for listing %s", listing_id)
        with self.session() as session:
            statement = select(Opportunity).where(
                Opportunity.listing_id == normalized_id
            )
            return list(session.exec(statement).all())

    def list_page(
        self,
        *,
        offset: int,
        limit: int,
        listing_id: UUID | None = None,
        min_confidence: float | None = None,
    ) -> tuple[list[Opportunity], int]:
        with self.session() as session:
            filters = []
            if listing_id is not None:
                filters.append(Opportunity.listing_id == listing_id)
            if min_confidence is not None:
                filters.append(Opportunity.confidence_score >= min_confidence)
            total = session.exec(
                select(func.count()).select_from(Opportunity).where(*filters)
            ).one()
            statement = (
                select(Opportunity)
                .where(*filters)
                .order_by(Opportunity.created_at.desc(), Opportunity.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(session.exec(statement).all()), total


class QueueRepository(DatabaseRepository[Queue]):
    """Persist and transition opportunities through manual review."""

    def __init__(
        self, database_url: Optional[str] = None, *, session: Optional[Session] = None
    ) -> None:
        super().__init__(Queue, database_url=database_url, session=session)

    def list_by_status(self, status: QueueStatus) -> list[Queue]:
        with self.session() as session:
            statement = (
                select(Queue).where(Queue.status == status).order_by(Queue.created_at)
            )
            return list(session.exec(statement).all())

    def list_page(
        self,
        *,
        offset: int,
        limit: int,
        status: QueueStatus | None = None,
    ) -> tuple[list[Queue], int]:
        with self.session() as session:
            filters = [Queue.status == status] if status is not None else []
            total = session.exec(
                select(func.count()).select_from(Queue).where(*filters)
            ).one()
            statement = (
                select(Queue)
                .where(*filters)
                .order_by(Queue.created_at.desc(), Queue.id.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(session.exec(statement).all()), total

    def get_for_opportunity(self, opportunity_id: UUID | str | None) -> Optional[Queue]:
        normalized_id = _coerce_uuid(opportunity_id)
        if normalized_id is None:
            return None
        with self.session() as session:
            statement = select(Queue).where(Queue.opportunity_id == normalized_id)
            return session.exec(statement).first()

    def enqueue(self, opportunity_id: UUID | str) -> Queue:
        """Create the single queue item for an opportunity, if needed."""
        normalized_id = _coerce_uuid(opportunity_id)
        if normalized_id is None:
            raise ValueError("opportunity_id is required")
        with self.session() as session:
            statement = select(Queue).where(Queue.opportunity_id == normalized_id)
            existing = session.exec(statement).one_or_none()
            if existing is not None:
                return existing
            item = Queue(opportunity_id=normalized_id)
            session.add(item)
            session.flush()
            session.refresh(item)
            return item

    def review(
        self, queue_id: UUID | str | None, notes: Optional[str] = None, *, expected_version: int | None = None
    ) -> Optional[Queue]:
        return self._transition(queue_id, QueueStatus.REVIEWING, notes, expected_version=expected_version)

    def approve(
        self, queue_id: UUID | str | None, notes: Optional[str] = None, *, expected_version: int | None = None
    ) -> Optional[Queue]:
        return self._transition(queue_id, QueueStatus.APPROVED, notes, expected_version=expected_version)

    def reject(
        self, queue_id: UUID | str | None, notes: Optional[str] = None, *, expected_version: int | None = None
    ) -> Optional[Queue]:
        return self._transition(queue_id, QueueStatus.REJECTED, notes, expected_version=expected_version)

    def archive(
        self, queue_id: UUID | str | None, notes: Optional[str] = None, *, expected_version: int | None = None
    ) -> Optional[Queue]:
        return self._transition(queue_id, QueueStatus.ARCHIVED, notes, expected_version=expected_version)

    def _transition(
        self,
        queue_id: UUID | str | None,
        status: QueueStatus,
        notes: Optional[str],
        *,
        expected_version: int | None = None,
    ) -> Optional[Queue]:
        if queue_id is None:
            return None
        with self.session() as session:
            item = session.get(Queue, _coerce_uuid(queue_id))
            if item is None:
                return None
            allowed = {
                QueueStatus.NEW: {QueueStatus.REVIEWING},
                QueueStatus.REVIEWING: {QueueStatus.APPROVED, QueueStatus.REJECTED},
                QueueStatus.APPROVED: {
                    QueueStatus.APPROVED,
                    QueueStatus.REJECTED,
                    QueueStatus.ARCHIVED,
                },
                QueueStatus.REJECTED: {QueueStatus.ARCHIVED},
                QueueStatus.ARCHIVED: set(),
            }
            if status not in allowed[item.status]:
                raise QueueTransitionError(
                    f"Cannot transition queue item from {item.status.value} to {status.value}"
                )
            if expected_version is not None and item.version != expected_version:
                raise StaleQueueUpdateError("Queue item version is stale")
            item.status = status
            item.reviewed_at = datetime.now(timezone.utc)
            if notes is not None:
                item.review_notes = notes
            item.updated_at = datetime.now(timezone.utc)
            session.add(item)
            try:
                session.flush()
            except StaleDataError as exc:
                raise StaleQueueUpdateError("Queue item version is stale") from exc
            session.refresh(item)
            return item


class PurchaseRepository(DatabaseRepository[Purchase]):
    def __init__(
        self, database_url: Optional[str] = None, *, session: Optional[Session] = None
    ) -> None:
        super().__init__(Purchase, database_url=database_url, session=session)

    def get_by_listing_id(self, listing_id: UUID | str | None) -> Optional[Purchase]:
        normalized_id = _coerce_uuid(listing_id)
        if normalized_id is None:
            return None
        logger.info("Fetching purchase for listing %s", listing_id)
        with self.session() as session:
            statement = select(Purchase).where(Purchase.listing_id == normalized_id)
            return session.exec(statement).one_or_none()
