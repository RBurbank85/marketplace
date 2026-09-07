from __future__ import annotations

import pytest
import httpx


@pytest.fixture(autouse=True)
def block_live_marketplace_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent tests from making live collector requests by default."""
    from core.networking import NetworkClient

    marketplace_hosts = (
        "craigslist.org",
        "facebook.com",
        "fb.com",
        "ebay.com",
        "offerup.com",
        "mercari.com",
        "reverb.com",
    )

    def is_marketplace_url(url: object) -> bool:
        host = httpx.URL(url).host.lower()
        return any(host == domain or host.endswith(f".{domain}") for domain in marketplace_hosts)

    async def blocked_request(*args, **kwargs):
        raise AssertionError(
            "Live network access is disabled in tests; use a fixture or mocked transport."
        )

    monkeypatch.setattr(NetworkClient, "request", blocked_request)

    original_async_request = httpx.AsyncClient.request

    async def guarded_async_request(self, method, url, *args, **kwargs):
        if is_marketplace_url(url) and not isinstance(self._transport, httpx.MockTransport):
            raise AssertionError(
                "Direct marketplace HTTP access is disabled in tests; use MockTransport."
            )
        return await original_async_request(self, method, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "request", guarded_async_request)

    original_sync_request = httpx.Client.request

    def guarded_sync_request(self, method, url, *args, **kwargs):
        if is_marketplace_url(url) and not isinstance(self._transport, httpx.MockTransport):
            raise AssertionError(
                "Direct marketplace HTTP access is disabled in tests; use MockTransport."
            )
        return original_sync_request(self, method, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "request", guarded_sync_request)
