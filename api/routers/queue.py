from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from alerts.approval import ApprovedOpportunityDispatcher
from database.repositories import (
    QueueRepository,
    QueueTransitionError,
    StaleQueueUpdateError,
)
from database.schemas import PaginatedResponse, QueueRead
from database.models import QueueStatus
from api.deps import get_queue_repository
from api.deps import get_db, get_notification_service
from sqlmodel import Session

router = APIRouter(prefix="/queue", tags=["queue"])


class QueueActionRequest(BaseModel):
    notes: Optional[str] = None
    expected_version: int = Field(..., ge=1)


def _transition(
    action: str,
    queue_id: UUID,
    request: QueueActionRequest,
    repo: QueueRepository,
) -> Any:
    try:
        return getattr(repo, action)(
            queue_id, request.notes, expected_version=request.expected_version
        )
    except StaleQueueUpdateError as exc:
        raise HTTPException(status_code=409, detail={"code": "stale_write", "message": "Queue item version is stale"}) from exc
    except QueueTransitionError as exc:
        raise HTTPException(status_code=409, detail={"code": "invalid_queue_transition", "message": str(exc)}) from exc


@router.get("/", response_model=PaginatedResponse[QueueRead])
def list_queue(
    status: QueueStatus | None = Query(None, description="Filter by queue lifecycle status."),
    offset: int = Query(0, ge=0, description="Number of matching records to skip."),
    limit: int = Query(50, ge=1, le=100, description="Maximum records to return."),
    repo: QueueRepository = Depends(get_queue_repository),
) -> Any:
    """Retrieve a bounded, deterministically sorted queue page."""
    items, total = repo.list_page(offset=offset, limit=limit, status=status)
    return {"items": items, "pagination": {"offset": offset, "limit": limit, "total": total, "has_more": offset + len(items) < total}}


@router.get("/{queue_id}", response_model=QueueRead)
def get_queue_item(
    queue_id: UUID,
    repo: QueueRepository = Depends(get_queue_repository),
) -> Any:
    """Get a single queue item by ID."""
    item = repo.get_by_id(queue_id)
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return item


@router.post("/{queue_id}/review", response_model=QueueRead)
def review_queue_item(
    queue_id: UUID,
    request: QueueActionRequest,
    repo: QueueRepository = Depends(get_queue_repository),
) -> Any:
    """Mark a queue item as being reviewed."""
    item = _transition("review", queue_id, request, repo)
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    repo.commit()
    return item


@router.post("/{queue_id}/approve", response_model=QueueRead)
def approve_queue_item(
    queue_id: UUID,
    request: QueueActionRequest,
    repo: QueueRepository = Depends(get_queue_repository),
    session: Session = Depends(get_db),
    notification_service=Depends(get_notification_service),
) -> Any:
    """Approve an opportunity, then dispatch its durable notifications."""
    item = _transition("approve", queue_id, request, repo)
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    repo.commit()
    results = ApprovedOpportunityDispatcher(
        notification_service, session=session
    ).dispatch(queue_id)
    payload = QueueRead.model_validate(item).model_dump()
    payload["notification_results"] = results
    return payload


@router.post("/{queue_id}/notify", response_model=QueueRead)
def notify_approved_queue_item(
    queue_id: UUID,
    repo: QueueRepository = Depends(get_queue_repository),
    session: Session = Depends(get_db),
    notification_service=Depends(get_notification_service),
) -> Any:
    """Retry failed provider deliveries for an approved queue item."""
    try:
        results = ApprovedOpportunityDispatcher(
            notification_service, session=session
        ).dispatch(queue_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Queue item not found"}) from exc
    except QueueTransitionError as exc:
        raise HTTPException(status_code=409, detail={"code": "invalid_queue_transition", "message": str(exc)}) from exc
    item = repo.get_by_id(queue_id)
    if item is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Queue item not found"})
    payload = QueueRead.model_validate(item).model_dump()
    payload["notification_results"] = results
    return payload


@router.post("/{queue_id}/reject", response_model=QueueRead)
def reject_queue_item(
    queue_id: UUID,
    request: QueueActionRequest,
    repo: QueueRepository = Depends(get_queue_repository),
) -> Any:
    """Reject an opportunity in the queue."""
    item = _transition("reject", queue_id, request, repo)
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    repo.commit()
    return item


@router.post("/{queue_id}/archive", response_model=QueueRead)
def archive_queue_item(
    queue_id: UUID,
    request: QueueActionRequest,
    repo: QueueRepository = Depends(get_queue_repository),
) -> Any:
    """Archive a queue item."""
    item = _transition("archive", queue_id, request, repo)
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    repo.commit()
    return item
