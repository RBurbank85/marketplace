from __future__ import annotations

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
            title_node = node.css_first(".result-title, .titlestring")
            price_node = node.css_first(".result-price, .price")
            description_node = node.css_first(
                ".result-description, .description, .result-meta"
            )

            title = title_node.text().strip() if title_node else ""
            url = title_node.attributes.get("href", "") if title_node else ""
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
        return items

    def _parse_bs4(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        items = []

        for node in soup.select(".result-row, .cl-static-search-result, .result"):
            title_node = node.select_one(".result-title, .titlestring")
            price_node = node.select_one(".result-price, .price")
            description_node = node.select_one(
                ".result-description, .description, .result-meta"
            )

            title = title_node.get_text().strip() if title_node else ""
            url = title_node.get("href", "") if title_node else ""
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
        return items


# Register the parser
ParserRegistry.register("craigslist", CraigslistParser)
