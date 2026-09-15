from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.settings import CollectorConfig, settings

router = APIRouter(prefix="/config", tags=["configuration"])


_UPDATABLE_FIELDS = {
    "search_interval",
    "minimum_flipscore",
    "minimum_expected_profit",
    "notifications_enabled",
    "notification_requires_approval",
    "scheduler_autostart",
    "logging_level",
    "enabled_collectors",
    "enabled_categories",
}


class CollectorConfigUpdate(BaseModel):
    queries: Optional[list[str]] = None
    locations: Optional[list[str]] = None
    pagination_limit: Optional[int] = Field(default=None, ge=1)
    request_timeout: Optional[float] = Field(default=None, gt=0)
    rate_limit_per_minute: Optional[int] = Field(default=None, ge=0)
    fixture_path: Optional[str] = None
    obey_robots: Optional[bool] = None


class ConfigUpdate(BaseModel):
    search_interval: Optional[int] = Field(default=None, ge=1)
    minimum_flipscore: Optional[int] = Field(default=None, ge=0, le=100)
    minimum_expected_profit: Optional[float] = Field(default=None, ge=0.0)
    notifications_enabled: Optional[bool] = None
    notification_requires_approval: Optional[bool] = None
    scheduler_autostart: Optional[bool] = None
    logging_level: Optional[str] = None
    enabled_collectors: Optional[list[str]] = None
    enabled_categories: Optional[list[str]] = None
    collector_configs: Optional[dict[str, CollectorConfigUpdate]] = None


@router.get("/", response_model=dict)
def get_config() -> Any:
    """Retrieve the current application configuration."""
    return settings.public_dump()


@router.put("/", response_model=dict)
def update_config(update: ConfigUpdate) -> Any:
    """Update application configuration at runtime.

    Restricted to the ``development`` environment for security.  Only a
    subset of non-secret fields may be changed.  Collector configurations
    can be added or merged — existing collectors not mentioned in the
    request are preserved.
    """
    if settings.environment.strip().lower() != "development":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "config_update_forbidden",
                "message": "Configuration updates are only allowed in the development environment.",
            },
        )

    data = update.model_dump(exclude_unset=True)

    collector_updates = data.pop("collector_configs", None)

    for field, value in data.items():
        if field in _UPDATABLE_FIELDS:
            setattr(settings, field, value)

    if collector_updates:
        existing = dict(settings.collector_configs)
        for name, cfg_update in collector_updates.items():
            current = existing.get(name, CollectorConfig())
            merged = current.model_copy(update=cfg_update)
            existing[name] = merged
        settings.collector_configs = existing

    return settings.public_dump()
