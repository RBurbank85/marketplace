"""eBay Browse API collector for MAIE.

Uses the eBay Browse API (client credentials grant flow) to search for
active listings and normalize them into the project's Listing model.

API reference:
  - https://developer.ebay.com/develop/api/buy/browse_api
  - Token: POST https://api.ebay.com/identity/v1/oauth2/token
  - Search: GET  https://api.ebay.com/buy/browse/v1/item_summary/search

Credentials (App ID / Cert ID) are passed at runtime through the
``credentials`` kwarg, matching how the scheduler injects
``CollectorConfig.credentials`` into ``collector.run(...)``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode

import httpx
from loguru import logger

from collectors.base import BaseCollector
from database.models import Listing, ListingStatus
from database.repositories import ListingRepository


# --- Constants ---------------------------------------------------------------

EBAY_API_SCOPE = "https://api.ebay.com/oauth/api_scope"
DEFAULT_BASE_URL = "https://api.ebay.com"
DEFAULT_TOKEN_PATH = "/identity/v1/oauth2/token"
DEFAULT_SEARCH_PATH = "/buy/browse/v1/item_summary/search"
DEFAULT_MARKETPLACE_ID = "EBAY_US"
DEFAULT_PAGE_LIMIT = 50  # eBay Browse API max is 200; 50 is the documented default
MAX_PAGE_LIMIT = 200
TOKEN_SAFETY_BUFFER_SECONDS = 60  # refresh slightly before actual expiry


class EbayAuthError(RuntimeError):
    """Raised when eBay OAuth token retrieval fails."""


class EbayCollector(BaseCollector):
    """Collector implementation for the eBay Browse API."""

    name = "ebay"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        token_path: str = DEFAULT_TOKEN_PATH,
        search_path: str = DEFAULT_SEARCH_PATH,
        marketplace_id: str = DEFAULT_MARKETPLACE_ID,
        request_delay: float = 0.5,
        max_retries: int = 2,
        obey_robots: bool = False,
        seen_ids: Iterable[str] | None = None,
        database_url: str | None = None,
        page_limit: int = DEFAULT_PAGE_LIMIT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_url = f"{self.base_url}{token_path}"
        self.search_url = f"{self.base_url}{search_path}"
        self.marketplace_id = marketplace_id
        self.database_url = database_url
        self.repository = (
            ListingRepository(database_url=database_url) if database_url else None
        )
        self._seen_ids: set[str] = set(seen_ids or [])
        self.request_delay = max(0.0, request_delay)
        self.max_retries = max(0, max_retries)
        self.page_limit = min(max(1, page_limit), MAX_PAGE_LIMIT)

        # Token cache
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

        # Per-run request metrics
        self.request_metrics: dict[str, int] = {
            "requests": 0,
            "retries": 0,
            "failures": 0,
        }

        self._client: httpx.AsyncClient | None = None
        self._pacing_lock = asyncio.Lock()
        self._next_request_at = 0.0
        self._logger = logger.bind(component="ebay_collector")

    # ------------------------------------------------------------------
    # HTTP client lifecycle
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # OAuth token management
    # ------------------------------------------------------------------

    def _resolve_credentials(self, kwargs: dict[str, Any]) -> tuple[str, str]:
        """Extract client_id and client_secret from kwargs or __init__ fallback."""
        credentials = kwargs.get("credentials") or {}
        client_id = credentials.get("client_id") or ""
        client_secret = credentials.get("client_secret") or ""
        if not client_id or not client_secret:
            raise EbayAuthError(
                "eBay Browse API requires 'client_id' and 'client_secret' "
                "in credentials. Obtain App ID and Cert ID from the eBay "
                "Developer Program."
            )
        return client_id, client_secret

    async def _get_access_token(self, kwargs: dict[str, Any]) -> str:
        """Return a cached token or mint a new one via client credentials flow."""
        if (
            self._access_token
            and time.monotonic() < self._token_expires_at
        ):
            return self._access_token

        client_id, client_secret = self._resolve_credentials(kwargs)

        credential = base64.b64encode(
            f"{client_id}:{client_secret}".encode("utf-8")
        ).decode("utf-8")

        headers = {
            "Authorization": f"Basic {credential}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        body = urlencode(
            {
                "grant_type": "client_credentials",
                "scope": EBAY_API_SCOPE,
            }
        )

        client = await self._get_client()
        self._logger.info("ebay_token_request", token_url=self.token_url)

        try:
            response = await client.post(self.token_url, headers=headers, content=body)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            self.request_metrics["failures"] += 1
            raise EbayAuthError(
                f"Failed to obtain eBay access token: {exc}"
            ) from exc

        payload = response.json()
        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in", 7200)

        if not access_token:
            raise EbayAuthError(
                f"eBay token response missing access_token: {payload}"
            )

        self._access_token = access_token
        self._token_expires_at = (
            time.monotonic() + float(expires_in) - TOKEN_SAFETY_BUFFER_SECONDS
        )
        self._logger.info(
            "ebay_token_acquired",
            expires_in=expires_in,
        )
        return access_token

    def _invalidate_token(self) -> None:
        """Force the next call to mint a fresh token (e.g. after a 401)."""
        self._access_token = None
        self._token_expires_at = 0.0

    # ------------------------------------------------------------------
    # Rate-limit pacing
    # ------------------------------------------------------------------

    async def _pace(self, rate_limit_per_minute: int | None) -> None:
        """Enforce a minimum interval between requests."""
        configured_interval = (
            60.0 / rate_limit_per_minute
            if rate_limit_per_minute and rate_limit_per_minute > 0
            else 0.0
        )
        interval = max(self.request_delay, configured_interval)
        async with self._pacing_lock:
            wait_seconds = self._next_request_at - time.monotonic()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._next_request_at = time.monotonic() + interval

    # ------------------------------------------------------------------
    # Fixture support
    # ------------------------------------------------------------------

    def _read_fixture(self, fixture_path: str | None) -> dict[str, Any] | None:
        if not fixture_path:
            return None
        path = Path(fixture_path)
        if not path.exists():
            raise FileNotFoundError(f"Fixture not found: {fixture_path}")
        return json.loads(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Search (abstract method)
    # ------------------------------------------------------------------

    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Search eBay via the Browse API and return the raw JSON response.

        When ``fixture_path`` is provided in kwargs, the JSON fixture is
        loaded instead of making any API call, which allows tests to run
        without credentials or network access.
        """
        fixture = self._read_fixture(kwargs.get("fixture_path"))
        if fixture is not None:
            self._logger.info(
                "ebay_fixture_loaded",
                fixture_path=kwargs.get("fixture_path"),
            )
            return fixture

        pagination_limit = max(1, int(kwargs.get("pagination_limit", 1)))
        page_limit = int(kwargs.get("page_limit", self.page_limit))
        rate_limit_per_minute = kwargs.get("rate_limit_per_minute")
        request_timeout = kwargs.get("request_timeout")

        # Build params for the first page
        params: dict[str, Any] = {
            "q": query,
            "limit": str(page_limit),
        }
        # Support optional category_ids, filter, sort passed through kwargs
        for key in ("category_ids", "filter", "sort", "aspect_filter"):
            value = kwargs.get(key)
            if value:
                params[key] = value

        # Fetch pages
        all_items: list[dict[str, Any]] = []
        total: int | None = None
        href_next: str | None = None

        for page in range(pagination_limit):
            await self._pace(rate_limit_per_minute)

            if page == 0:
                result = await self._search_request(params, kwargs, request_timeout)
            else:
                # Use the next-page href if available, otherwise increment offset
                if href_next:
                    result = await self._search_request(
                        None, kwargs, request_timeout, full_url=href_next
                    )
                else:
                    params["offset"] = str(page * page_limit)
                    result = await self._search_request(
                        params, kwargs, request_timeout
                    )

            all_items.extend(result.get("itemSummaries", []))
            if total is None:
                total = result.get("total")
            href_next = result.get("next")

            if not href_next:
                break

        return {
            "itemSummaries": all_items,
            "total": total,
        }

    async def _search_request(
        self,
        params: dict[str, Any] | None,
        kwargs: dict[str, Any],
        request_timeout: float | None = None,
        *,
        full_url: str | None = None,
    ) -> dict[str, Any]:
        """Execute a single eBay search API call with token auth and retry."""
        token = await self._get_access_token(kwargs)

        url = full_url or self.search_url
        if params:
            url = f"{url}?{urlencode(params)}"

        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
            "Accept": "application/json",
        }

        client = await self._get_client()
        request_kwargs: dict[str, Any] = {"headers": headers}
        if request_timeout is not None:
            request_kwargs["timeout"] = request_timeout

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                self._logger.debug(
                    "ebay_search_request",
                    url=url,
                    attempt=attempt + 1,
                )
                response = await client.get(url, **request_kwargs)

                # If 401, refresh token and retry once
                if response.status_code == 401 and attempt == 0:
                    self._logger.warning("ebay_token_expired_refreshing")
                    self._invalidate_token()
                    token = await self._get_access_token(kwargs)
                    headers["Authorization"] = f"Bearer {token}"
                    request_kwargs["headers"] = headers
                    self.request_metrics["retries"] += 1
                    continue

                response.raise_for_status()
                self.request_metrics["requests"] += 1
                return response.json()

            except httpx.HTTPError as exc:
                last_exc = exc
                self._logger.warning(
                    "ebay_search_failed",
                    url=url,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt < self.max_retries:
                    delay = 2.0 ** attempt
                    await asyncio.sleep(delay)
                else:
                    self.request_metrics["failures"] += 1

        raise last_exc or RuntimeError("eBay search request failed")

    # ------------------------------------------------------------------
    # Fetch (abstract method)
    # ------------------------------------------------------------------

    async def fetch(self, search_results: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """Extract item summaries from the search response."""
        if isinstance(search_results, dict):
            return list(search_results.get("itemSummaries", []))
        if isinstance(search_results, list):
            return search_results
        return []

    # ------------------------------------------------------------------
    # Normalize (abstract method)
    # ------------------------------------------------------------------

    async def normalize(self, item: Any, **kwargs: Any) -> Listing:
        """Convert an eBay item summary dict into a Listing model."""
        if isinstance(item, Listing):
            return item

        payload = dict(item)
        title = (payload.get("title") or "").strip()
        price = self._parse_price(payload.get("price"))
        external_id = payload.get("itemId") or ""
        url = payload.get("itemWebUrl") or ""
        condition = payload.get("condition")
        description_parts: list[str] = []
        if condition:
            description_parts.append(f"Condition: {condition}")
        seller = payload.get("seller")
        if seller and isinstance(seller, dict):
            username = seller.get("username")
            if username:
                description_parts.append(f"Seller: {username}")
        description = " | ".join(description_parts) if description_parts else None

        return Listing(
            title=title,
            description=description,
            price=price,
            source="ebay",
            external_id=external_id,
            url=url,
            category=kwargs.get("category"),
            status=ListingStatus.NEW,
        )

    @staticmethod
    def _parse_price(price_obj: Any) -> float:
        """Extract a numeric price from the eBay price object or raw value."""
        if price_obj is None:
            return 0.0
        if isinstance(price_obj, (int, float)):
            return float(price_obj)
        if isinstance(price_obj, dict):
            value = price_obj.get("value")
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0
        if isinstance(price_obj, str):
            cleaned = price_obj.replace(",", "").replace("$", "").strip()
            if cleaned:
                try:
                    return float(cleaned)
                except ValueError:
                    return 0.0
        return 0.0

    # ------------------------------------------------------------------
    # Validate (abstract method)
    # ------------------------------------------------------------------

    async def validate(self, item: Listing, **kwargs: Any) -> bool:
        """Return True when a normalized listing is acceptable to persist."""
        return (
            isinstance(item, Listing)
            and bool(item.title)
            and item.price >= 0
            and bool(item.external_id or item.url)
        )

    # ------------------------------------------------------------------
    # Save (abstract method)
    # ------------------------------------------------------------------

    async def save(self, items: Iterable[Any], **kwargs: Any) -> list[Listing]:
        """Persist validated listings with deduplication by source:external_id."""
        saved: list[Listing] = []
        for item in items:
            listing = (
                item
                if isinstance(item, Listing)
                else await self.normalize(item, **kwargs)
            )
            if not await self.validate(listing, **kwargs):
                continue

            identity = listing.external_id or listing.url or listing.title
            key = f"{listing.source}:{identity}"
            if key in self._seen_ids:
                continue

            if self.repository is not None:
                existing = self.repository.get_by_external_id(
                    listing.external_id, listing.source
                )
                if existing is not None:
                    self._seen_ids.add(key)
                    saved.append(existing)
                    continue
                listing = self.repository.create(listing)

            self._seen_ids.add(key)
            saved.append(listing)

        return saved


__all__ = ["EbayCollector", "EbayAuthError"]
