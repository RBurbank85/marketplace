from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from core.events.base import ListingDiscovered


def test_listing_event_preserves_fields_and_json_serialization() -> None:
    event_id = UUID("11111111-1111-1111-1111-111111111111")
    timestamp = datetime(2026, 9, 7, 12, 30, tzinfo=timezone.utc)
    event = ListingDiscovered(
        event_id=event_id,
        timestamp=timestamp,
        external_id="listing-123",
        source="fixture",
        data={"title": "Amplifier"},
    )

    assert set(ListingDiscovered.model_fields) == {
        "event_id",
        "timestamp",
        "correlation_id",
        "listing_id",
        "external_id",
        "source",
        "data",
    }
    assert event.model_dump()["event_id"] == event_id
    assert event.model_dump(mode="json") == {
        "event_id": str(event_id),
        "timestamp": "2026-09-07T12:30:00Z",
        "correlation_id": None,
        "listing_id": None,
        "external_id": "listing-123",
        "source": "fixture",
        "data": {"title": "Amplifier"},
    }


def test_event_models_remain_frozen_and_validate_required_fields() -> None:
    event = ListingDiscovered(
        external_id="listing-123",
        source="fixture",
    )

    with pytest.raises(ValidationError):
        event.source = "other"

    with pytest.raises(ValidationError):
        ListingDiscovered(source="fixture")