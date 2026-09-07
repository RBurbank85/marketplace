from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Generic, Optional, TypeVar
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError
from sqlmodel import Session, SQLModel, select

from database.database import get_session
from database.models import (
    Listing,
    ListingStatus,
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

    def delete(self, instance_id: UUID | str | None) -> None:
        normalized_id = _coerce_uuid(instance_id)
        if normalized_id is None:
            return None
        logger.debug("Deleting %s %s", self.model_type.__name__, instance_id)
        try:
            with self.session() as session:
                instance = session.get(self.model_type, normalized_id)
                if instance is None:
                    return None
                session.delete(instance)
                session.flush()
        except StaleDataError as exc:
            logger.error(
                "Optimistic locking failure during delete for %s %s",
                self.model_type.__name__,
                instance_id,
            )
            raise exc


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
        self, queue_id: UUID | str | None, notes: Optional[str] = None
    ) -> Optional[Queue]:
        return self._transition(queue_id, QueueStatus.REVIEWING, notes)

    def approve(
        self, queue_id: UUID | str | None, notes: Optional[str] = None
    ) -> Optional[Queue]:
        return self._transition(queue_id, QueueStatus.APPROVED, notes)

    def reject(
        self, queue_id: UUID | str | None, notes: Optional[str] = None
    ) -> Optional[Queue]:
        return self._transition(queue_id, QueueStatus.REJECTED, notes)

    def archive(
        self, queue_id: UUID | str | None, notes: Optional[str] = None
    ) -> Optional[Queue]:
        return self._transition(queue_id, QueueStatus.ARCHIVED, notes)

    def _transition(
        self,
        queue_id: UUID | str | None,
        status: QueueStatus,
        notes: Optional[str],
    ) -> Optional[Queue]:
        if queue_id is None:
            return None
        values: dict[str, Any] = {
            "status": status,
            "reviewed_at": datetime.now(timezone.utc),
        }
        if notes is not None:
            values["review_notes"] = notes
        return self.update(queue_id, values)


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
