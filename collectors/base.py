"""Generic collector framework for marketplace integrations."""

from __future__ import annotations

import importlib
import pkgutil
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar, Iterable

from uuid import uuid4
from core.plugins import CollectorPlugin
from core.events.bus import bus
from core.events.base import (
    ListingDiscovered,
    ListingStored,
    ListingValidated,
    CollectorStarted,
    CollectorFinished,
    CollectorFailed
)

from analysis.search import SearchGenerator


class CollectorRegistry:
    """Registry for discoverable collector subclasses."""

    _registry: ClassVar[dict[str, type["BaseCollector"]]] = {}

    @classmethod
    def register(cls, name: str, collector_cls: type["BaseCollector"]) -> None:
        cls._registry[name.lower()] = collector_cls

    @classmethod
    def get(cls, name: str) -> type["BaseCollector"] | None:
        if not name:
            return None
        return cls._registry.get(name.lower())

    @classmethod
    def all(cls) -> list[type["BaseCollector"]]:
        return list(cls._registry.values())


class BaseCollector(CollectorPlugin, ABC):
    """Abstract base class for all marketplace collectors."""

    name: str | None = None

    def generate_search_queries(
        self, query: str, *, category: str | None = None, max_queries: int = 24
    ) -> list[str]:
        """Expand a seed query into optimized collector searches."""
        category_plugin = self._resolve_category(category)
        generator = SearchGenerator(category=category_plugin)
        return generator.generate(query, max_queries=max_queries)

    def _resolve_category(self, category: str | None) -> Any | None:
        if not category:
            return None
        from categories.catalog import get_category

        return get_category(category)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls is BaseCollector:
            return
        collector_name = getattr(cls, "name", None) or cls.__name__
        CollectorRegistry.register(collector_name, cls)
        CollectorRegistry.register(cls.__name__, cls)

    def _reset_run_metrics(self) -> None:
        self.last_run_metrics = {
            "discovered": 0,
            "persisted": 0,
            "skipped": 0,
            "failed": 0,
        }
    @abstractmethod
    async def search(self, query: str, **kwargs: Any) -> Any:
        """Fetch the raw search results from a marketplace."""

    @abstractmethod
    async def fetch(self, search_results: Any, **kwargs: Any) -> Any:
        """Retrieve the relevant listing payloads from search results."""

    @abstractmethod
    async def normalize(self, item: Any, **kwargs: Any) -> Any:
        """Normalize a fetched item into a consistent internal representation."""

    @abstractmethod
    async def validate(self, item: Any, **kwargs: Any) -> bool:
        """Return True when a normalized item is acceptable to persist."""

    @abstractmethod
    async def save(self, items: Iterable[Any], **kwargs: Any) -> Any:
        """Persist the validated items through the configured storage layer."""

    async def run(self, query: str, **kwargs: Any) -> Any:
        """Execute the full pipeline for a search query."""
        session_id = uuid4()
        self._reset_run_metrics()
        collector_name = getattr(self, "name", None) or self.__class__.__name__
        
        await bus.publish(CollectorStarted(
            collector_name=collector_name,
            session_id=session_id
        ))

        try:
            search_queries = kwargs.get("search_queries")
            if search_queries is None and kwargs.get("expand_searches", False):
                search_queries = self.generate_search_queries(
                    query, category=kwargs.get("category")
                )

            if search_queries is None:
                search_queries = [query]
            elif isinstance(search_queries, str):
                search_queries = [search_queries]
            elif not isinstance(search_queries, (list, tuple, set)):
                search_queries = [search_queries]

            valid_items: list[Any] = []
            for search_query in search_queries:
                search_results = await self.search(search_query, **kwargs)
                fetched_items = await self.fetch(search_results, **kwargs)

                if fetched_items is None:
                    fetched_items = []
                elif isinstance(fetched_items, (str, bytes)):
                    fetched_items = [fetched_items]
                elif not isinstance(fetched_items, (list, tuple, set)):
                    fetched_items = [fetched_items]

                for item in fetched_items:
                    normalized_item = await self.normalize(item, **kwargs)
                    if not await self.validate(normalized_item, **kwargs):
                        self.last_run_metrics["skipped"] += 1
                        continue

                    self.last_run_metrics["discovered"] += 1
                    event_data = self._event_data(normalized_item)
                    await bus.publish(ListingDiscovered(
                        external_id=event_data.get("external_id") or "unknown",
                        source=event_data.get("source") or self.name or "unknown",
                        data=event_data,
                    ))

                    await bus.publish(ListingValidated(
                        external_id=event_data.get("external_id") or "unknown",
                        source=event_data.get("source") or self.name or "unknown",
                        data=event_data,
                    ))
                    valid_items.append(normalized_item)

            saved_items = await self.save(valid_items, **kwargs)
            listings_count = self._saved_count(saved_items, valid_items)
            self.last_run_metrics["persisted"] = listings_count
            self.last_run_metrics["skipped"] += len(valid_items) - listings_count
            if isinstance(saved_items, Iterable) and not isinstance(
                saved_items, (str, bytes, Mapping)
            ):
                for saved_item in saved_items:
                    event_data = self._event_data(saved_item)
                    listing_id = event_data.get("id")
                    if listing_id is None:
                        continue
                    await bus.publish(ListingStored(
                        listing_id=listing_id,
                        external_id=event_data.get("external_id") or "unknown",
                        source=event_data.get("source") or self.name or "unknown",
                        data=event_data,
                    ))

            await bus.publish(CollectorFinished(
                collector_name=collector_name,
                session_id=session_id,
                listings_count=listings_count
            ))
            return listings_count

        except Exception as e:
            self.last_run_metrics["failed"] += 1
            import traceback
            await bus.publish(CollectorFailed(
                collector_name=collector_name,
                session_id=session_id,
                error=str(e),
                stack_trace=traceback.format_exc()
            ))
            raise e

    @staticmethod
    def _event_data(item: Any) -> dict[str, Any]:
        if isinstance(item, Mapping):
            return dict(item)
        if hasattr(item, "model_dump"):
            return item.model_dump()
        if hasattr(item, "__dict__"):
            return dict(vars(item))
        return {"value": item}

    @staticmethod
    def _saved_count(saved_items: Any, valid_items: list[Any]) -> int:
        if isinstance(saved_items, int):
            return saved_items
        if saved_items is None:
            return len(valid_items)
        if isinstance(saved_items, (str, bytes, Mapping)):
            return len(valid_items)
        try:
            return len(saved_items)
        except TypeError:
            return len(valid_items)


def discover_collectors(package_name: str = "collectors") -> list[type[BaseCollector]]:
    """Import collector modules and return all registered collector classes."""
    package = importlib.import_module(package_name)
    for _, module_name, _ in pkgutil.iter_modules(
        package.__path__, package.__name__ + "."
    ):
        if module_name.endswith(".base"):
            continue
        importlib.import_module(module_name)
    return CollectorRegistry.all()


__all__ = ["BaseCollector", "CollectorRegistry", "discover_collectors"]
