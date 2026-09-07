import pytest
from pathlib import Path

from collectors.craigslist import CraigslistCollector
from database.models import Listing, ListingStatus


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "craigslist_search.html"


@pytest.mark.asyncio
async def test_craigslist_search_reads_fixture_html():
    collector = CraigslistCollector(obey_robots=False, request_delay=0)

    html = await collector.search("desk", fixture_path=str(FIXTURE_PATH))

    assert isinstance(html, str)
    assert "Vintage Camera" in html


@pytest.mark.asyncio
async def test_craigslist_fetch_and_normalize_listing_data():
    collector = CraigslistCollector(obey_robots=False, request_delay=0)
    html = await collector.search("desk", fixture_path=str(FIXTURE_PATH))
    results = await collector.fetch(html)

    assert len(results) == 3

    normalized = await collector.normalize(results[0])

    assert isinstance(normalized, Listing)
    assert normalized.title == "Vintage Camera"
    assert normalized.price == 50.0
    assert normalized.source == "craigslist"
    assert normalized.external_id == "7700000001"
    assert normalized.url.endswith("/sfc/ele/7700000001.html")
    assert normalized.status == ListingStatus.NEW


@pytest.mark.asyncio
async def test_craigslist_save_deduplicates_items():
    collector = CraigslistCollector(obey_robots=False, request_delay=0)
    html = await collector.search("desk", fixture_path=str(FIXTURE_PATH))
    results = await collector.fetch(html)

    first = await collector.normalize(results[0])
    second = await collector.normalize(results[0])

    saved = await collector.save([first, second])

    assert len(saved) == 1
    assert saved[0].external_id == "7700000001"


def test_craigslist_generate_search_queries_expands_terms():
    collector = CraigslistCollector(obey_robots=False, request_delay=0)

    queries = collector.generate_search_queries("desk", category="electronics")

    assert "desk" in queries
    assert any("bundle" in query.lower() for query in queries)
    assert any("must sell" in query.lower() for query in queries)
