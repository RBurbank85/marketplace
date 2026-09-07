from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_direct_marketplace_http_is_blocked_in_tests() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(AssertionError, match="marketplace HTTP access"):
            await client.get("https://www.craigslist.org/search/sss?query=guitar")


@pytest.mark.asyncio
async def test_mock_transport_can_supply_marketplace_fixture() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text="fixture", request=request)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://www.craigslist.org/search/sss")

    assert response.text == "fixture"