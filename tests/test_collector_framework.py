import pytest

from collectors.base import BaseCollector, CollectorRegistry, discover_collectors


class DummyCollector(BaseCollector):
    name = "dummy"

    async def search(self, query, **kwargs):
        return [{"query": query}]

    async def fetch(self, search_results, **kwargs):
        return search_results

    async def normalize(self, item, **kwargs):
        return {"query": item["query"], "normalized": True}

    async def validate(self, item, **kwargs):
        return bool(item.get("query"))

    async def save(self, items, **kwargs):
        return len(items)


class FilteringCollector(DummyCollector):
    name = "filtering"

    def __init__(self):
        self.saved = []

    async def search(self, query, **kwargs):
        return [{"query": "valid"}, {"query": ""}]

    async def normalize(self, item, **kwargs):
        return {"query": item["query"], "source": "test"}

    async def save(self, items, **kwargs):
        self.saved = list(items)
        return self.saved


def test_base_collector_registers_concrete_subclasses():
    assert CollectorRegistry.get("DummyCollector") is DummyCollector
    assert CollectorRegistry.get("dummy") is DummyCollector


def test_base_collector_cannot_be_instantiated_without_implementations():
    with pytest.raises(TypeError):

        class BrokenCollector(BaseCollector):
            pass

        BrokenCollector()


@pytest.mark.asyncio
async def test_run_orchestrates_the_collector_pipeline():
    collector = DummyCollector()
    assert await collector.run("books") == 1


@pytest.mark.asyncio
async def test_run_validates_before_saving_and_skips_invalid_items():
    collector = FilteringCollector()

    assert await collector.run("books") == 1
    assert collector.saved == [{"query": "valid", "source": "test"}]


def test_discover_collectors_imports_modules_from_the_package():
    collectors = discover_collectors()
    assert DummyCollector in collectors


def test_generate_search_queries_expands_base_query_with_category_terms():
    collector = DummyCollector()

    queries = collector.generate_search_queries("marantz receiver", category="audio")
    lowered = {query.lower() for query in queries}

    assert "marantz receiver" in lowered
    assert "maranz receiver" in lowered
    assert "marantz receiver bundle" in lowered
    assert "marantz receiver must sell" in lowered


def test_generate_search_queries_returns_deduplicated_candidates():
    collector = DummyCollector()

    queries = collector.generate_search_queries(
        "receiver", category="audio", max_queries=10
    )

    assert len(queries) <= 10
    assert len(set(queries)) == len(queries)


@pytest.mark.asyncio
async def test_run_can_execute_expanded_search_set():
    collector = DummyCollector()

    result = await collector.run(
        "marantz receiver", expand_searches=True, category="audio"
    )

    assert result > 1
