from __future__ import annotations

import asyncio
from typing import Any, Mapping, Optional

import httpx
from loguru import logger

from config.settings import settings
from core.identity import identity_service


class NetworkClient:
    """
    Shared asynchronous network client with retry logic and connection pooling.

    This class wraps httpx.AsyncClient to provide a centralized way of making
    network requests with consistent timeouts, retries, and logging.
    """

    def __init__(
        self,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
        proxy: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.timeout = (
            timeout if timeout is not None else float(settings.network_timeout)
        )
        self.max_retries = (
            max_retries if max_retries is not None else settings.network_max_retries
        )
        self.backoff_factor = (
            backoff_factor
            if backoff_factor is not None
            else settings.network_retry_backoff
        )
        self.proxy = proxy or settings.network_proxy

        default_headers = {"User-Agent": settings.network_user_agent}
        if headers:
            default_headers.update(headers)
        self.headers = default_headers

        self._client: Optional[httpx.AsyncClient] = None
        self._logger = logger.bind(component="network_client")

    async def get_client(self) -> httpx.AsyncClient:
        """
        Get or create the shared AsyncClient instance.

        Returns:
            An initialized httpx.AsyncClient.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                proxy=self.proxy,
                headers=self.headers,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """
        Close the shared AsyncClient instance gracefully.
        """
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            self._logger.debug("network_client_closed")

    async def request(
        self,
        method: str,
        url: str,
        collector_name: Optional[str] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Execute an HTTP request with exponential backoff retries.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Target URL
            collector_name: Optional name of the collector making the request for identity management.
            **kwargs: Additional arguments passed to httpx.request

        Returns:
            httpx.Response object
        """
        if collector_name:
            if not await identity_service.is_allowed(url, collector_name):
                raise RuntimeError(
                    f"Request disallowed by robots.txt for {url} (collector: {collector_name})"
                )

            identity = identity_service.generate_identity(collector_name)

            # Merge headers: identity < existing_kwargs
            request_headers = identity.headers.copy()
            if "headers" in kwargs:
                request_headers.update(kwargs.pop("headers"))
            kwargs["headers"] = request_headers

            # Randomized delay
            if identity.delay > 0:
                self._logger.debug(
                    "identity_delay", delay=identity.delay, collector=collector_name
                )
                await asyncio.sleep(identity.delay)

        client = await self.get_client()
        last_exception: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                self._logger.debug(
                    "request_started", method=method, url=url, attempt=attempt + 1
                )
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_exception = exc
                status_code = (
                    exc.response.status_code
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response
                    else None
                )
                retryable = (
                    status_code is None
                    or status_code in {408, 425, 429}
                    or status_code >= 500
                )
                self._logger.warning(
                    "request_failed",
                    method=method,
                    url=url,
                    attempt=attempt + 1,
                    error=str(exc),
                )

                if attempt < self.max_retries and retryable:
                    sleep_time = self.backoff_factor * (2**attempt)
                    self._logger.info(
                        "retry_scheduled", delay=sleep_time, attempt=attempt + 1
                    )
                    await asyncio.sleep(sleep_time)
                else:
                    self._logger.error(
                        "request_exhausted",
                        method=method,
                        url=url,
                        attempts=attempt + 1,
                        error=str(exc),
                    )
                    if not retryable:
                        break

        if last_exception:
            raise last_exception
        raise RuntimeError(f"Failed to execute {method} request to {url}")

    async def get(
        self, url: str, collector_name: Optional[str] = None, **kwargs: Any
    ) -> httpx.Response:
        """Execute a GET request."""
        return await self.request("GET", url, collector_name=collector_name, **kwargs)

    async def post(
        self, url: str, collector_name: Optional[str] = None, **kwargs: Any
    ) -> httpx.Response:
        """Execute a POST request."""
        return await self.request("POST", url, collector_name=collector_name, **kwargs)


# Global shared instance
network_client = NetworkClient()
