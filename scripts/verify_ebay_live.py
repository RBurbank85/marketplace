"""Live smoke test for the eBay Browse API collector.

Loads credentials from the local .env (via the project Settings), mints an
application access token using the client_credentials grant, and runs a single
real search. Prints token status and the first few item summaries.

Usage:
    uv run python scripts/verify_ebay_live.py

This makes REAL network calls to api.ebay.com. Run it only after you have
placed your real App ID / Cert ID in .env under
COLLECTOR_CONFIGS -> ebay -> credentials.
"""

from __future__ import annotations

import asyncio
import sys

from config.settings import settings
from collectors.ebay import (
    DEFAULT_BASE_URL,
    EbayAuthError,
    EbayCollector,
)


async def main() -> int:
    config = settings.collector_configs.get("ebay")
    if config is None:
        print("ERROR: no 'ebay' entry found in COLLECTOR_CONFIGS (.env).")
        return 2

    creds = {
        name: value.get_secret_value() for name, value in config.credentials.items()
    }
    client_id = creds.get("client_id", "")
    client_secret = creds.get("client_secret", "")

    if not client_id or client_id.startswith("YOUR_EBAY_"):
        print("ERROR: eBay client_id is still a placeholder in .env.")
        print("       Replace YOUR_EBAY_APP_ID with your real eBay App ID.")
        return 2
    if not client_secret or client_secret.startswith("YOUR_EBAY_"):
        print("ERROR: eBay client_secret is still a placeholder in .env.")
        print("       Replace YOUR_EBAY_CERT_ID with your real eBay Cert ID.")
        return 2

    print(f"Loaded eBay config: {len(config.queries)} queries, "
          f"pagination_limit={config.pagination_limit}, "
          f"rate_limit_per_minute={config.rate_limit_per_minute}")
    print(f"base_url: {config.base_url or DEFAULT_BASE_URL}")
    print(f"client_id: {client_id[:6]}...{client_id[-4:]} "
          f"(len={len(client_id)})")

    collector = EbayCollector(
        base_url=config.base_url or DEFAULT_BASE_URL,
        request_delay=0.5,
        page_limit=50,
    )

    query = config.queries[0] if config.queries else "guitar"
    print(f"\nRequesting access token from {collector.token_url} ...")

    try:
        token = await collector._get_access_token({"credentials": creds})
    except EbayAuthError as exc:
        print(f"\nFAILED to obtain access token:\n  {exc}")
        return 1

    print(f"Token acquired: {token[:12]}...{token[-4:]} (len={len(token)})")
    print(f"\nRunning live search for '{query}' via Browse API ...")

    try:
        result = await collector.search(
            query,
            credentials=creds,
            pagination_limit=1,
            page_limit=10,
            request_timeout=config.request_timeout,
            rate_limit_per_minute=config.rate_limit_per_minute,
        )
    except Exception as exc:
        print(f"\nFAILED during search:\n  {exc}")
        return 1
    finally:
        await collector.close()

    items = result.get("itemSummaries", [])
    total = result.get("total")
    print(f"\nSuccess. eBay reported total={total}, returned {len(items)} items:")
    for i, item in enumerate(items[:5], 1):
        price = item.get("price", {})
        price_str = f"{price.get('value', '?')} {price.get('currency', '')}" if isinstance(price, dict) else str(price)
        print(f"  {i}. {item.get('title', '?')[:60]}  -  {price_str}")

    print(f"\nRequest metrics: {collector.request_metrics}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
