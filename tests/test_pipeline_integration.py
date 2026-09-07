from __future__ import annotations

import pytest

from alerts.notifications import Notification, NotificationService
from core.pipeline import PipelineEngine
from core.pipeline_stages import (
    ListingPipelineData,
    NotifyStage,
    OpportunityDetectionStage,
    PersistStage,
    QueueStage,
    ScoreStage,
    ValidateStage,
    NormalizeStage,
)
from database.database import initialize_database
from database.repositories import ListingRepository, OpportunityRepository, QueueRepository


class FailingNotification(Notification):
    def send(self, alert) -> None:
        raise RuntimeError("provider unavailable")


def _engine(database_url: str, notification_service=None) -> PipelineEngine:
    return PipelineEngine(
        [
            NormalizeStage(),
            ValidateStage(),
            PersistStage(repository=ListingRepository(database_url=database_url)),
            ScoreStage(),
            OpportunityDetectionStage(),
            QueueStage(
                opp_threshold=0,
                opportunity_repository=OpportunityRepository(database_url=database_url),
            ),
            NotifyStage(notification_service=notification_service),
        ]
    )


@pytest.mark.asyncio
async def test_valid_listing_is_persisted_queued_and_idempotent(tmp_path) -> None:
    database_url = str(tmp_path / "pipeline.db")
    initialize_database(database_url)
    raw_data = {
        "title": "Nintendo Switch OLED",
        "price": "$299.99",
        "source": "test",
        "external_id": "listing-1",
        "url": "https://example.test/listing-1",
    }

    engine = _engine(database_url)
    first = await engine.execute(ListingPipelineData(raw_data=raw_data))
    second = await engine.execute(ListingPipelineData(raw_data=raw_data))

    assert not first.terminated
    assert not second.terminated
    assert len(ListingRepository(database_url=database_url).list()) == 1
    assert len(OpportunityRepository(database_url=database_url).list()) == 1
    assert len(QueueRepository(database_url=database_url).list()) == 1


@pytest.mark.asyncio
async def test_invalid_listing_stops_before_persistence(tmp_path) -> None:
    database_url = str(tmp_path / "invalid.db")
    initialize_database(database_url)

    result = await _engine(database_url).execute(
        ListingPipelineData(
            raw_data={"title": "", "price": 0, "source": "test", "external_id": "bad"}
        )
    )

    assert result.terminated
    assert ListingRepository(database_url=database_url).list() == []


@pytest.mark.asyncio
async def test_notification_failure_is_visible_after_database_commit(tmp_path) -> None:
    database_url = str(tmp_path / "notification.db")
    initialize_database(database_url)

    result = await _engine(
        database_url, NotificationService([FailingNotification()])
    ).execute(
        ListingPipelineData(
            raw_data={
                "title": "Nintendo Switch OLED",
                "price": 299,
                "source": "test",
                "external_id": "listing-2",
            }
        )
    )

    assert result.terminated
    assert "provider unavailable" in result.termination_reason
    assert result.metrics[-1].success is False
    assert len(OpportunityRepository(database_url=database_url).list()) == 1