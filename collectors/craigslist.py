from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote, urljoin

from loguru import logger

from collectors.base import BaseCollector
from collectors.parsers.craigslist import CraigslistParser
from core.networking import network_client
from core.identity import identity_service, IdentityPolicy
from database.models import Listing, ListingStatus


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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.search_path = search_path
        self.location = location
        self._seen_ids: set[str] = set(seen_ids or [])
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

    async def _fetch_html(self, url: str, *, fixture_path: str | None = None) -> str:
        fixture_content = self._read_fixture(fixture_path)
        if fixture_content is not None:
            self._logger.info("fixture_loaded", url=url, fixture_path=fixture_path)
            return fixture_content

        response = await network_client.get(url, collector_name=self.name, timeout=10)
        return response.text

    async def search(self, query: str, **kwargs: Any) -> str:
        url = kwargs.get("url") or self._build_search_url(
            query, location=kwargs.get("location", self.location)
        )
        html = await self._fetch_html(url, fixture_path=kwargs.get("fixture_path"))
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
