from __future__ import annotations

from typing import Any

import pytest

from collectors.base import BaseCollector
from config.settings import Settings
from core.events.base import (
    CollectorFailed,
    ListingDiscovered,
    ListingStored,
    ListingValidated,
)
from core.events.bus import bus
from core.scheduler import SchedulerService
from database.database import initialize_database
from database.models import Listing
from database.repositories import ListingRepository


class DatabaseFixtureCollector(BaseCollector):
    name = "database-fixture"

    def __init__(self, database_url: str) -> None:
        self.repository = ListingRepository(database_url=database_url)

    async def search(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "title": "Valid listing",
                "price": 100,
                "source": "fixture",
                "external_id": "same-id",
            },
            {
                "title": "",
                "price": 100,
                "source": "fixture",
                "external_id": "invalid-id",
            },
        ]

    async def fetch(self, search_results: Any, **kwargs: Any) -> Any:
        return search_results

    async def normalize(self, item: Any, **kwargs: Any) -> Listing:
        return Listing(**item)

    async def validate(self, item: Listing, **kwargs: Any) -> bool:
        return bool(item.title and item.price > 0 and item.external_id)

    async def save(self, items: Any, **kwargs: Any) -> list[Listing]:
        saved: list[Listing] = []
        for item in items:
            existing = self.repository.get_by_external_id(
                item.external_id, item.source
            )
            if existing is None:
                saved.append(self.repository.create(item))
        return saved


class FailingFixtureCollector(DatabaseFixtureCollector):
    name = "failing-fixture"

    async def search(self, query: str, **kwargs: Any) -> Any:
        raise RuntimeError("fixture failure")


@pytest.mark.asyncio
async def test_scheduler_collector_persists_valid_records_and_deduplicates(tmp_path) -> None:
    database_url = str(tmp_path / "collector-e2e.db")
    initialize_database(database_url)
    collector = DatabaseFixtureCollector(database_url)
    service = SchedulerService(
        settings=Settings(enabled_collectors=[collector.name]),
        collectors={collector.name: collector},
        retry_attempts=1,
    )
    events: list[Any] = []
    handlers = {
        event_type: lambda event: events.append(event)
        for event_type in (
            ListingDiscovered,
            ListingValidated,
            ListingStored,
        )
    }
    for event_type, handler in handlers.items():
        bus.subscribe(event_type, handler)

    try:
        first = await service.run_job(collector.name)
        second = await service.run_job(collector.name)
    finally:
        for event_type, handler in handlers.items():
            bus.unsubscribe(event_type, handler)

    assert first["status"] == "success"
    assert second["status"] == "success"
    assert first["discovered"] == 1
    assert first["persisted"] == 1
    assert first["skipped"] == 1
    assert second["discovered"] == 1
    assert second["persisted"] == 0
    assert second["skipped"] == 2
    assert len(ListingRepository(database_url=database_url).list()) == 1
    assert ListingRepository(database_url=database_url).get_by_external_id(
        "invalid-id", "fixture"
    ) is None
    assert len([event for event in events if isinstance(event, ListingDiscovered)]) == 2
    assert len([event for event in events if isinstance(event, ListingValidated)]) == 2
    assert len([event for event in events if isinstance(event, ListingStored)]) == 1
    assert service.metrics[-1]["status"] == "success"


@pytest.mark.asyncio
async def test_scheduler_records_collector_failure_metric(tmp_path) -> None:
    database_url = str(tmp_path / "collector-failure.db")
    initialize_database(database_url)
    collector = FailingFixtureCollector(database_url)
    service = SchedulerService(
        settings=Settings(enabled_collectors=[collector.name]),
        collectors={collector.name: collector},
        retry_attempts=1,
    )
    failures: list[CollectorFailed] = []

    def record_failure(event: CollectorFailed) -> None:
        failures.append(event)

    bus.subscribe(CollectorFailed, record_failure)

    try:
        result = await service.run_job(collector.name)
    finally:
        bus.unsubscribe(CollectorFailed, record_failure)

    assert result["status"] == "failed"
    assert result["error"] == "fixture failure"
    assert result["failed"] == 1
    assert len(failures) == 1
    assert service.metrics[-1]["status"] == "failed"
