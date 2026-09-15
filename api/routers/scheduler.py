from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from core.scheduler import SchedulerService
from api.deps import get_scheduler_service

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status", response_model=dict)
def get_scheduler_status(
    service: SchedulerService = Depends(get_scheduler_service),
) -> Any:
    """Show scheduler configuration and recent execution metrics."""
    return service.status()


@router.get("/metrics", response_model=dict)
def get_scheduler_metrics(
    offset: int = Query(0, ge=0, description="Number of metrics to skip."),
    limit: int = Query(50, ge=1, le=500, description="Maximum metrics to return."),
    service: SchedulerService = Depends(get_scheduler_service),
) -> Any:
    """Retrieve scheduler execution metrics with pagination.

    Returns all process-local metrics (not just the last 3 shown in
    ``/scheduler/status``).  Metrics are returned newest-first.
    """
    all_metrics = list(reversed(service.metrics))
    total = len(all_metrics)
    items = all_metrics[offset : offset + limit]
    return {
        "items": items,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + len(items) < total,
        },
    }


@router.post("/start", response_model=dict)
async def start_scheduler(
    service: SchedulerService = Depends(get_scheduler_service),
) -> Any:
    """Start the background scheduler."""
    service.start()
    return {"message": "Scheduler started"}


@router.post("/stop", response_model=dict)
async def stop_scheduler(
    service: SchedulerService = Depends(get_scheduler_service),
) -> Any:
    """Stop the background scheduler."""
    service.stop()
    return {"message": "Scheduler stopped"}


@router.post("/pause", response_model=dict)
async def pause_scheduler(
    service: SchedulerService = Depends(get_scheduler_service),
) -> Any:
    """Pause the background scheduler."""
    service.pause()
    return {"message": "Scheduler paused"}


@router.post("/resume", response_model=dict)
async def resume_scheduler(
    service: SchedulerService = Depends(get_scheduler_service),
) -> Any:
    """Resume the background scheduler."""
    service.resume()
    return {"message": "Scheduler resumed"}


@router.post("/run/{collector_name}", response_model=dict)
async def run_collector(
    collector_name: str,
    service: SchedulerService = Depends(get_scheduler_service),
) -> Any:
    """Run a collector job immediately."""
    result = await service.run_job(collector_name)
    if result.get("status") == "failed":
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result
