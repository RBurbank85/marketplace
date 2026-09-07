from __future__ import annotations

import pytest

from analysis.valuation import ComparableProduct, InMemoryPricingProvider
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
    ValuateStage,
)
from database.database import initialize_database
from database.repositories import (
    ListingRepository,
    OpportunityRepository,
    PriceHistoryRepository,
    QueueRepository,
)


class FailingNotification(Notification):
    def send(self, alert) -> None:
        raise RuntimeError("provider unavailable")


def _engine(database_url: str, notification_service=None) -> PipelineEngine:
    return PipelineEngine(
        [
            NormalizeStage(),
            ValidateStage(),
            PersistStage(repository=ListingRepository(database_url=database_url)),
            ValuateStage(
                providers=[
                    InMemoryPricingProvider(
                        [ComparableProduct(title="Nintendo Switch OLED", price=400)]
                    )
                ]
            ),
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
    assert first.data.enriched_data["valuation_available"] is True
    assert first.data.opportunity_results["expected_profit"] == pytest.approx(100.01)


@pytest.mark.asyncio
async def test_repeated_pipeline_observation_updates_price_and_persists_facts(
    tmp_path,
) -> None:
    database_url = str(tmp_path / "repeated-observation.db")
    initialize_database(database_url)
    engine = _engine(database_url)

    await engine.execute(
        ListingPipelineData(
            raw_data={
                "title": "Nintendo Switch OLED",
                "price": 299,
                "source": "test",
                "external_id": "repeat-1",
                "category": "gaming",
            }
        )
    )
    await engine.execute(
        ListingPipelineData(
            raw_data={
                "title": "Nintendo Switch OLED price drop",
                "price": 249,
                "source": "test",
                "external_id": "repeat-1",
                "category": "gaming",
            }
        )
    )

    listing = ListingRepository(database_url).get_by_external_id("repeat-1", "test")
    assert listing is not None
    assert listing.price == 249
    assert listing.category == "gaming"
    assert listing.flip_score is not None
    assert listing.keyword_score is not None
    assert len(PriceHistoryRepository(database_url).list_for_listing(listing.id)) == 2


@pytest.mark.asyncio
async def test_pipeline_without_valuation_provider_does_not_queue(tmp_path) -> None:
    database_url = str(tmp_path / "unvalued.db")
    initialize_database(database_url)
    result = await PipelineEngine(
        [
            NormalizeStage(),
            ValidateStage(),
            PersistStage(repository=ListingRepository(database_url=database_url)),
            ValuateStage(),
            ScoreStage(),
            OpportunityDetectionStage(),
            QueueStage(
                opp_threshold=0,
                opportunity_repository=OpportunityRepository(database_url=database_url),
            ),
        ]
    ).execute(
        ListingPipelineData(
            raw_data={
                "title": "Nintendo Switch OLED",
                "price": 299,
                "source": "test",
                "external_id": "unvalued-1",
            }
        )
    )

    assert result.data.enriched_data["valuation_available"] is False
    assert result.data.enriched_data["valuation_confidence"] == 0
    assert result.metadata["queue_skip_reason"] == "valuation_unavailable"
    assert result.metadata["queue_skipped_valuation_unavailable"] == 1
    assert OpportunityRepository(database_url=database_url).list() == []


@pytest.mark.asyncio
async def test_zero_market_value_is_available_and_not_treated_as_missing(tmp_path) -> None:
    database_url = str(tmp_path / "zero-value.db")
    initialize_database(database_url)
    result = await PipelineEngine(
        [
            NormalizeStage(),
            ValidateStage(),
            PersistStage(repository=ListingRepository(database_url=database_url)),
            ValuateStage(
                providers=[
                    InMemoryPricingProvider(
                        [ComparableProduct(title="Nintendo Switch OLED", price=0)]
                    )
                ]
            ),
            ScoreStage(),
            OpportunityDetectionStage(),
            QueueStage(
                opp_threshold=0,
                opportunity_repository=OpportunityRepository(database_url=database_url),
            ),
        ]
    ).execute(
        ListingPipelineData(
            raw_data={
                "title": "Nintendo Switch OLED",
                "price": 1,
                "source": "test",
                "external_id": "zero-value-1",
            }
        )
    )

    assert result.data.enriched_data["market_value"] == 0
    assert result.data.enriched_data["valuation_available"] is True
    assert result.data.opportunity_results["expected_profit"] == -1
    assert len(OpportunityRepository(database_url=database_url).list()) == 1


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