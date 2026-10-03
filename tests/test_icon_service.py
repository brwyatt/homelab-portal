import pytest
import httpx
from fastapi.testclient import TestClient

from app.config import PortalConfig, ServiceConfig
from app.main import app, icon_service, reload_configuration
from app.services.icon_service import IconService


def test_service_id_slug() -> None:
    svc1 = ServiceConfig(name="Home Assistant", url="https://ha.example.com", category="core")
    assert svc1.service_id == "home-assistant"

    svc2 = ServiceConfig(name="Z-Wave JS UI", url="https://zwave.example.com", category="core")
    assert svc2.service_id == "z-wave-js-ui"

    svc3 = ServiceConfig(name="!@#$% Special", url="https://special.example.com", category="core")
    assert svc3.service_id == "special"


def test_get_service_by_id() -> None:
    portal_cfg = PortalConfig(
        services=[
            ServiceConfig(name="PVE", url="https://pve.example.com", category="core"),
            ServiceConfig(name="PBS", url="https://pbs.example.com", category="core"),
        ]
    )
    assert portal_cfg.get_service_by_id("pve") is not None
    assert portal_cfg.get_service_by_id("pve").name == "PVE"
    assert portal_cfg.get_service_by_id("nonexistent") is None


def test_extract_icon_urls() -> None:
    svc = IconService()
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon-32x32.png">
        <link rel="apple-touch-icon" sizes="180x180" href="/assets/apple-touch-icon.png">
        <link rel="stylesheet" href="/style.css">
    </head>
    </html>
    """
    candidates = svc._extract_icon_urls(html, "https://service.example.com/subpath/")
    # apple-touch-icon prioritized
    assert candidates == [
        "https://service.example.com/assets/apple-touch-icon.png",
        "https://service.example.com/assets/favicon-32x32.png",
    ]


@pytest.mark.asyncio
async def test_cross_domain_redirect_blocked() -> None:
    svc = IconService()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url == "https://app.example.com/":
            return httpx.Response(302, headers={"Location": "https://auth.example.com/login"})
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        resp, final_url = await svc._safe_fetch(client, "https://app.example.com/", max_redirects=2)
        assert resp is None


@pytest.mark.asyncio
async def test_same_domain_redirect_allowed() -> None:
    svc = IconService()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url == "https://app.example.com/":
            return httpx.Response(302, headers={"Location": "/web/index.html"})
        if request.url == "https://app.example.com/web/index.html":
            return httpx.Response(200, text="<html>Dashboard</html>")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        resp, final_url = await svc._safe_fetch(client, "https://app.example.com/", max_redirects=2)
        assert resp is not None
        assert resp.status_code == 200
        assert final_url == "https://app.example.com/web/index.html"


@pytest.mark.asyncio
async def test_fallback_to_root_favicon_svg() -> None:
    svg_content = b"<svg xmlns='http://www.w3.org/2000/svg'><circle r='10'/></svg>"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url == "https://app.example.com/":
            return httpx.Response(200, text="<html><body>Hello</body></html>")
        if request.url == "https://app.example.com/favicon.svg":
            return httpx.Response(200, content=svg_content, headers={"Content-Type": "image/svg+xml"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    svc = IconService()
    svc._get_client = lambda: httpx.AsyncClient(transport=transport)

    service = ServiceConfig(name="MyApp SVG", url="https://app.example.com", category="core")
    icon = await svc.get_icon(service)

    assert icon is not None
    assert icon.content == svg_content
    assert icon.media_type == "image/svg+xml"


@pytest.mark.asyncio
async def test_fallback_prefers_svg_over_ico() -> None:
    svg_content = b"<svg xmlns='http://www.w3.org/2000/svg'><circle r='10'/></svg>"
    ico_content = b"\x00\x00\x01\x00\x01\x00\x10\x10"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url == "https://app.example.com/":
            return httpx.Response(200, text="<html><body>Hello</body></html>")
        if request.url == "https://app.example.com/favicon.svg":
            return httpx.Response(200, content=svg_content, headers={"Content-Type": "image/svg+xml"})
        if request.url == "https://app.example.com/favicon.ico":
            return httpx.Response(200, content=ico_content, headers={"Content-Type": "image/x-icon"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    svc = IconService()
    svc._get_client = lambda: httpx.AsyncClient(transport=transport)

    service = ServiceConfig(name="MyApp Multi", url="https://app.example.com", category="core")
    icon = await svc.get_icon(service)

    assert icon is not None
    assert icon.content == svg_content
    assert icon.media_type == "image/svg+xml"


@pytest.mark.asyncio
async def test_fallback_to_root_favicon() -> None:
    # 1x1 transparent PNG bytes
    png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url == "https://app.example.com/":
            # No <link> icons in HTML
            return httpx.Response(200, text="<html><body>Hello</body></html>")
        if request.url == "https://app.example.com/favicon.ico":
            return httpx.Response(200, content=png_data, headers={"Content-Type": "image/png"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    svc = IconService()
    # Monkeypatch _get_client
    svc._get_client = lambda: httpx.AsyncClient(transport=transport)

    service = ServiceConfig(name="MyApp", url="https://app.example.com", category="core")
    icon = await svc.get_icon(service)

    assert icon is not None
    assert icon.content == png_data
    assert icon.media_type == "image/png"


@pytest.mark.asyncio
async def test_negative_cache() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    svc = IconService(negative_ttl=60.0)
    svc._get_client = lambda: httpx.AsyncClient(transport=transport)

    service = ServiceConfig(name="MyApp", url="https://app.example.com", category="core")
    res1 = await svc.get_icon(service)
    assert res1 is None
    first_call_count = call_count

    # Second call should hit negative cache and not make any more network requests
    res2 = await svc.get_icon(service)
    assert res2 is None
    assert call_count == first_call_count


def test_route_get_service_icon(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    # 404 for unknown service
    resp = client.get("/api/services/nonexistent-service/icon")
    assert resp.status_code == 404
