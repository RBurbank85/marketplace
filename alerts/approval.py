from __future__ import annotations

from typing import Any
from uuid import UUID

from alerts.notifications import AlertNotification, NotificationService
from database.models import NotificationDelivery, QueueStatus
from database.repositories import (
    ListingRepository,
    NotificationDeliveryRepository,
    OpportunityRepository,
    QueueRepository,
    QueueTransitionError,
)


class ApprovedOpportunityDispatcher:
    """Deliver approved opportunities using facts reloaded from operational storage."""

    def __init__(
        self,
        notification_service: NotificationService,
        *,
        database_url: str | None = None,
        session: Any = None,
    ) -> None:
        self.notification_service = notification_service
        self.queue_repository = QueueRepository(database_url, session=session)
        self.opportunity_repository = OpportunityRepository(database_url, session=session)
        self.listing_repository = ListingRepository(database_url, session=session)
        self.delivery_repository = NotificationDeliveryRepository(
            database_url, session=session
        )

    def dispatch(self, queue_id: UUID | str) -> list[dict[str, str]]:
        queue_item = self.queue_repository.get_by_id(queue_id)
        if queue_item is None:
            raise LookupError("Queue item not found")
        if queue_item.status != QueueStatus.APPROVED:
            raise QueueTransitionError("Only approved queue items can be notified")

        opportunity = self.opportunity_repository.get_by_id(queue_item.opportunity_id)
        if opportunity is None or opportunity.listing_id is None:
            raise LookupError("Approved opportunity facts are unavailable")
        listing = self.listing_repository.get_by_id(opportunity.listing_id)
        if listing is None:
            raise LookupError("Approved listing facts are unavailable")

        alert = AlertNotification(
            title=listing.title,
            price=listing.price,
            estimated_value=opportunity.estimated_market_value
            if opportunity.estimated_market_value is not None
            else listing.price + opportunity.potential_profit,
            expected_profit=opportunity.potential_profit,
            flip_score=int(opportunity.flip_score or listing.flip_score or 0),
            confidence=opportunity.confidence_score,
            reasoning=opportunity.notes or "",
            listing_url=listing.url or "",
            dedupe_key=str(opportunity.id),
        )
        outcomes: list[dict[str, str]] = []
        for provider in self.notification_service.providers:
            provider_name = getattr(provider, "name", provider.__class__.__name__)
            claim = self.delivery_repository.claim(
                NotificationDelivery(
                    dedupe_key=alert.dedupe_key,
                    provider=provider_name,
                    opportunity_id=opportunity.id,
                )
            )
            if claim is None:
                existing = self.delivery_repository.get(alert.dedupe_key, provider_name)
                outcomes.append(
                    {"provider": provider_name, "status": existing.status if existing else "skipped"}
                )
                continue
            try:
                provider.send(alert)
            except Exception as exc:
                self.delivery_repository.mark_failed(claim.id, str(exc))
                outcomes.append(
                    {"provider": provider_name, "status": "failed", "error": str(exc)}
                )
            else:
                self.delivery_repository.mark_succeeded(claim.id)
                outcomes.append({"provider": provider_name, "status": "succeeded"})
        return outcomes
