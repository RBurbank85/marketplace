from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable

from loguru import logger

from collectors.base import BaseCollector, CollectorRegistry, discover_collectors
from config.settings import Settings, settings as default_settings
from core.scheduler_base import BaseScheduler
from core.scheduler_apscheduler import APSchedulerBackend


class SchedulerService:
    """Coordinate collector execution with retries, overlap protection, and metrics."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        collectors: dict[str, BaseCollector] | None = None,
        backend: BaseScheduler | None = None,
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
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrent_collectors)
        self.metrics: list[dict[str, Any]] = []
        self._logger = logger.bind(component="scheduler_service")

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
            self.collectors[collector_name.lower()] = collector_cls()
        return self.collectors

    def _get_collector(self, collector_name: str) -> BaseCollector | None:
        normalized_name = collector_name.lower()
        resolved = self._resolve_collectors()
        collector = resolved.get(normalized_name)
        if collector is None:
            registry_cls = CollectorRegistry.get(normalized_name)
            if registry_cls is None:
                return None
            collector = registry_cls()
        return collector

    def start(self) -> None:
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

    def stop(self, wait: bool = True) -> None:
        self.backend.stop(wait=wait)
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
        for attempt in range(1, self.retry_attempts + 1):
            try:
                self._logger.info(
                    "scheduler.job_started", collector=collector_name, attempt=attempt
                )
                await collector.run(query="")
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
                )
                return {
                    "collector": collector_name,
                    "status": "success",
                    "attempts": attempt,
                    "duration_seconds": duration_seconds,
                }
            except Exception as exc:  # pragma: no cover - exercised through retry loop
                last_error = exc
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
        )
        self._record_metric(
            collector_name,
            "failed",
            attempts=self.retry_attempts,
            duration_seconds=duration_seconds,
            error=error,
        )
        return {
            "collector": collector_name,
            "status": "failed",
            "attempts": self.retry_attempts,
            "error": error,
        }

    def _record_metric(
        self,
        collector_name: str,
        status: str,
        *,
        attempts: int,
        duration_seconds: float,
        error: str | None = None,
    ) -> None:
        self.metrics.append(
            {
                "collector": collector_name,
                "status": status,
                "attempts": attempts,
                "duration_seconds": duration_seconds,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


__all__ = ["SchedulerService"]
