from __future__ import annotations

import re
from typing import Any
from loguru import logger

try:
    from selectolax.parser import HTMLParser

    USE_SELECTOLAX = True
except ImportError:
    USE_SELECTOLAX = False
    try:
        from bs4 import BeautifulSoup

        USE_BS4 = True
    except ImportError:
        USE_BS4 = False

from core.parsing import BaseParser, ParserRegistry


class CraigslistParser(BaseParser):
    """Resilient parser for Craigslist search results using CSS selectors."""

    def parse(self, html: str) -> list[dict[str, Any]]:
        if USE_SELECTOLAX:
            return self._parse_selectolax(html)
        elif USE_BS4:
            return self._parse_bs4(html)
        else:
            logger.error("No suitable HTML parser found (selectolax or beautifulsoup4)")
            return []

    def _parse_selectolax(self, html: str) -> list[dict[str, Any]]:
        tree = HTMLParser(html)
        items = []

        # Craigslist search result rows
        # Common selectors: .result-row, .cl-static-search-result, .result
        for node in tree.css(".result-row, .cl-static-search-result, .result"):
            # Title selectors across Craigslist layout versions:
            #   - Legacy: .result-title, .titlestring (href on the title <a> tag)
            #   - Current: .title (inside a parent <a> tag that carries the href)
            title_node = node.css_first(
                ".result-title, .titlestring, .title"
            )
            price_node = node.css_first(".result-price, .price")
            description_node = node.css_first(
                ".result-description, .description, .result-meta"
            )

            title = title_node.text().strip() if title_node else ""

            # URL extraction: try the title node's href first (legacy layout),
            # then fall back to the nearest ancestor <a> tag (current layout)
            # or a direct <a> child within the result node.
            url = ""
            if title_node:
                url = title_node.attributes.get("href", "") or ""
            if not url:
                anchor = node.css_first("a")
                if anchor:
                    url = anchor.attributes.get("href", "") or ""

            # Fall back to the li title attribute if text is empty
            if not title:
                title = node.attributes.get("title", "") or ""

            price = price_node.text().strip() if price_node else ""
            description = (
                description_node.text().strip() if description_node else None
            )
            external_id = node.attributes.get("data-id") or node.attributes.get("id")

            if title and url:
                items.append(
                    {
                        "title": title,
                        "url": url,
                        "price": price,
                        "description": description,
                        "external_id": external_id,
                    }
                )
        return self._deduplicate(items)

    def _parse_bs4(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        items = []

        for node in soup.select(".result-row, .cl-static-search-result, .result"):
            title_node = node.select_one(".result-title, .titlestring, .title")
            price_node = node.select_one(".result-price, .price")
            description_node = node.select_one(
                ".result-description, .description, .result-meta"
            )

            title = title_node.get_text().strip() if title_node else ""
            url = title_node.get("href", "") if title_node else ""
            if not url:
                anchor = node.find("a")
                if anchor:
                    url = anchor.get("href", "") or ""
            if not title:
                title = node.get("title", "") or ""
            price = price_node.get_text().strip() if price_node else ""
            description = (
                description_node.get_text().strip() if description_node else None
            )
            external_id = node.get("data-id") or node.get("id")

            if title and url:
                items.append(
                    {
                        "title": title,
                        "url": url,
                        "price": price,
                        "description": description,
                        "external_id": external_id,
                    }
                )
        return self._deduplicate(items)

    @staticmethod
    def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for item in items:
            external_id = item.get("external_id")
            if not external_id or not str(external_id).isdigit():
                # Match both legacy numeric IDs and current alphanumeric IDs
                match = re.search(r"/(\d+)(?:\.html)?(?:[?#].*)?$", item["url"])
                if not match:
                    match = re.search(r"/([A-Za-z0-9]{10,})(?:[?#].*)?$", item["url"])
                external_id = match.group(1) if match else item["url"]
            key = str(external_id)
            if key in seen:
                continue
            seen.add(key)
            item["external_id"] = str(external_id) if external_id else None
            unique.append(item)
        return unique


# Register the parser
ParserRegistry.register("craigslist", CraigslistParser)
