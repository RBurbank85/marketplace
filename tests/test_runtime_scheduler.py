import pytest
from typing import Any

from typer.testing import CliRunner

from app.main import app
from collectors.base import BaseCollector
from config.settings import Settings
from core.scheduler import SchedulerService
from core.scheduler_backends import FutureCeleryBackend, FutureRQBackend


class RecordingCollector(BaseCollector):
    name = "recording"

    def __init__(self, *, fail_once: bool = False) -> None:
        self.calls = 0
        self.fail_once = fail_once

    async def search(self, query: str, **kwargs: Any) -> Any:
        return []

    async def fetch(self, search_results: Any, **kwargs: Any) -> Any:
        return []

    async def normalize(self, item: Any, **kwargs: Any) -> Any:
        return item

    async def validate(self, item: Any, **kwargs: Any) -> bool:
        return True

    async def save(self, items: Any, **kwargs: Any) -> Any:
        self.calls += 1
        return list(items)

    async def run(self, query: str, **kwargs: Any) -> Any:
        if self.fail_once and self.calls == 0:
            self.calls += 1
            raise RuntimeError("boom")
        self.calls += 1
        return self.calls


class ConfigRecordingCollector(RecordingCollector):
    name = "configured-recording"

    def __init__(self) -> None:
        super().__init__()
        self.run_arguments: list[tuple[str, dict[str, Any]]] = []

    async def run(self, query: str, **kwargs: Any) -> Any:
        self.run_arguments.append((query, kwargs))
        return await super().run(query, **kwargs)


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []
        self.started = False

    def schedule(self, func, **kwargs: Any) -> str:
        job_id = kwargs.get("job_id") or str(len(self.jobs))
        self.jobs.append({"func": func, "id": job_id, **kwargs})
        return job_id

    def cancel(self, job_id: str) -> bool:
        self.jobs = [job for job in self.jobs if job.get("id") != job_id]
        return True

    def start(self) -> None:
        self.started = True

    def stop(self, wait: bool = True) -> None:
        self.started = False

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass

    def status(self) -> dict[str, Any]:
        return {"running": self.started, "jobs_count": len(self.jobs)}


@pytest.mark.asyncio
async def test_scheduler_executes_enabled_collectors_and_records_metrics() -> None:
    collector = RecordingCollector()
    settings = Settings(enabled_collectors=["recording"], search_interval=2)
    service = SchedulerService(
        settings=settings,
        collectors={"recording": collector},
        backend=FakeScheduler(),
    )

    service.start()
    result = await service.run_job("recording")

    assert collector.calls == 1
    assert result["status"] == "success"
    assert result["collector"] == "recording"
    assert service.metrics[-1]["status"] == "success"


@pytest.mark.asyncio
async def test_scheduler_passes_configured_queries_and_locations() -> None:
    collector = ConfigRecordingCollector()
    settings = Settings(
        enabled_collectors=[collector.name],
        collector_configs={
            collector.name: {
                "queries": ["guitar", "camera"],
                "locations": ["seattle", "portland"],
                "pagination_limit": 4,
                "request_timeout": 7.5,
                "rate_limit_per_minute": 12,
                "credentials": {"token": "secret"},
            }
        },
    )
    service = SchedulerService(
        settings=settings,
        collectors={collector.name: collector},
        backend=FakeScheduler(),
        retry_attempts=1,
    )

    result = await service.run_job(collector.name)

    assert result["status"] == "success"
    assert [query for query, _ in collector.run_arguments] == [
        "guitar",
        "guitar",
        "camera",
        "camera",
    ]
    assert {kwargs["location"] for _, kwargs in collector.run_arguments} == {
        "seattle",
        "portland",
    }
    assert collector.run_arguments[0][1]["pagination_limit"] == 4
    assert collector.run_arguments[0][1]["credentials"] == {"token": "secret"}


@pytest.mark.asyncio
async def test_scheduler_uses_empty_query_and_default_config_when_unconfigured() -> None:
    collector = ConfigRecordingCollector()
    settings = Settings(enabled_collectors=[collector.name])
    service = SchedulerService(
        settings=settings,
        collectors={collector.name: collector},
        backend=FakeScheduler(),
        retry_attempts=1,
    )

    await service.run_job(collector.name)

    assert collector.run_arguments == [("", {})]


@pytest.mark.asyncio
async def test_scheduler_skips_overlapping_jobs() -> None:
    collector = RecordingCollector()
    settings = Settings(enabled_collectors=["recording"], search_interval=2)
    service = SchedulerService(
        settings=settings,
        collectors={"recording": collector},
        backend=FakeScheduler(),
    )

    async with service._job_locks["recording"]:
        result = await service._run_job_safe("recording")

    assert result["status"] == "skipped"
    assert collector.calls == 0


@pytest.mark.asyncio
async def test_scheduler_retries_failed_jobs_with_backoff(monkeypatch: Any) -> None:
    collector = RecordingCollector(fail_once=True)
    settings = Settings(enabled_collectors=["recording"], search_interval=2)
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("core.scheduler.asyncio.sleep", fake_sleep)

    service = SchedulerService(
        settings=settings,
        collectors={"recording": collector},
        backend=FakeScheduler(),
        retry_attempts=2,
        retry_backoff_base_seconds=1.0,
    )

    result = await service._execute_collector("recording")

    assert collector.calls == 2
    assert result["status"] == "success"
    assert sleeps == [1.0]


def test_scheduler_cli_exposes_status_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["scheduler", "status"])

    assert result.exit_code == 0
    assert "Scheduler" in result.output


def test_scheduler_cli_run_awaits_async_service(monkeypatch: Any) -> None:
    class FakeScheduler:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def run_job(self, collector_name: str) -> dict[str, Any]:
            return {"collector": collector_name, "status": "success"}

    monkeypatch.setattr("app.main.SchedulerService", FakeScheduler)
    result = CliRunner().invoke(app, ["scheduler", "run", "recording"])

    assert result.exit_code == 0
    assert "recording: success" in result.output


@pytest.mark.parametrize("backend_type", [FutureCeleryBackend, FutureRQBackend])
def test_deferred_scheduler_backends_report_unsupported(backend_type: Any) -> None:
    backend = backend_type()

    assert backend.status() == {
        "type": backend.backend_type,
        "running": False,
        "status": "unsupported",
        "supported": False,
    }


@pytest.mark.parametrize("backend_type", [FutureCeleryBackend, FutureRQBackend])
@pytest.mark.parametrize("operation", ["start", "stop", "pause", "resume"])
def test_deferred_scheduler_lifecycle_operations_fail(
    backend_type: Any, operation: str
) -> None:
    with pytest.raises(NotImplementedError, match="not supported"):
        getattr(backend_type(), operation)()


@pytest.mark.parametrize("backend_type", [FutureCeleryBackend, FutureRQBackend])
def test_deferred_scheduler_job_operations_fail(backend_type: Any) -> None:
    backend = backend_type()

    with pytest.raises(NotImplementedError, match="not supported"):
        backend.schedule(lambda: None)
    with pytest.raises(NotImplementedError, match="not supported"):
        backend.cancel("job-id")
