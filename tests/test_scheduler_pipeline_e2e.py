from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from alerts.notifications import Notification, NotificationService
from collectors.craigslist import CraigslistCollector
from config.settings import CollectorConfig, Settings
from core.scheduler import SchedulerService
from database.database import initialize_database
from database.repositories import (
    ListingRepository,
    NotificationDeliveryRepository,
    OpportunityRepository,
    PriceHistoryRepository,
    QueueRepository,
)
from analysis.valuation.estimator import ValuationResult


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "craigslist_search.html"


class FixtureCraigslistCollector(CraigslistCollector):
    async def fetch(self, search_results: Any, **kwargs: Any) -> list[dict[str, Any]]:
        items = await super().fetch(search_results, **kwargs)
        items.append(
            {
                "title": "",
                "price": "$0",
                "external_id": "invalid-fixture-listing",
                "url": "https://sfbay.craigslist.org/invalid-fixture-listing.html",
            }
        )
        return items


class FailingNotification(Notification):
    name = "failing"

    def send(self, alert) -> None:
        raise RuntimeError("provider unavailable")


def _settings(database_url: str, *, notifications_enabled: bool = False) -> Settings:
    return Settings(
        database_url=database_url,
        enabled_collectors=["craigslist"],
        minimum_flipscore=0,
        minimum_expected_profit=0,
        notifications_enabled=notifications_enabled,
        notification_requires_approval=False,
        collector_configs={
            "craigslist": CollectorConfig(
                queries=["camera"], fixture_path=str(FIXTURE_PATH)
            )
        },
    )


@pytest.mark.asyncio
async def test_craigslist_fixture_flows_through_idempotent_review_pipeline(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "analysis.valuation.estimator.estimate_value",
        lambda listing: ValuationResult(estimated_market_value=1000, confidence=0.9),
    )
    database_url = str(tmp_path / "craigslist-pipeline.db")
    initialize_database(database_url)
    collector = FixtureCraigslistCollector(
        database_url=database_url, obey_robots=False, request_delay=0
    )
    service = SchedulerService(
        settings=_settings(database_url),
        collectors={"craigslist": collector},
        retry_attempts=1,
    )

    first = await service.run_job("craigslist")
    second = await service.run_job("craigslist")

    assert first["status"] == second["status"] == "success"
    assert first["discovered"] == second["discovered"] == 3
    assert first["persisted"] == 3
    assert second["persisted"] == 0
    assert len(ListingRepository(database_url=database_url).list()) == 3
    assert len(PriceHistoryRepository(database_url=database_url).list()) == 3
    assert len(OpportunityRepository(database_url=database_url).list()) == 3
    assert len(QueueRepository(database_url=database_url).list()) == 3
    assert NotificationDeliveryRepository(database_url=database_url).list() == []


@pytest.mark.asyncio
async def test_notification_failure_keeps_committed_fixture_records(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "analysis.valuation.estimator.estimate_value",
        lambda listing: ValuationResult(estimated_market_value=1000, confidence=0.9),
    )
    database_url = str(tmp_path / "craigslist-notification.db")
    initialize_database(database_url)
    collector = FixtureCraigslistCollector(
        database_url=database_url, obey_robots=False, request_delay=0
    )
    service = SchedulerService(
        settings=_settings(database_url, notifications_enabled=True),
        collectors={"craigslist": collector},
        notification_service=NotificationService([FailingNotification()]),
        retry_attempts=1,
    )

    result = await service.run_job("craigslist")

    assert result["status"] == "failed"
    assert "provider unavailable" in result["error"]
    assert len(ListingRepository(database_url=database_url).list()) == 1
    assert len(OpportunityRepository(database_url=database_url).list()) == 1
    assert len(QueueRepository(database_url=database_url).list()) == 1
    assert NotificationDeliveryRepository(database_url=database_url).list() == []
