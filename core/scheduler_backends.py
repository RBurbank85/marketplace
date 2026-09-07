from __future__ import annotations

from typing import Any, Callable, NoReturn

from core.scheduler_base import BaseScheduler


class _UnsupportedBackend(BaseScheduler):
    """Shared contract for scheduler integrations deferred from this release."""

    backend_type = "unsupported"

    def _unsupported(self) -> NoReturn:
        raise NotImplementedError(
            f"{self.backend_type.title()} backend is not supported in this release."
        )

    def start(self) -> None:
        self._unsupported()

    def stop(self, wait: bool = True) -> None:
        self._unsupported()

    def pause(self) -> None:
        self._unsupported()

    def resume(self) -> None:
        self._unsupported()

    def status(self) -> dict[str, Any]:
        return {
            "type": self.backend_type,
            "running": False,
            "status": "unsupported",
            "supported": False,
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
        self._unsupported()

    def cancel(self, job_id: str) -> bool:
        self._unsupported()


class FutureCeleryBackend(_UnsupportedBackend):
    """Deferred Celery integration; not supported in this release."""

    backend_type = "celery"


class FutureRQBackend(_UnsupportedBackend):
    """Deferred RQ integration; not supported in this release."""

    backend_type = "rq"
