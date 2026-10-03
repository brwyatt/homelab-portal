"""Unit tests for disk cache and stale-while-revalidate asset cache service."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.cache import AssetCacheService, DiskCache


def test_disk_cache_basic(tmp_path: Path) -> None:
    cache = DiskCache(cache_dir=tmp_path)
    assert cache.get("vendor", "test.js") is None

    # Put item
    cache.put(
        namespace="vendor",
        key="test.js",
        data=b"console.log('hello');",
        content_type="application/javascript",
        etag="etag-123",
        ttl=3600.0,
    )

    item = cache.get("vendor", "test.js")
    assert item is not None
    data, meta = item
    assert data == b"console.log('hello');"
    assert meta["content_type"] == "application/javascript"
    assert meta["etag"] == "etag-123"
    assert abs((meta["expires_at"] - meta["cached_at"]) - 3600.0) < 0.1

    # Safe key handling
    unsafe_key = "https://example.com/icons/../foo/bar?baz=1"
    cache.put(
        namespace="icons",
        key=unsafe_key,
        data=b"<svg></svg>",
        content_type="image/svg+xml",
        etag="etag-svg",
        ttl=60.0,
    )
    item_svg = cache.get("icons", unsafe_key)
    assert item_svg is not None
    assert item_svg[0] == b"<svg></svg>"

    # Clear
    cache.clear("icons")
    assert cache.get("icons", unsafe_key) is None
    assert cache.get("vendor", "test.js") is not None

    cache.clear()
    assert cache.get("vendor", "test.js") is None


@pytest.mark.asyncio
async def test_asset_cache_service_cold_start_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    disk_cache = DiskCache(cache_dir=tmp_path)
    service = AssetCacheService(disk_cache=disk_cache)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"var feather = {};"
    mock_resp.headers = {"content-type": "application/javascript", "etag": '"v1.0"'}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(return_value=mock_resp)
    monkeypatch.setattr(service, "_get_client", lambda: mock_client)

    asset = await service.get_feather_js()
    assert asset is not None
    assert asset.content == b"var feather = {};"
    assert asset.etag == "v1.0"

    # Disk cache should now have it
    disk_item = disk_cache.get("vendor", "feather.min.js")
    assert disk_item is not None
    assert disk_item[0] == b"var feather = {};"


@pytest.mark.asyncio
async def test_asset_cache_service_fresh_hit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    disk_cache = DiskCache(cache_dir=tmp_path)
    service = AssetCacheService(disk_cache=disk_cache)

    # Seed fresh cache
    disk_cache.put("vendor", "feather.min.js", b"cached_js", "application/javascript", "etag1", ttl=3600.0)

    # _get_client should not be called
    mock_client = AsyncMock()
    monkeypatch.setattr(service, "_get_client", lambda: mock_client)

    asset = await service.get_feather_js()
    assert asset is not None
    assert asset.content == b"cached_js"
    assert mock_client.get.call_count == 0


@pytest.mark.asyncio
async def test_asset_cache_service_stale_revalidate_upstream_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    disk_cache = DiskCache(cache_dir=tmp_path)
    service = AssetCacheService(disk_cache=disk_cache, stale_retry_ttl=1800.0)

    # Seed cache with expired asset
    disk_cache.put("vendor", "test.js", b"v1", "application/javascript", "etag1", ttl=-10.0)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    monkeypatch.setattr(service, "_get_client", lambda: mock_client)

    # Stale-while-revalidate: upstream fails, so it serves stale from disk and resets TTL!
    res = await service.get_asset(
        url="https://cdn.example.com/test.js",
        namespace="vendor",
        key="test.js",
        default_content_type="application/javascript",
    )
    assert res is not None
    assert res.content == b"v1"

    # Verify TTL was extended
    _, meta = disk_cache.get("vendor", "test.js") or (None, {})
    assert meta["expires_at"] > time.time()


@pytest.mark.asyncio
async def test_asset_cache_service_stale_revalidate_304(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    disk_cache = DiskCache(cache_dir=tmp_path)
    service = AssetCacheService(disk_cache=disk_cache)

    disk_cache.put("vendor", "test.js", b"v1", "application/javascript", "etag1", ttl=-10.0)

    mock_resp = MagicMock()
    mock_resp.status_code = 304

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    monkeypatch.setattr(service, "_get_client", lambda: mock_client)

    res = await service.get_asset(
        url="https://cdn.example.com/test.js",
        namespace="vendor",
        key="test.js",
        default_content_type="application/javascript",
    )
    assert res is not None
    assert res.content == b"v1"
    _, meta = disk_cache.get("vendor", "test.js") or (None, {})
    assert meta["expires_at"] > time.time()


@pytest.mark.asyncio
async def test_asset_cache_service_cold_start_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    disk_cache = DiskCache(cache_dir=tmp_path)
    service = AssetCacheService(disk_cache=disk_cache)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Offline"))
    monkeypatch.setattr(service, "_get_client", lambda: mock_client)

    res = await service.get_asset(
        url="https://cdn.example.com/test.js",
        namespace="vendor",
        key="test.js",
    )
    assert res is None
