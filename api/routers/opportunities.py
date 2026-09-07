from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from database.repositories import OpportunityRepository
from database.schemas import OpportunityCreate, OpportunityRead, PaginatedResponse
from api.deps import get_opportunity_repository

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("/", response_model=PaginatedResponse[OpportunityRead])
def list_opportunities(
    listing_id: UUID | None = Query(None, description="Filter by source listing ID."),
    min_confidence: float | None = Query(None, ge=0, le=1, description="Minimum confidence score."),
    offset: int = Query(0, ge=0, description="Number of matching records to skip."),
    limit: int = Query(50, ge=1, le=100, description="Maximum records to return."),
    repo: OpportunityRepository = Depends(get_opportunity_repository),
) -> Any:
    """Retrieve a bounded, deterministically sorted opportunity page."""
    items, total = repo.list_page(
        offset=offset, limit=limit, listing_id=listing_id, min_confidence=min_confidence
    )
    return {"items": items, "pagination": {"offset": offset, "limit": limit, "total": total, "has_more": offset + len(items) < total}}


@router.get("/{opportunity_id}", response_model=OpportunityRead)
def get_opportunity(
    opportunity_id: UUID,
    repo: OpportunityRepository = Depends(get_opportunity_repository),
) -> Any:
    """Get a single opportunity by ID."""
    opportunity = repo.get_by_id(opportunity_id)
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opportunity


@router.post("/", response_model=OpportunityRead, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    opportunity_in: OpportunityCreate,
    repo: OpportunityRepository = Depends(get_opportunity_repository),
) -> Any:
    """Create a new opportunity."""
    from database.models import Opportunity

    opportunity = Opportunity(**opportunity_in.model_dump())
    return repo.create(opportunity)


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity(
    opportunity_id: UUID,
    repo: OpportunityRepository = Depends(get_opportunity_repository),
) -> None:
    """Delete an opportunity."""
    if not repo.delete(opportunity_id):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Opportunity not found"})
