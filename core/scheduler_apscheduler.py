from __future__ import annotations

from datetime import timezone
from typing import Any, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from core.scheduler_base import BaseScheduler


class APSchedulerBackend(BaseScheduler):
    """APScheduler implementation of the BaseScheduler."""

    def __init__(self, **scheduler_kwargs: Any) -> None:
        defaults = {"timezone": timezone.utc, "job_defaults": {"coalesce": True, "max_instances": 1}}
        defaults.update(scheduler_kwargs)
        self._scheduler = AsyncIOScheduler(**defaults)
        self._logger = logger.bind(component="apscheduler_backend")

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            self._logger.info("apscheduler.started")

    def stop(self, wait: bool = True) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            self._logger.info("apscheduler.stopped")

    def pause(self) -> None:
        self._scheduler.pause()
        self._logger.info("apscheduler.paused")

    def resume(self) -> None:
        self._scheduler.resume()
        self._logger.info("apscheduler.resumed")

    def status(self) -> dict[str, Any]:
        return {
            "type": "apscheduler",
            "running": self._scheduler.running,
            "jobs_count": len(self._scheduler.get_jobs()),
            "state": str(self._scheduler.state),
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
        job = self._scheduler.add_job(
            func,
            args=args,
            kwargs=kwargs,
            id=job_id,
            name=name,
            trigger=trigger,
            replace_existing=True,
            **trigger_kwargs,
        )
        self._logger.info("apscheduler.job_scheduled", job_id=job.id, name=name)
        return str(job.id)

    def cancel(self, job_id: str) -> bool:
        try:
            self._scheduler.remove_job(job_id)
            self._logger.info("apscheduler.job_cancelled", job_id=job_id)
            return True
        except Exception:
            self._logger.warning("apscheduler.job_cancel_failed", job_id=job_id)
            return False
