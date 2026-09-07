from __future__ import annotations

import re
import asyncio
import time
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

from loguru import logger

from collectors.base import BaseCollector
from collectors.parsers.craigslist import CraigslistParser
from core.networking import network_client
from core.identity import identity_service, IdentityPolicy
from database.models import Listing, ListingStatus
from database.repositories import ListingRepository


class CraigslistCollector(BaseCollector):
    """Collector implementation for Craigslist search results."""

    name = "craigslist"

    def __init__(
        self,
        *,
        base_url: str = "https://www.craigslist.org",
        search_path: str = "/search/sss",
        location: str | None = None,
        request_delay: float = 2.0,
        max_retries: int = 2,
        obey_robots: bool = True,
        seen_ids: Iterable[str] | None = None,
        database_url: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.search_path = search_path
        self.location = location
        self.database_url = database_url
        self.repository = (
            ListingRepository(database_url=database_url) if database_url else None
        )
        self._seen_ids: set[str] = set(seen_ids or [])
        self._last_request_at: float | None = None
        self._logger = logger.bind(component="craigslist_collector")

        # Register collector policy
        identity_service.register_policy(
            IdentityPolicy(
                name=self.name,
                min_delay=request_delay,
                max_delay=request_delay * 2,
                obey_robots=obey_robots,
            )
        )

    def _build_search_url(self, query: str, *, location: str | None = None) -> str:
        if location and "." not in location:
            host = f"https://{location}.craigslist.org"
        elif location:
            host = location
        else:
            host = self.base_url
        return f"{host}{self.search_path}?query={quote(query)}"

    def _read_fixture(self, fixture_path: str | None) -> str | None:
        if not fixture_path:
            return None
        path = Path(fixture_path)
        if not path.exists():
            raise FileNotFoundError(f"Fixture not found: {fixture_path}")
        return path.read_text(encoding="utf-8")

    async def _fetch_html(
        self,
        url: str,
        *,
        fixture_path: str | None = None,
        request_timeout: float | None = None,
        page: int = 0,
        rate_limit_per_minute: int | None = None,
    ) -> str:
        fixture_content = self._read_fixture(fixture_path)
        if fixture_content is not None:
            self._logger.info("fixture_loaded", url=url, fixture_path=fixture_path)
            return fixture_content

        if rate_limit_per_minute and rate_limit_per_minute > 0:
            interval = 60.0 / rate_limit_per_minute
            if self._last_request_at is not None:
                wait_seconds = interval - (time.monotonic() - self._last_request_at)
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)

        self._last_request_at = time.monotonic()
        response = await network_client.get(
            url,
            collector_name=self.name,
            timeout=request_timeout,
        )
        return response.text

    @staticmethod
    def _page_url(url: str, page: int) -> str:
        if page == 0:
            return url
        parsed = urlsplit(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["s"] = str(page * 120)
        return urlunsplit(parsed._replace(query=urlencode(query)))

    async def search(self, query: str, **kwargs: Any) -> str:
        url = kwargs.get("url") or self._build_search_url(
            query, location=kwargs.get("location", self.location)
        )
        fixture_path = kwargs.get("fixture_path")
        if fixture_path:
            html = await self._fetch_html(url, fixture_path=fixture_path)
        else:
            page_limit = max(1, int(kwargs.get("pagination_limit", 1)))
            pages = [
                await self._fetch_html(
                    self._page_url(url, page),
                    request_timeout=kwargs.get("request_timeout"),
                    page=page,
                    rate_limit_per_minute=kwargs.get("rate_limit_per_minute"),
                )
                for page in range(page_limit)
            ]
            html = "\n".join(pages)
        self._logger.info(
            "search_completed", query=query, source=self.name, url=url, length=len(html)
        )
        return html

    async def fetch(self, search_results: Any, **kwargs: Any) -> list[dict[str, Any]]:
        if isinstance(search_results, str):
            parser = CraigslistParser()
            items = parser.parse(search_results)
            return [
                self._shape_listing(
                    item, base_url=kwargs.get("base_url", self.base_url)
                )
                for item in items
            ]

        if isinstance(search_results, list):
            return [
                self._shape_listing(
                    item, base_url=kwargs.get("base_url", self.base_url)
                )
                for item in search_results
            ]

        return []

    async def normalize(self, item: Any, **kwargs: Any) -> Listing:
        if isinstance(item, Listing):
            return item

        payload = dict(item)
        title = (payload.get("title") or "").strip()
        price = self._parse_price(payload.get("price"))
        external_id = payload.get("external_id") or self._extract_external_id(
            payload.get("url") or ""
        )
        url = self._absolute_url(
            payload.get("url") or "", base_url=kwargs.get("base_url", self.base_url)
        )

        return Listing(
            title=title,
            description=(payload.get("description") or None),
            price=price,
            source="craigslist",
            external_id=external_id,
            url=url,
            status=ListingStatus.NEW,
        )

    async def validate(self, item: Listing, **kwargs: Any) -> bool:
        return (
            isinstance(item, Listing)
            and bool(item.title)
            and item.price >= 0
            and bool(item.external_id or item.url)
        )

    async def save(self, items: Iterable[Any], **kwargs: Any) -> list[Listing]:
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

    def _shape_listing(
        self, item: Mapping[str, Any], *, base_url: str
    ) -> dict[str, Any]:
        title = (item.get("title") or "").strip()
        url = self._absolute_url(item.get("url") or "", base_url=base_url)
        return {
            "title": title,
            "url": url,
            "price": item.get("price", ""),
            "description": item.get("description"),
            "external_id": item.get("external_id"),
        }

    def _absolute_url(self, href: str, *, base_url: str) -> str:
        if not href:
            return ""
        if href.startswith("http"):
            return href
        return urljoin(f"{base_url.rstrip('/')}/", href.lstrip("/"))

    def _extract_external_id(self, href: str) -> str | None:
        match = re.search(r"/(\d+)(?:\.html)?$", href)
        if match:
            return match.group(1)
        return None

    def _parse_price(self, value: Any) -> float:
        if value in (None, ""):
            return 0.0

        cleaned = re.sub(r"[^0-9.\-]", "", str(value))
        if not cleaned:
            return 0.0
        return float(cleaned)


__all__ = ["CraigslistCollector"]
