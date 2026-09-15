from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from database.repositories import SearchRepository
from database.schemas import SearchCreate, SearchRead
from api.deps import get_search_repository

router = APIRouter(prefix="/searches", tags=["searches"])


@router.get("/", response_model=List[SearchRead])
def list_searches(
    repo: SearchRepository = Depends(get_search_repository),
) -> Any:
    """Retrieve all recent searches."""
    return repo.list()


@router.get("/{search_id}", response_model=SearchRead)
def get_search(
    search_id: UUID,
    repo: SearchRepository = Depends(get_search_repository),
) -> Any:
    """Get a single search record by ID."""
    search = repo.get_by_id(search_id)
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")
    return search


@router.post("/", response_model=SearchRead, status_code=status.HTTP_201_CREATED)
def create_search(
    search_in: SearchCreate,
    repo: SearchRepository = Depends(get_search_repository),
) -> Any:
    """Log a new search query."""
    from database.models import Search

    search = Search(**search_in.model_dump())
    return repo.create(search)


@router.delete("/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_search(
    search_id: UUID,
    repo: SearchRepository = Depends(get_search_repository),
) -> None:
    """Delete a search record by ID."""
    if not repo.delete(search_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Search not found"},
        )
