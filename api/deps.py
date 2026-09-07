import threading
import time
from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import APIKeyHeader
from sqlmodel import Session

from database.database import get_session
from database.repositories import (
    ListingRepository,
    OpportunityRepository,
    QueueRepository,
    SearchRepository,
    SellerRepository,
    PurchaseRepository,
)

from core.plugins import PluginRegistry, PluginLoader, get_default_registry

from core.scheduler import SchedulerService
from config.settings import settings

_scheduler_service = SchedulerService(settings=settings)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
PUBLIC_ENDPOINTS = {"/", "/docs", "/redoc", "/openapi.json", "/dashboard"}


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_ENDPOINTS or path.startswith("/dashboard/assets/")


class _InMemoryRateLimiter:
    """Fixed-window limiter; its storage can be replaced with Redis later."""

    window_seconds = 60.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, int]] = {}

    def allow(self, key: str, limit: int, now: float) -> bool:
        with self._lock:
            cutoff = now - self.window_seconds
            self._entries = {
                entry_key: entry
                for entry_key, entry in self._entries.items()
                if entry[0] > cutoff
            }

            window_start, count = self._entries.get(key, (now, 0))
            if now - window_start >= self.window_seconds:
                window_start, count = now, 0

            if count >= limit:
                self._entries[key] = (window_start, count)
                return False

            self._entries[key] = (window_start, count + 1)
            return True

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_rate_limiter = _InMemoryRateLimiter()


async def get_api_key(
    request: Request,
    api_key_header: str = Depends(API_KEY_HEADER),
) -> str:
    """Validate the API key from the header."""
    # Whitelist public endpoints
    if _is_public_path(request.url.path):
        return ""

    if not settings.api_auth_enabled:
        return ""

    if not settings.api_key:
        # If no API key is configured, allow access (for development)
        return ""

    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required for this endpoint",
        )

    if api_key_header == settings.api_key:
        return api_key_header

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Could not validate API key",
    )


async def get_current_user(
    api_key: str = Depends(get_api_key),
) -> Optional[dict]:
    """
    Dependency to get the current user.
    Currently uses API Key, but designed to be easily swapped for JWT.
    """
    # This is a placeholder for future JWT authentication.
    # When implementing JWT, this dependency would validate the token
    # and return the user object/claims.
    return {"id": "default_user", "api_key": api_key}


async def rate_limiter(
    request: Request,
    user: Optional[dict] = Depends(get_current_user),
) -> None:
    """Allow configured requests per client in a rolling one-minute window."""
    if _is_public_path(request.url.path):
        return

    limit = settings.rate_limit_requests_per_minute
    if limit is None or limit <= 0:
        return

    client_key = request.client.host if request.client else "unknown"
    if not _rate_limiter.allow(client_key, limit, time.monotonic()):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(int(_rate_limiter.window_seconds))},
        )


def get_db() -> Generator[Session, None, None]:
    with get_session() as session:
        yield session


def get_plugin_registry() -> PluginRegistry:
    registry = get_default_registry()
    if not registry.get_collectors():
        loader = PluginLoader(registry)
        loader.discover(packages=["collectors"])
    return registry


def get_scheduler_service() -> SchedulerService:
    return _scheduler_service


def get_listing_repository(session: Session = Depends(get_db)) -> ListingRepository:
    return ListingRepository(session=session)


def get_opportunity_repository(
    session: Session = Depends(get_db),
) -> OpportunityRepository:
    return OpportunityRepository(session=session)


def get_queue_repository(session: Session = Depends(get_db)) -> QueueRepository:
    return QueueRepository(session=session)


def get_search_repository(session: Session = Depends(get_db)) -> SearchRepository:
    return SearchRepository(session=session)


def get_seller_repository(session: Session = Depends(get_db)) -> SellerRepository:
    return SellerRepository(session=session)


def get_purchase_repository(session: Session = Depends(get_db)) -> PurchaseRepository:
    return PurchaseRepository(session=session)
