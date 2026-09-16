"""Tests for the eBay Browse API collector.

Tests use the fixture file (ebay_search.json) and httpx MockTransport
to avoid live API calls. The conftest blocks all ebay.com network access
unless using MockTransport.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from collectors.ebay import EbayAuthError, EbayCollector
from database.database import initialize_database
from database.models import Listing, ListingStatus
from database.repositories import ListingRepository


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ebay_search.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _mock_transport(handler):
    """Return a MockTransport-wrapped httpx.AsyncClient for testing."""
    return httpx.MockTransport(handler)


# --- Fixture-based tests (no network, no credentials) -----------------------


@pytest.mark.asyncio
async def test_ebay_search_reads_fixture_json():
    collector = EbayCollector(request_delay=0)

    result = await collector.search("guitar", fixture_path=str(FIXTURE_PATH))

    assert isinstance(result, dict)
    assert len(result["itemSummaries"]) == 3
    assert result["total"] == 3


@pytest.mark.asyncio
async def test_ebay_fetch_extracts_item_summaries():
    collector = EbayCollector(request_delay=0)
    search_result = await collector.search("guitar", fixture_path=str(FIXTURE_PATH))

    items = await collector.fetch(search_result)

    assert len(items) == 3
    assert items[0]["title"] == "Fender Player Stratocaster Electric Guitar - Sunburst"


@pytest.mark.asyncio
async def test_ebay_normalize_creates_listing():
    collector = EbayCollector(request_delay=0)
    search_result = await collector.search("guitar", fixture_path=str(FIXTURE_PATH))
    items = await collector.fetch(search_result)

    listing = await collector.normalize(items[0])

    assert isinstance(listing, Listing)
    assert listing.title == "Fender Player Stratocaster Electric Guitar - Sunburst"
    assert listing.price == 599.99
    assert listing.source == "ebay"
    assert listing.external_id == "v1|110000000001|0"
    assert listing.url == "https://www.ebay.com/itm/110000000001"
    assert listing.status == ListingStatus.NEW
    assert "Condition: Used" in (listing.description or "")
    assert "Seller: guitar_seller_1" in (listing.description or "")


@pytest.mark.asyncio
async def test_ebay_normalize_handles_missing_price():
    collector = EbayCollector(request_delay=0)

    listing = await collector.normalize({"itemId": "v1|123|0", "title": "No Price Item"})

    assert listing.price == 0.0
    assert listing.external_id == "v1|123|0"


@pytest.mark.asyncio
async def test_ebay_normalize_accepts_raw_price_float():
    collector = EbayCollector(request_delay=0)

    listing = await collector.normalize(
        {"itemId": "v1|456|0", "title": "Float Price", "price": 42.5}
    )

    assert listing.price == 42.5


@pytest.mark.asyncio
async def test_ebay_validate_requires_title_and_id():
    collector = EbayCollector(request_delay=0)

    good = Listing(
        title="Test", price=10.0, source="ebay", external_id="v1|1|0"
    )
    assert await collector.validate(good) is True

    no_title = Listing(title="", price=10.0, source="ebay", external_id="v1|2|0")
    assert await collector.validate(no_title) is False

    no_id = Listing(title="Test", price=10.0, source="ebay", external_id="", url="")
    assert await collector.validate(no_id) is False  # no id or url


@pytest.mark.asyncio
async def test_ebay_save_deduplicates_items():
    collector = EbayCollector(request_delay=0)
    search_result = await collector.search("guitar", fixture_path=str(FIXTURE_PATH))
    items = await collector.fetch(search_result)

    first = await collector.normalize(items[0])
    second = await collector.normalize(items[0])

    saved = await collector.save([first, second])

    assert len(saved) == 1
    assert saved[0].external_id == "v1|110000000001|0"


@pytest.mark.asyncio
async def test_ebay_save_persists_and_deduplicates_by_source(tmp_path):
    database_url = str(tmp_path / "ebay.db")
    initialize_database(database_url)
    collector = EbayCollector(database_url=database_url, request_delay=0)
    search_result = await collector.search("guitar", fixture_path=str(FIXTURE_PATH))
    items = await collector.fetch(search_result)
    listings = [await collector.normalize(item) for item in items]

    first = await collector.save(listings + [listings[0]])
    second = await collector.save(listings)

    repository = ListingRepository(database_url=database_url)
    assert len(first) == 3
    assert len(second) == 0
    assert len(repository.list()) == 3


# --- Credential error tests -------------------------------------------------


@pytest.mark.asyncio
async def test_ebay_missing_credentials_raises_auth_error():
    collector = EbayCollector(request_delay=0)

    with pytest.raises(EbayAuthError, match="client_id"):
        await collector.search("guitar")


@pytest.mark.asyncio
async def test_ebay_search_with_credentials_uses_mock_transport(monkeypatch):
    """Verify the search request sends Bearer token and marketplace header."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "itemSummaries": [
                    {
                        "itemId": "v1|999|0",
                        "title": "Mock Item",
                        "price": {"value": "25.00", "currency": "USD"},
                        "itemWebUrl": "https://www.ebay.com/itm/999",
                    }
                ],
                "total": 1,
            },
        )

    def token_handler(request: httpx.Request) -> httpx.Response:
        captured["token_url"] = str(request.url)
        captured["token_headers"] = dict(request.headers)
        # Read the form body
        body = request.content.decode("utf-8")
        captured["token_body"] = body
        return httpx.Response(
            200,
            json={
                "access_token": "test-access-token",
                "expires_in": 7200,
                "token_type": "Application Access Token",
            },
        )

    # Build a transport that routes token and search differently
    def unified_handler(request: httpx.Request) -> httpx.Response:
        if "oauth2/token" in str(request.url):
            return token_handler(request)
        return handler(request)

    collector = EbayCollector(request_delay=0)

    # Inject our mock client
    mock_client = httpx.AsyncClient(transport=_mock_transport(unified_handler))

    async def fake_get_client():
        return mock_client

    monkeypatch.setattr(collector, "_get_client", fake_get_client)

    result = await collector.search(
        "guitar",
        credentials={"client_id": "test-app-id", "client_secret": "test-cert-id"},
    )

    assert len(result["itemSummaries"]) == 1
    assert captured["token_url"] == "https://api.ebay.com/identity/v1/oauth2/token"
    assert captured["token_headers"]["authorization"].startswith("Basic ")
    assert "grant_type=client_credentials" in captured["token_body"]
    assert captured["headers"]["authorization"] == "Bearer test-access-token"
    assert captured["headers"]["x-ebay-c-marketplace-id"] == "EBAY_US"


@pytest.mark.asyncio
async def test_ebay_token_caching_avoids_duplicate_token_requests(monkeypatch):
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if "oauth2/token" in str(request.url):
            token_calls += 1
            return httpx.Response(
                200,
                json={
                    "access_token": "cached-token",
                    "expires_in": 7200,
                    "token_type": "Application Access Token",
                },
            )
        return httpx.Response(
            200,
            json={"itemSummaries": [], "total": 0},
        )

    collector = EbayCollector(request_delay=0)
    mock_client = httpx.AsyncClient(transport=_mock_transport(handler))

    async def fake_get_client():
        return mock_client

    monkeypatch.setattr(collector, "_get_client", fake_get_client)

    creds = {"client_id": "app-id", "client_secret": "cert-id"}
    await collector.search("guitar", credentials=creds)
    await collector.search("drums", credentials=creds)

    assert token_calls == 1  # token was cached


@pytest.mark.asyncio
async def test_ebay_401_triggers_token_refresh(monkeypatch):
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if "oauth2/token" in str(request.url):
            token_calls += 1
            return httpx.Response(
                200,
                json={
                    "access_token": f"token-{token_calls}",
                    "expires_in": 7200,
                    "token_type": "Application Access Token",
                },
            )
        # First search call returns 401, second returns data
        auth = request.headers.get("authorization", "")
        if auth == "Bearer token-1":
            return httpx.Response(401, json={"error": "invalid_token"})
        return httpx.Response(
            200,
            json={
                "itemSummaries": [
                    {
                        "itemId": "v1|1|0",
                        "title": "Refreshed Item",
                        "price": {"value": "10.00", "currency": "USD"},
                        "itemWebUrl": "https://www.ebay.com/itm/1",
                    }
                ],
                "total": 1,
            },
        )

    collector = EbayCollector(request_delay=0, max_retries=1)
    mock_client = httpx.AsyncClient(transport=_mock_transport(handler))

    async def fake_get_client():
        return mock_client

    monkeypatch.setattr(collector, "_get_client", fake_get_client)

    result = await collector.search(
        "guitar",
        credentials={"client_id": "app-id", "client_secret": "cert-id"},
    )

    assert len(result["itemSummaries"]) == 1
    assert token_calls == 2  # initial + refresh


@pytest.mark.asyncio
async def test_ebay_credentials_not_sent_in_fixture_mode():
    """Ensure credentials are not required and not leaked when using fixture."""
    collector = EbayCollector(request_delay=0)

    result = await collector.search(
        "guitar",
        fixture_path=str(FIXTURE_PATH),
        credentials={"client_id": "secret-app-id", "client_secret": "secret-cert"},
    )

    assert len(result["itemSummaries"]) == 3
    # No HTTP client should have been created for fixture mode
    assert collector._client is None


@pytest.mark.asyncio
async def test_ebay_full_pipeline_run_with_fixture():
    collector = EbayCollector(request_delay=0)
    search_result = await collector.search("guitar", fixture_path=str(FIXTURE_PATH))

    count = await collector.run(
        query="guitar",
        search_queries=["guitar"],
        fixture_path=str(FIXTURE_PATH),
    )

    assert count == 3
    assert collector.last_run_metrics["discovered"] == 3
    assert collector.last_run_metrics["persisted"] == 3


def test_ebay_collector_registered_in_registry():
    from collectors.base import CollectorRegistry, discover_collectors

    discover_collectors()
    cls = CollectorRegistry.get("ebay")
    assert cls is not None
    assert cls.__name__ == "EbayCollector"
