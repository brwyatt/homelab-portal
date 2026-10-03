"""Tests for Feather icon utilities and endpoints."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

from app.cache import AssetCacheService, DiskCache
from app.icons import normalize_icon_name
from app.main import app, asset_cache_service


def test_normalize_icon_name() -> None:
    assert normalize_icon_name("server") == "server"
    assert normalize_icon_name("feather:server") == "server"
    assert normalize_icon_name("feather-server") == "server"
    assert normalize_icon_name("lucide:server") == "server"
    assert normalize_icon_name("server.svg") == "server"
    assert normalize_icon_name("hard_drive") == "hard-drive"
    assert normalize_icon_name("house") == "home"  # Alias
    assert normalize_icon_name("network") == "share-2"  # Alias
    assert normalize_icon_name("security") == "shield"  # Alias
    assert normalize_icon_name("dns") == "globe"  # Alias
    assert normalize_icon_name("") == ""
    assert normalize_icon_name(None) == ""


def test_vendor_feather_js_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test_disk_cache = DiskCache(cache_dir=tmp_path)
    test_asset_service = AssetCacheService(disk_cache=test_disk_cache)
    test_disk_cache.put("vendor", "feather.min.js", b"console.log('feather');", "application/javascript", "etag-js", 3600.0)

    monkeypatch.setattr(asset_cache_service, "disk_cache", test_disk_cache)
    monkeypatch.setattr(asset_cache_service, "get_feather_js", test_asset_service.get_feather_js)

    client = TestClient(app)
    resp = client.get("/static/vendor/feather.min.js")
    assert resp.status_code == 200
    assert resp.content == b"console.log('feather');"
    assert "application/javascript" in resp.headers["content-type"]
    assert resp.headers["etag"] == '"etag-js"'

    # Conditional 304
    resp304 = client.get("/static/vendor/feather.min.js", headers={"If-None-Match": '"etag-js"'})
    assert resp304.status_code == 304


def test_api_icons_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test_disk_cache = DiskCache(cache_dir=tmp_path)
    test_asset_service = AssetCacheService(disk_cache=test_disk_cache)
    svg_data = b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path d="M1 1"/></svg>'
    test_disk_cache.put("feather_svg", "home.svg", svg_data, "image/svg+xml", "etag-home", 3600.0)

    monkeypatch.setattr(asset_cache_service, "disk_cache", test_disk_cache)
    monkeypatch.setattr(asset_cache_service, "get_feather_icon", test_asset_service.get_feather_icon)

    client = TestClient(app)
    # Using alias "house"
    resp = client.get("/api/icons/house")
    assert resp.status_code == 200
    assert resp.content == svg_data
    assert resp.headers["content-type"] == "image/svg+xml"
    assert resp.headers["etag"] == '"etag-home"'

    # 304 Not Modified
    resp304 = client.get("/api/icons/house", headers={"If-None-Match": '"etag-home"'})
    assert resp304.status_code == 304
