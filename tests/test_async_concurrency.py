import asyncio
import time
import pytest
from typing import Any, Iterable

from collectors.base import BaseCollector
from config.settings import Settings
from core.scheduler import SchedulerService


class SlowCollector(BaseCollector):
    def __init__(self, name: str, delay: float = 0.1):
        self.name = name
        self.delay = delay
        self.start_time = 0.0
        self.end_time = 0.0
        self.executions = 0

    async def search(self, query: str, **kwargs: Any) -> Any:
        self.start_time = time.time()
        await asyncio.sleep(self.delay)
        return [{"id": 1}]

    async def fetch(self, search_results: Any, **kwargs: Any) -> Any:
        return search_results

    async def normalize(self, item: Any, **kwargs: Any) -> Any:
        return item

    async def validate(self, item: Any, **kwargs: Any) -> bool:
        return True

    async def save(self, items: Iterable[Any], **kwargs: Any) -> Any:
        self.end_time = time.time()
        self.executions += 1
        return list(items)

    async def run(self, query: str, **kwargs: Any) -> Any:
        self.start_time = time.time()
        await asyncio.sleep(self.delay)
        self.end_time = time.time()
        self.executions += 1
        return self.executions


class FlakyCollector(SlowCollector):
    def __init__(self, name: str, failures: int) -> None:
        super().__init__(name)
        self.failures = failures

    async def run(self, query: str, **kwargs: Any) -> Any:
        self.executions += 1
        if self.executions <= self.failures:
            raise RuntimeError("temporary failure")
        return self.executions


class FailingCollector(FlakyCollector):
    def __init__(self, name: str) -> None:
        super().__init__(name, failures=999)


@pytest.mark.asyncio
async def test_collectors_run_concurrently():
    # Setup two collectors
    c1 = SlowCollector("c1", delay=0.2)
    c2 = SlowCollector("c2", delay=0.2)

    settings = Settings(enabled_collectors=["c1", "c2"], max_concurrent_collectors=5)
    service = SchedulerService(settings=settings, collectors={"c1": c1, "c2": c2})

    # Run both jobs "at the same time" (not using APScheduler here for simplicity, testing SchedulerService logic)
    start = time.time()
    results = await asyncio.gather(service.run_job("c1"), service.run_job("c2"))
    duration = time.time() - start

    assert results[0]["status"] == "success"
    assert results[1]["status"] == "success"
    # If they ran sequentially, duration would be >= 0.4
    # If they ran concurrently, duration would be ~0.2
    assert duration < 0.35
    assert c1.executions == 1
    assert c2.executions == 1


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency():
    # Setup three collectors, but limit concurrency to 2
    c1 = SlowCollector("c1", delay=0.2)
    c2 = SlowCollector("c2", delay=0.2)
    c3 = SlowCollector("c3", delay=0.2)

    settings = Settings(
        enabled_collectors=["c1", "c2", "c3"], max_concurrent_collectors=2
    )
    service = SchedulerService(
        settings=settings, collectors={"c1": c1, "c2": c2, "c3": c3}
    )

    start = time.time()
    results = await asyncio.gather(
        service.run_job("c1"), service.run_job("c2"), service.run_job("c3")
    )
    duration = time.time() - start

    assert all(r["status"] == "success" for r in results)
    # With limit 2, c1 and c2 run concurrently (~0.2s), then c3 runs (~0.2s). Total ~0.4s
    assert duration >= 0.4
    assert duration < 0.6
    assert c1.executions == 1
    assert c2.executions == 1
    assert c3.executions == 1


@pytest.mark.asyncio
async def test_overlap_protection_prevents_same_collector_twice():
    c1 = SlowCollector("c1", delay=0.2)
    settings = Settings(enabled_collectors=["c1"], max_concurrent_collectors=5)
    service = SchedulerService(settings=settings, collectors={"c1": c1})

    # Start first job, then try to start second job before first finishes
    task1 = asyncio.create_task(service.run_job("c1"))
    await asyncio.sleep(0.05)  # Ensure task1 has started and acquired the lock
    task2 = asyncio.create_task(service.run_job("c1"))

    results = await asyncio.gather(task1, task2)

    assert results[0]["status"] == "success"
    assert results[1]["status"] == "skipped"
    assert c1.executions == 1


@pytest.mark.asyncio
async def test_retry_count_and_success_metric() -> None:
    collector = FlakyCollector("flaky", failures=1)
    settings = Settings(enabled_collectors=["flaky"])
    service = SchedulerService(
        settings=settings,
        collectors={"flaky": collector},
        retry_attempts=2,
        retry_backoff_base_seconds=0,
    )

    result = await service.run_job("flaky")

    assert result["status"] == "success"
    assert result["attempts"] == 2
    assert service.metrics[-1]["status"] == "success"
    assert service.metrics[-1]["attempts"] == 2


@pytest.mark.asyncio
async def test_failure_metric_reports_exhausted_retries() -> None:
    collector = FailingCollector("failing")
    settings = Settings(enabled_collectors=["failing"])
    service = SchedulerService(
        settings=settings,
        collectors={"failing": collector},
        retry_attempts=2,
        retry_backoff_base_seconds=0,
    )

    result = await service.run_job("failing")

    assert result["status"] == "failed"
    assert result["attempts"] == 2
    assert service.metrics[-1]["status"] == "failed"
    assert service.metrics[-1]["attempts"] == 2
    assert service.metrics[-1]["error"] == "temporary failure"
