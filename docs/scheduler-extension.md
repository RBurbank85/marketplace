# Adding Alternative Schedulers

MAIE uses a pluggable scheduler architecture. To add a new scheduler backend, follow these steps:

## Current backend support

APScheduler is the only supported scheduler backend in the current release and
is the default used by `SchedulerService`. Celery and RQ are intentionally
deferred integrations: `FutureCeleryBackend` and `FutureRQBackend` remain
importable as explicit placeholders, but report `supported: false` and raise
`NotImplementedError` for lifecycle, scheduling, and cancellation operations.
They must not be configured as operational backends until a release adds their
optional dependencies and a complete `BaseScheduler` implementation.

## 1. Implement the `BaseScheduler` Protocol

Create a new class that implements the `BaseScheduler` protocol defined in `./core/scheduler_base.py`.

```python
from typing import Any, Callable
from core.scheduler_base import BaseScheduler

class MyCustomBackend(BaseScheduler):
    def start(self) -> None:
        # Implementation
        pass

    def stop(self, wait: bool = True) -> None:
        # Implementation
        pass

    def pause(self) -> None:
        # Implementation
        pass

    def resume(self) -> None:
        # Implementation
        pass

    def status(self) -> dict[str, Any]:
        # Return status information
        return {"running": True, "type": "custom"}

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
        # Schedule the task and return the job ID
        return "job_id"

    def cancel(self, job_id: str) -> bool:
        # Cancel the task and return success status
        return True
```

## 2. Register the Backend

Add your backend to `./core/scheduler_backends.py` or import it where you initialize the `SchedulerService`.

## 3. Inject the Backend

When initializing the `SchedulerService`, provide your custom backend:

```python
from core.scheduler import SchedulerService
from my_module import MyCustomBackend

backend = MyCustomBackend()
scheduler_service = SchedulerService(backend=backend)
```

In the API, you can update `./api/deps.py` to use your new backend.
