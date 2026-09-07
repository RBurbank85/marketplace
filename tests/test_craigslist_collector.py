import pytest
from pathlib import Path

from collectors.craigslist import CraigslistCollector
from database.database import initialize_database
from database.models import Listing, ListingStatus
from database.repositories import ListingRepository


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "craigslist_search.html"


@pytest.mark.asyncio
async def test_craigslist_search_reads_fixture_html():
    collector = CraigslistCollector(obey_robots=False, request_delay=0)

    html = await collector.search("desk", fixture_path=str(FIXTURE_PATH))

    assert isinstance(html, str)
    assert "Vintage Camera" in html


@pytest.mark.asyncio
async def test_craigslist_fixture_search_respects_pagination_limit():
    collector = CraigslistCollector(obey_robots=False, request_delay=0)

    html = await collector.search(
        "desk", fixture_path=str(FIXTURE_PATH), pagination_limit=2
    )

    assert html.count("Vintage Camera") == 2


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


@pytest.mark.asyncio
async def test_craigslist_save_persists_and_deduplicates_by_source(tmp_path):
    database_url = str(tmp_path / "craigslist.db")
    initialize_database(database_url)
    collector = CraigslistCollector(
        database_url=database_url, obey_robots=False, request_delay=0
    )
    html = await collector.search("desk", fixture_path=str(FIXTURE_PATH))
    results = await collector.fetch(html)
    listings = [await collector.normalize(result) for result in results]

    first = await collector.save(listings + [listings[0]])
    second = await collector.save(listings)

    repository = ListingRepository(database_url=database_url)
    assert len(first) == 3
    assert len(second) == 0
    assert len(repository.list()) == 3


def test_craigslist_generate_search_queries_expands_terms():
    collector = CraigslistCollector(obey_robots=False, request_delay=0)

    queries = collector.generate_search_queries("desk", category="electronics")

    assert "desk" in queries
    assert any("bundle" in query.lower() for query in queries)
    assert any("must sell" in query.lower() for query in queries)


@pytest.mark.asyncio
async def test_craigslist_network_options_control_timeout_and_pagination(monkeypatch):
    requests = []

    class FakeResponse:
        text = "<html></html>"

    async def fake_get(url, **kwargs):
        requests.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr("collectors.craigslist.network_client.get", fake_get)
    collector = CraigslistCollector(obey_robots=False, request_delay=0)

    await collector.search(
        "desk",
        pagination_limit=2,
        request_timeout=4.5,
        rate_limit_per_minute=0,
        credentials={"token": "must-not-be-sent"},
    )

    assert [url for url, _ in requests] == [
        "https://www.craigslist.org/search/sss?query=desk",
        "https://www.craigslist.org/search/sss?query=desk&s=120",
    ]
    assert all(kwargs["timeout"] == 4.5 for _, kwargs in requests)
    assert all("credentials" not in kwargs for _, kwargs in requests)
    assert "must-not-be-sent" not in str(requests)


@pytest.mark.asyncio
async def test_craigslist_rate_limit_paces_requests(monkeypatch):
    sleeps = []

    class FakeResponse:
        text = "<html></html>"

    async def fake_get(url, **kwargs):
        return FakeResponse()

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("collectors.craigslist.network_client.get", fake_get)
    monkeypatch.setattr("collectors.craigslist.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("collectors.craigslist.time.monotonic", lambda: 0.0)
    collector = CraigslistCollector(obey_robots=False, request_delay=0)

    await collector._fetch_html(
        "https://www.craigslist.org/search/sss?query=desk",
        rate_limit_per_minute=60,
    )
    await collector._fetch_html(
        "https://www.craigslist.org/search/sss?query=desk&s=120",
        rate_limit_per_minute=60,
    )

    assert sleeps == [1.0]
