from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from database.repositories import ListingRepository
from database.schemas import ListingCreate, ListingRead, ListingUpdate, PaginatedResponse
from database.models import ListingStatus
from api.deps import get_listing_repository

router = APIRouter(prefix="/listings", tags=["listings"])


@router.get("/", response_model=PaginatedResponse[ListingRead])
def list_listings(
    status: ListingStatus | None = Query(None, description="Filter by listing lifecycle status."),
    source: str | None = Query(None, min_length=1, description="Filter by marketplace source."),
    category: str | None = Query(None, min_length=1, description="Filter by indexed category."),
    offset: int = Query(0, ge=0, description="Number of matching records to skip."),
    limit: int = Query(50, ge=1, le=100, description="Maximum records to return."),
    repo: ListingRepository = Depends(get_listing_repository),
) -> Any:
    """Retrieve a bounded, deterministically sorted listing page."""
    items, total = repo.list_page(
        offset=offset, limit=limit, status=status, source=source, category=category
    )
    return {"items": items, "pagination": {"offset": offset, "limit": limit, "total": total, "has_more": offset + len(items) < total}}


@router.get("/{listing_id}", response_model=ListingRead)
def get_listing(
    listing_id: UUID,
    repo: ListingRepository = Depends(get_listing_repository),
) -> Any:
    """Get a single listing by ID."""
    listing = repo.get_by_id(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.post("/", response_model=ListingRead, status_code=status.HTTP_201_CREATED)
def create_listing(
    listing_in: ListingCreate,
    repo: ListingRepository = Depends(get_listing_repository),
) -> Any:
    """Create a new listing."""
    from database.models import Listing

    listing = Listing(**listing_in.model_dump())
    try:
        return repo.create(listing)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail={"code": "duplicate_identity", "message": "A listing with this source and external ID already exists."}) from exc


@router.patch("/{listing_id}", response_model=ListingRead)
def update_listing(
    listing_id: UUID,
    listing_in: ListingUpdate,
    repo: ListingRepository = Depends(get_listing_repository),
) -> Any:
    """Update an existing listing."""
    listing = repo.update(listing_id, listing_in.model_dump(exclude_unset=True))
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_listing(
    listing_id: UUID,
    repo: ListingRepository = Depends(get_listing_repository),
) -> None:
    """Delete a listing."""
    if not repo.delete(listing_id):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Listing not found"})
