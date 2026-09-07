from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field

class Event(BaseModel):
    """Base class for all events in the system."""
    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[UUID] = None

class ListingEvent(Event):
    """Events related to a specific listing."""
    listing_id: Optional[UUID] = None
    external_id: str
    source: str
    data: Dict[str, Any] = {}

class ListingDiscovered(ListingEvent):
    """Fired when a collector finds a new listing."""
    pass

class ListingValidated(ListingEvent):
    """Fired after a listing has passed validation checks."""
    pass

class ListingStored(ListingEvent):
    """Fired after a listing is persisted to the database."""
    listing_id: UUID

class ListingUpdated(ListingEvent):
    """Fired when an existing listing's attributes change."""
    listing_id: UUID
    changes: Dict[str, Any]

class ListingValued(ListingEvent):
    """Fired after a listing has been assigned a market value."""
    listing_id: UUID
    market_value: float
    confidence: float

class OpportunityCreated(ListingEvent):
    """Fired when a listing meets the criteria for an arbitrage opportunity."""
    listing_id: UUID
    opportunity_id: UUID
    potential_profit: float
    score: float

class OpportunityApproved(Event):
    """Fired when an opportunity is approved by a reviewer."""
    opportunity_id: UUID
    listing_id: UUID

class NotificationSent(Event):
    """Fired after a notification has been successfully delivered."""
    notification_id: UUID
    recipient: str
    channel: str

class CollectorEvent(Event):
    """Events related to collector lifecycle."""
    collector_name: str
    session_id: UUID

class CollectorStarted(CollectorEvent):
    pass

class CollectorFinished(CollectorEvent):
    listings_count: int

class CollectorFailed(CollectorEvent):
    error: str
    stack_trace: Optional[str] = None
