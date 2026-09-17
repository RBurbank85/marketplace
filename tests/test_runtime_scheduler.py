import pytest
from typing import Any

from typer.testing import CliRunner

from api import deps
from api.main import app as api_app
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
        self.start_calls = 0
        self.stop_calls = 0

    def schedule(self, func, **kwargs: Any) -> str:
        job_id = kwargs.get("job_id") or str(len(self.jobs))
        self.jobs.append({"func": func, "id": job_id, **kwargs})
        return job_id

    def cancel(self, job_id: str) -> bool:
        self.jobs = [job for job in self.jobs if job.get("id") != job_id]
        return True

    def start(self) -> None:
        self.start_calls += 1
        self.started = True

    def stop(self, wait: bool = True) -> None:
        self.stop_calls += 1
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
    settings = Settings(enabled_collectors=["recording"], search_interval=2, enabled_categories=[])
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
async def test_scheduler_manual_run_uses_injected_fake_collector() -> None:
    collector = RecordingCollector()
    service = SchedulerService(
        settings=Settings(enabled_collectors=[collector.name], enabled_categories=[]),
        collectors={collector.name: collector},
        backend=FakeScheduler(),
    )

    result = await service.run_job(collector.name)

    assert result["status"] == "success"
    assert collector.calls == 1


def test_scheduler_start_and_stop_are_idempotent() -> None:
    backend = FakeScheduler()
    service = SchedulerService(
        settings=Settings(enabled_collectors=["recording"]),
        collectors={"recording": RecordingCollector()},
        backend=backend,
    )

    service.start()
    service.start()
    service.stop()
    service.stop()

    assert backend.start_calls == 1
    assert backend.stop_calls == 1


@pytest.mark.asyncio
async def test_fastapi_lifespan_autostarts_and_stops_shared_scheduler(
    monkeypatch: Any,
) -> None:
    backend = FakeScheduler()
    service_settings = Settings(
        scheduler_autostart=True, enabled_collectors=["recording"]
    )
    service = SchedulerService(
        settings=service_settings,
        collectors={"recording": RecordingCollector()},
        backend=backend,
    )
    monkeypatch.setattr("api.main.initialize_database", lambda: None)
    monkeypatch.setattr(deps, "_scheduler_service", service)
    monkeypatch.setattr(deps.settings, "scheduler_autostart", True)

    async with api_app.router.lifespan_context(api_app):
        assert api_app.state.scheduler_service is service
        assert backend.started is True

    assert backend.started is False
    assert backend.start_calls == 1
    assert backend.stop_calls == 1


@pytest.mark.asyncio
async def test_fastapi_lifespan_does_not_start_scheduler_when_disabled(
    monkeypatch: Any,
) -> None:
    backend = FakeScheduler()
    service = SchedulerService(
        settings=Settings(scheduler_autostart=False, enabled_collectors=["recording"]),
        collectors={"recording": RecordingCollector()},
        backend=backend,
    )
    monkeypatch.setattr("api.main.initialize_database", lambda: None)
    monkeypatch.setattr(deps, "_scheduler_service", service)
    monkeypatch.setattr(deps.settings, "scheduler_autostart", False)

    async with api_app.router.lifespan_context(api_app):
        assert backend.started is False

    assert backend.start_calls == 0
    assert backend.stop_calls == 0


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
    assert collector.run_arguments[0][1]["request_timeout"] == 7.5
    assert collector.run_arguments[0][1]["rate_limit_per_minute"] == 12
    assert collector.run_arguments[0][1]["credentials"] == {"token": "secret"}


@pytest.mark.asyncio
async def test_scheduler_uses_empty_query_and_default_config_when_unconfigured() -> None:
    collector = ConfigRecordingCollector()
    settings = Settings(enabled_collectors=[collector.name], enabled_categories=[])
    service = SchedulerService(
        settings=settings,
        collectors={collector.name: collector},
        backend=FakeScheduler(),
        retry_attempts=1,
    )

    await service.run_job(collector.name)

    assert collector.run_arguments == [("", {})]


@pytest.mark.asyncio
async def test_scheduler_uses_fallback_config_from_enabled_categories() -> None:
    collector = ConfigRecordingCollector()
    settings = Settings(
        enabled_collectors=[collector.name],
        enabled_categories=["electronics", "tools"],
    )
    service = SchedulerService(
        settings=settings,
        collectors={collector.name: collector},
        backend=FakeScheduler(),
        retry_attempts=1,
    )

    await service.run_job(collector.name)

    queries = [query for query, _ in collector.run_arguments]
    assert queries == ["electronics", "tools"]


@pytest.mark.asyncio
async def test_scheduler_passes_obey_robots_from_collector_config() -> None:
    from collectors.craigslist import CraigslistCollector
    from config.settings import CollectorConfig as Cfg
    from core.identity import identity_service

    settings = Settings(
        enabled_collectors=["craigslist"],
        enabled_categories=[],
        collector_configs={
            "craigslist": Cfg(queries=["test"], obey_robots=False),
        },
    )
    service = SchedulerService(
        settings=settings,
        collectors={},
        backend=FakeScheduler(),
    )

    collector = service._instantiate_collector(CraigslistCollector, "craigslist")
    assert collector is not None
    pol = identity_service.get_policy("craigslist")
    assert pol.obey_robots is False


@pytest.mark.asyncio
async def test_scheduler_passes_base_url_from_collector_config() -> None:
    from collectors.ebay import EbayCollector
    from config.settings import CollectorConfig as Cfg

    settings = Settings(
        enabled_collectors=["ebay"],
        enabled_categories=[],
        collector_configs={
            "ebay": Cfg(
                queries=["test"],
                base_url="https://api.sandbox.ebay.com",
                credentials={
                    "client_id": "sandbox-app-id",
                    "client_secret": "sandbox-cert-id",
                },
            ),
        },
    )
    service = SchedulerService(
        settings=settings,
        collectors={},
        backend=FakeScheduler(),
    )

    collector = service._instantiate_collector(EbayCollector, "ebay")
    assert isinstance(collector, EbayCollector)
    assert collector.base_url == "https://api.sandbox.ebay.com"
    assert collector.token_url.startswith("https://api.sandbox.ebay.com")
    assert collector.search_url.startswith("https://api.sandbox.ebay.com")


def test_scheduler_passes_expand_searches_in_execution_parameters() -> None:
    from config.settings import CollectorConfig as Cfg

    config = Cfg(queries=["receiver", "guitar"], expand_searches=True)
    params = SchedulerService._collector_execution_parameters(config)

    assert len(params) == 2
    for _query, kwargs in params:
        assert kwargs["expand_searches"] is True

    # Defaults to False when not set
    default_config = Cfg(queries=["test"])
    default_params = SchedulerService._collector_execution_parameters(default_config)
    assert default_params[0][1]["expand_searches"] is False


@pytest.mark.asyncio
async def test_scheduler_skips_overlapping_jobs() -> None:
    collector = RecordingCollector()
    settings = Settings(enabled_collectors=["recording"], search_interval=2, enabled_categories=[])
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
    settings = Settings(enabled_collectors=["recording"], search_interval=2, enabled_categories=[])
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
