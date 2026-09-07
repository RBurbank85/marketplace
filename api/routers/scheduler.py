from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from core.scheduler import SchedulerService
from api.deps import get_scheduler_service

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status", response_model=dict)
def get_scheduler_status(
    service: SchedulerService = Depends(get_scheduler_service),
) -> Any:
    """Show scheduler configuration and recent execution metrics."""
    return service.status()


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
