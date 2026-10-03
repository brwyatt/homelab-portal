"""Tests for Service Health Checking and JSONata evaluation."""
import pytest
import httpx
from app.config import PortalConfig, ServiceConfig, HealthCheckConfig
from app.services.health_service import HealthCheckService, ServiceStatus


@pytest.mark.asyncio
async def test_healthcheck_unknown_when_not_configured():
    service = ServiceConfig(
        name="No Health",
        url="https://example.com",
    )
    hs = HealthCheckService()
    status = await hs.get_service_status(service)
    assert status.status == "unknown"
    assert status.message == "No healthcheck configured"
    await hs.close()


@pytest.mark.asyncio
async def test_healthcheck_http_status_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="OK")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    hs = HealthCheckService(client=client)

    service = ServiceConfig(
        name="Test Service",
        url="https://test.local",
        healthcheck=HealthCheckConfig(expected_status=[200]),
    )

    status = await hs.get_service_status(service)
    assert status.status == "up"
    assert status.status_code == 200
    await hs.close()


@pytest.mark.asyncio
async def test_healthcheck_http_status_down():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    hs = HealthCheckService(client=client)

    service = ServiceConfig(
        name="Error Service",
        url="https://error.local",
        healthcheck=HealthCheckConfig(expected_status=[200]),
    )

    status = await hs.get_service_status(service)
    assert status.status == "down"
    assert status.status_code == 500
    await hs.close()


@pytest.mark.asyncio
async def test_healthcheck_text_match():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="pong")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    hs = HealthCheckService(client=client)

    service_pass = ServiceConfig(
        name="Ping",
        url="https://ping.local",
        healthcheck=HealthCheckConfig(text_match="pong"),
    )
    status_pass = await hs.get_service_status(service_pass)
    assert status_pass.status == "up"

    service_fail = ServiceConfig(
        name="Ping Fail",
        url="https://ping.local",
        healthcheck=HealthCheckConfig(text_match="expected_other"),
    )
    status_fail = await hs.get_service_status(service_fail)
    assert status_fail.status == "down"
    await hs.close()


@pytest.mark.asyncio
async def test_healthcheck_relative_path():
    requested_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requested_url
        requested_url = str(request.url)
        return httpx.Response(200, text="OK")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    hs = HealthCheckService(client=client)

    service = ServiceConfig(
        name="Relative Path Service",
        url="https://app.local/base",
        healthcheck=HealthCheckConfig(path="/status"),
    )
    status = await hs.get_service_status(service)
    assert status.status == "up"
    assert requested_url == "https://app.local/base/status"
    await hs.close()


@pytest.mark.asyncio
async def test_healthcheck_jsonata_expression():
    payload_ok = {
        "port_9000": {"status": "OK", "message": "Port 9000 on 127.0.0.1 is listening"},
        "service_thelounge": {"status": "OK", "message": "Service is active"},
    }
    payload_degraded = {
        "port_9000": {"status": "OK", "message": "Port 9000 on 127.0.0.1 is listening"},
        "service_thelounge": {"status": "DOWN", "message": "Service failed"},
    }

    current_payload = payload_ok

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        return httpx.Response(200, text=json.dumps(current_payload), headers={"content-type": "application/json"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    hs = HealthCheckService(client=client)

    query = '$.*.status and $count(*[status="OK"]) = $count(*)'
    service = ServiceConfig(
        name="The Lounge Check",
        url="https://thelounge.local",
        healthcheck=HealthCheckConfig(json_query=query, interval=1),
    )

    # Test passing condition
    status = await hs.get_service_status(service)
    assert status.status == "up"

    # Test degraded condition (clear cache first)
    hs._cache.clear()
    current_payload = payload_degraded
    status_degraded = await hs.get_service_status(service)
    assert status_degraded.status == "down"
    await hs.close()


@pytest.mark.asyncio
async def test_healthcheck_caching():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, text="OK")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    hs = HealthCheckService(client=client)

    service = ServiceConfig(
        name="Cache Check",
        url="https://cache.local",
        healthcheck=HealthCheckConfig(interval=15),
    )

    status1 = await hs.get_service_status(service)
    assert status1.status == "up"
    assert call_count == 1

    # Second check within interval must hit cache
    status2 = await hs.get_service_status(service)
    assert status2.status == "up"
    assert call_count == 1
    await hs.close()
