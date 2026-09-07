from typing import Any

from fastapi import APIRouter
from config.settings import settings

router = APIRouter(prefix="/config", tags=["configuration"])


@router.get("/", response_model=dict)
def get_config() -> Any:
    """Retrieve the current application configuration."""
    return settings.public_dump()
