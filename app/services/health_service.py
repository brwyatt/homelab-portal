"""Service health check manager with JSONata evaluation and async caching."""
from __future__ import annotations

import asyncio
import time
from typing import Any, final
import httpx
import jsonata  # type: ignore[import-untyped,import-not-found]
from pydantic import BaseModel

from app.config import ServiceConfig


class ServiceStatus(BaseModel):
    status: str  # "up", "down", "unknown"
    status_code: int | None = None
    message: str | None = None
    checked_at: float | None = None


@final
class HealthCheckService:
    _client: httpx.AsyncClient | None
    _cache: dict[str, ServiceStatus]
    _locks: dict[str, asyncio.Lock]
    _compiled_queries: dict[str, object]

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._cache = {}
        self._locks = {}
        self._compiled_queries = {}

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                verify=False,  # Allow self-signed internal homelab certs
                follow_redirects=True,
                headers={"User-Agent": "Homelab-Portal-Healthcheck/1.0"},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _get_lock(self, service_id: str) -> asyncio.Lock:
        if service_id not in self._locks:
            self._locks[service_id] = asyncio.Lock()
        return self._locks[service_id]

    async def get_service_status(self, service: ServiceConfig) -> ServiceStatus:
        hc = service.healthcheck
        if hc is None:
            return ServiceStatus(status="unknown", message="No healthcheck configured")

        service_id = service.service_id
        now = time.time()

        # Check existing cache
        cached = self._cache.get(service_id)
        if cached and cached.checked_at is not None:
            if (now - cached.checked_at) < max(hc.interval, 1):
                return cached

        # Request coalescing with per-service lock
        lock = self._get_lock(service_id)
        async with lock:
            # Re-check cache after acquiring lock
            cached = self._cache.get(service_id)
            if cached and cached.checked_at is not None:
                if (time.time() - cached.checked_at) < max(hc.interval, 1):
                    return cached

            status = await self._check_health(service)
            self._cache[service_id] = status
            return status

    async def _check_health(self, service: ServiceConfig) -> ServiceStatus:
        hc = service.healthcheck
        if hc is None:
            return ServiceStatus(status="unknown", message="No healthcheck configured")

        target_url = hc.url or service.url
        now = time.time()
        client = self._get_client()

        try:
            req_headers = {"Accept": "*/*"}
            if hc.headers:
                req_headers.update(hc.headers)

            response = await client.request(
                method=hc.method.upper(),
                url=target_url,
                headers=req_headers,
                timeout=hc.timeout,
            )

            # Check HTTP Status Code
            if response.status_code not in hc.expected_status:
                return ServiceStatus(
                    status="down",
                    status_code=response.status_code,
                    message=f"HTTP status {response.status_code} not in expected {hc.expected_status}",
                    checked_at=now,
                )

            # Check text_match if defined
            if hc.text_match is not None:
                if hc.text_match not in response.text:
                    return ServiceStatus(
                        status="down",
                        status_code=response.status_code,
                        message=f"Response text does not contain expected substring: {hc.text_match!r}",
                        checked_at=now,
                    )

            # Check json_query (JSONata) if defined
            if hc.json_query is not None:
                try:
                    data = response.json()
                except Exception as json_err:
                    return ServiceStatus(
                        status="down",
                        status_code=response.status_code,
                        message=f"Failed to parse response as JSON: {json_err}",
                        checked_at=now,
                    )

                try:
                    expr = self._compiled_queries.get(hc.json_query)
                    if expr is None:
                        expr = jsonata.Jsonata(hc.json_query)
                        self._compiled_queries[hc.json_query] = expr

                    result = expr.evaluate(data)
                    # Truthy evaluation in Python:
                    # True, non-empty, non-zero
                    if not result:
                        return ServiceStatus(
                            status="down",
                            status_code=response.status_code,
                            message=f"JSONata query '{hc.json_query}' evaluated to false: {result!r}",
                            checked_at=now,
                        )
                except Exception as query_err:
                    return ServiceStatus(
                        status="down",
                        status_code=response.status_code,
                        message=f"Error evaluating JSONata query '{hc.json_query}': {query_err}",
                        checked_at=now,
                    )

            return ServiceStatus(
                status="up",
                status_code=response.status_code,
                message="Health check passed",
                checked_at=now,
            )

        except httpx.TimeoutException:
            return ServiceStatus(
                status="down",
                status_code=None,
                message=f"Health check timed out after {hc.timeout}s",
                checked_at=now,
            )
        except httpx.RequestError as exc:
            return ServiceStatus(
                status="down",
                status_code=None,
                message=f"Connection error: {exc}",
                checked_at=now,
            )
        except Exception as exc:
            return ServiceStatus(
                status="down",
                status_code=None,
                message=f"Unexpected health check error: {exc}",
                checked_at=now,
            )


# Global singleton instance
health_service = HealthCheckService()
