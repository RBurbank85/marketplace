from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Callable

from loguru import logger

from collectors.base import BaseCollector, CollectorRegistry, discover_collectors
from config.settings import Settings, settings as default_settings
from alerts.discord import DiscordNotification
from alerts.notifications import NotificationService
from core.events.base import ListingStored
from core.events.bus import bus
from core.pipeline import PipelineEngine
from core.pipeline_stages import (
    ListingPipelineData,
    NormalizeStage,
    NotifyStage,
    OpportunityDetectionStage,
    PersistStage,
    QueueStage,
    ScoreStage,
    ValidateStage,
    ValuateStage,
)
from core.scheduler_base import BaseScheduler
from core.scheduler_apscheduler import APSchedulerBackend
from database.database import initialize_database
from database.repositories import ListingRepository, OpportunityRepository
from analysis.valuation.comparables import PricingProvider


class SchedulerService:
    """Run collectors and own the single listing-processing pipeline.

    Scheduler execution is the ownership boundary for business processing. The
    event bus remains observational; subscribers must not persist, score, queue,
    or notify listings.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        collectors: dict[str, BaseCollector] | None = None,
        backend: BaseScheduler | None = None,
        notification_service: NotificationService | None = None,
        valuation_providers: Sequence[PricingProvider] = (),
        retry_attempts: int = 3,
        retry_backoff_base_seconds: float = 1.0,
    ) -> None:
        self.settings = settings or default_settings
        self.collectors = collectors or {}
        self.backend = backend or APSchedulerBackend()
        self.retry_attempts = retry_attempts
        self.retry_backoff_base_seconds = retry_backoff_base_seconds
        self._job_locks: dict[str, asyncio.Lock] = {}
        self._active_collectors: set[str] = set()
        self._started = False
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrent_collectors)
        self.metrics: list[dict[str, Any]] = []
        self._logger = logger.bind(component="scheduler_service")

        database_url = self.settings.database_url
        if database_url is None and self.collectors:
            first_collector = next(iter(self.collectors.values()))
            database_url = getattr(first_collector, "database_url", None)
            if database_url is None:
                database_url = getattr(
                    getattr(first_collector, "repository", None), "database_url", None
                )
        database_url = database_url or str(self.settings.sqlite_path)
        initialize_database(database_url)
        providers = []
        if self.settings.discord_webhook:
            providers.append(DiscordNotification(self.settings.discord_webhook))
            notification_service = notification_service or NotificationService(providers)
        self.pipeline = PipelineEngine(
            [
                NormalizeStage(),
                ValidateStage(),
                PersistStage(repository=ListingRepository(database_url=database_url)),
                ValuateStage(providers=valuation_providers),
                ScoreStage(),
                OpportunityDetectionStage(),
                QueueStage(
                    opp_threshold=70.0,
                    score_threshold=self.settings.minimum_flipscore,
                    minimum_expected_profit=self.settings.minimum_expected_profit,
                    opportunity_repository=OpportunityRepository(database_url=database_url),
                    database_url=database_url,
                ),
                NotifyStage(
                    notification_service=notification_service,
                    database_url=database_url,
                    enabled=self.settings.notifications_enabled,
                    requires_approval=self.settings.notification_requires_approval,
                ),
            ]
        )

        self._initialize_job_locks()

    def _initialize_job_locks(self) -> None:
        enabled_collectors = [
            name for name in self.settings.enabled_collectors if str(name).strip()
        ]
        for name in enabled_collectors:
            self._job_locks.setdefault(name.lower(), asyncio.Lock())

    def _resolve_collectors(self) -> dict[str, BaseCollector]:
        if self.collectors:
            return self.collectors

        for collector_cls in discover_collectors():
            collector_name = (
                getattr(collector_cls, "name", None) or collector_cls.__name__
            )
            self.collectors[collector_name.lower()] = self._instantiate_collector(
                collector_cls
            )
        return self.collectors

    def _instantiate_collector(
        self, collector_cls: type[BaseCollector]
    ) -> BaseCollector:
        parameters = inspect.signature(collector_cls).parameters
        if "database_url" not in parameters:
            return collector_cls()
        database_url = self.settings.database_url or str(self.settings.sqlite_path)
        return collector_cls(database_url=database_url)

    def _get_collector(self, collector_name: str) -> BaseCollector | None:
        normalized_name = collector_name.lower()
        resolved = self._resolve_collectors()
        collector = resolved.get(normalized_name)
        if collector is None:
            registry_cls = CollectorRegistry.get(normalized_name)
            if registry_cls is None:
                return None
            collector = self._instantiate_collector(registry_cls)
        return collector

    def start(self) -> None:
        if self._started:
            return

        self._logger.info(
            "scheduler.starting",
            enabled_collectors=list(self.settings.enabled_collectors),
            interval_minutes=self.settings.search_interval,
        )

        for collector_name in self.settings.enabled_collectors:
            normalized_name = str(collector_name).strip().lower()
            if not normalized_name:
                continue
            self._job_locks.setdefault(normalized_name, asyncio.Lock())
            self.schedule(
                self._run_job_safe,
                args=[normalized_name],
                job_id=f"collector:{normalized_name}",
                name=normalized_name,
                trigger="interval",
                minutes=self.settings.search_interval,
            )

        self.backend.start()
        self._started = True

    def stop(self, wait: bool = True) -> None:
        if not self._started:
            return
        self.backend.stop(wait=wait)
        self._started = False
        self._logger.info("scheduler.stopped")

    def shutdown(self, wait: bool = True) -> None:
        """Alias for stop() for backward compatibility."""
        self.stop(wait=wait)

    def pause(self) -> None:
        self.backend.pause()

    def resume(self) -> None:
        self.backend.resume()

    def status(self) -> dict[str, Any]:
        backend_status = self.backend.status()
        return {
            "running": backend_status.get("running", False),
            "backend": backend_status,
            "enabled_collectors": list(self.settings.enabled_collectors),
            "interval_minutes": self.settings.search_interval,
            "metrics_count": len(self.metrics),
            "latest_metrics": list(self.metrics[-3:]),
            "metrics_scope": "process-local",
            "metrics_persisted": False,
            "autostart": self.settings.scheduler_autostart,
        }

    def schedule(
        self,
        func: Callable[..., Any],
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        *,
        job_id: str | None = None,
        name: str | None = None,
        trigger: str = "interval",
        **trigger_kwargs: Any,
    ) -> str:
        return self.backend.schedule(
            func,
            args=args,
            kwargs=kwargs,
            job_id=job_id,
            name=name,
            trigger=trigger,
            **trigger_kwargs,
        )

    def cancel(self, job_id: str) -> bool:
        return self.backend.cancel(job_id)

    async def _run_job_safe(self, collector_name: str) -> dict[str, Any]:
        normalized_name = collector_name.lower()
        lock = self._job_locks.setdefault(normalized_name, asyncio.Lock())
        if lock.locked() or normalized_name in self._active_collectors:
            self._logger.info(
                "scheduler.job_skipped",
                collector=normalized_name,
                reason="already_running",
            )
            self._record_metric(
                normalized_name, "skipped", attempts=0, duration_seconds=0.0
            )
            return {"collector": normalized_name, "status": "skipped", "attempts": 0}

        self._active_collectors.add(normalized_name)
        try:
            async with lock:
                async with self._semaphore:
                    return await self._execute_collector(normalized_name)
        finally:
            self._active_collectors.discard(normalized_name)

    async def run_job(self, collector_name: str) -> dict[str, Any]:
        return await self._run_job_safe(collector_name)

    async def _execute_collector(self, collector_name: str) -> dict[str, Any]:
        collector = self._get_collector(collector_name)
        if collector is None:
            error = f"Collector {collector_name} is not available"
            self._logger.error(
                "scheduler.job_failed", collector=collector_name, error=error
            )
            self._record_metric(
                collector_name, "failed", attempts=1, duration_seconds=0.0, error=error
            )
            return {
                "collector": collector_name,
                "status": "failed",
                "attempts": 1,
                "error": error,
            }

        started_at = time.perf_counter()
        last_error: Exception | None = None
        config = self.settings.collector_configs.get(collector_name)
        execution_parameters = self._collector_execution_parameters(config)
        totals = {"discovered": 0, "persisted": 0, "skipped": 0, "failed": 0}
        for attempt in range(1, self.retry_attempts + 1):
            try:
                self._logger.info(
                    "scheduler.job_started", collector=collector_name, attempt=attempt
                )
                for query, kwargs in execution_parameters:
                    run_kwargs = dict(kwargs)
                    if collector.__class__.run is BaseCollector.run:
                        run_kwargs["item_handler"] = self._process_listing
                    await collector.run(query=query, **run_kwargs)
                    for metric_name, value in getattr(
                        collector, "last_run_metrics", {}
                    ).items():
                        totals[metric_name] += value
                duration_seconds = round(time.perf_counter() - started_at, 6)
                self._logger.info(
                    "scheduler.job_succeeded",
                    collector=collector_name,
                    attempt=attempt,
                    duration_seconds=duration_seconds,
                )
                self._record_metric(
                    collector_name,
                    "success",
                    attempts=attempt,
                    duration_seconds=duration_seconds,
                    counts=totals,
                )
                return {
                    "collector": collector_name,
                    "status": "success",
                    "attempts": attempt,
                    "duration_seconds": duration_seconds,
                    **totals,
                }
            except Exception as exc:  # pragma: no cover - exercised through retry loop
                last_error = exc
                run_metrics = getattr(collector, "last_run_metrics", None)
                if run_metrics:
                    for metric_name, value in run_metrics.items():
                        totals[metric_name] += value
                else:
                    totals["failed"] += 1
                if attempt >= self.retry_attempts:
                    break
                delay_seconds = self.retry_backoff_base_seconds * (2 ** (attempt - 1))
                self._logger.warning(
                    "scheduler.job_retry",
                    collector=collector_name,
                    attempt=attempt,
                    delay_seconds=delay_seconds,
                    error=str(exc),
                )
                await asyncio.sleep(delay_seconds)

        duration_seconds = round(time.perf_counter() - started_at, 6)
        error = (
            str(last_error) if last_error is not None else "Unknown collector failure"
        )
        self._logger.error(
            "scheduler.job_failed",
            collector=collector_name,
            attempts=self.retry_attempts,
            error=error,
            counts=totals,
        )
        self._record_metric(
            collector_name,
            "failed",
            attempts=self.retry_attempts,
            duration_seconds=duration_seconds,
            error=error,
            counts=totals,
        )
        return {
            "collector": collector_name,
            "status": "failed",
            "attempts": self.retry_attempts,
            "error": error,
            **totals,
        }

    async def _process_listing(self, item: Any) -> Any:
        context = await self.pipeline.execute(
            ListingPipelineData(raw_data=self._item_data(item))
        )
        failed_metrics = [metric for metric in context.metrics if not metric.success]
        if failed_metrics:
            raise RuntimeError(failed_metrics[-1].error or "Listing pipeline failed")
        if context.data.listing_id is None or not context.metadata.get("listing_created", False):
            return None

        listing_data = context.data.listing.model_dump() if context.data.listing else {}
        await bus.publish(
            ListingStored(
                listing_id=context.data.listing_id,
                external_id=listing_data.get("external_id") or "unknown",
                source=listing_data.get("source") or "unknown",
                data=listing_data,
            )
        )
        return context.data.listing_id

    @staticmethod
    def _item_data(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return item
        if hasattr(item, "model_dump"):
            return item.model_dump()
        return dict(vars(item))

    @staticmethod
    def _collector_execution_parameters(
        config: Any | None,
    ) -> list[tuple[str, dict[str, Any]]]:
        if config is None:
            return [("", {})]

        queries = config.queries or [""]
        locations = config.locations or [None]
        credentials = {
            name: value.get_secret_value()
            for name, value in config.credentials.items()
        }
        common = {
            "pagination_limit": config.pagination_limit,
            "request_timeout": config.request_timeout,
            "rate_limit_per_minute": config.rate_limit_per_minute,
            "credentials": credentials,
            "fixture_path": config.fixture_path,
        }
        return [
            (
                query,
                {**common, "location": location},
            )
            for query in queries
            for location in locations
        ]

    def _record_metric(
        self,
        collector_name: str,
        status: str,
        *,
        attempts: int,
        duration_seconds: float,
        error: str | None = None,
        counts: dict[str, int] | None = None,
    ) -> None:
        metric = {
                "collector": collector_name,
                "status": status,
                "attempts": attempts,
                "duration_seconds": duration_seconds,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        if counts:
            metric.update(counts)
        self.metrics.append(metric)


__all__ = ["SchedulerService"]
