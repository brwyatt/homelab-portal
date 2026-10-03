"""Disk-backed caching and asset fetching with stale-while-revalidate strategy."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import time
from typing import NamedTuple, final

import httpx

logger = logging.getLogger(__name__)


def get_default_cache_dir() -> Path:
    """Determine default persistent cache directory."""
    env_dir = os.getenv("PORTAL_CACHE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parent.parent / ".cache"


@final
class DiskCache:
    """Atomic, namespace-isolated filesystem cache for static assets and favicons."""

    cache_dir: Path

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir if cache_dir is not None else get_default_cache_dir()

    def _safe_key(self, key: str) -> str:
        """Sanitize cache key to prevent directory traversal and invalid path characters."""
        if re.match(r"^[a-zA-Z0-9_\.-]+$", key) and ".." not in key:
            return key
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _paths(self, namespace: str, key: str) -> tuple[Path, Path]:
        ns_dir = self.cache_dir / namespace
        ns_dir.mkdir(parents=True, exist_ok=True)
        safe = self._safe_key(key)
        return ns_dir / f"{safe}.bin", ns_dir / f"{safe}.meta.json"

    def get(self, namespace: str, key: str) -> tuple[bytes, dict[str, object]] | None:
        """Read data and metadata from disk cache if both exist and are valid."""
        bin_path, meta_path = self._paths(namespace, key)
        if not (bin_path.is_file() and meta_path.is_file()):
            return None

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_raw: object = json.load(f)
            if not isinstance(meta_raw, dict):
                return None
            meta: dict[str, object] = {str(k): v for k, v in meta_raw.items()}
            with open(bin_path, "rb") as f:
                data = f.read()
            return data, meta
        except Exception as e:
            logger.debug(f"Failed to read disk cache for {namespace}/{key}: {e}")
            return None

    def put(
        self,
        namespace: str,
        key: str,
        data: bytes,
        content_type: str,
        etag: str,
        ttl: float,
        extra: dict[str, object] | None = None,
    ) -> None:
        """Write data and metadata atomically to disk cache."""
        bin_path, meta_path = self._paths(namespace, key)
        target_dir = bin_path.parent

        now = time.time()
        meta: dict[str, object] = {
            "content_type": content_type,
            "etag": etag,
            "expires_at": now + ttl,
            "cached_at": now,
        }
        if extra:
            meta.update(extra)

        try:
            # Write binary data atomically
            with tempfile.NamedTemporaryFile(dir=target_dir, delete=False) as f:
                _ = f.write(data)
                tmp_bin = f.name
            os.replace(tmp_bin, bin_path)

            # Write metadata atomically
            with tempfile.NamedTemporaryFile(dir=target_dir, delete=False, mode="w", encoding="utf-8") as f:
                json.dump(meta, f)
                tmp_meta = f.name
            os.replace(tmp_meta, meta_path)
        except Exception as e:
            logger.warning(f"Failed to write disk cache for {namespace}/{key}: {e}")

    def touch(self, namespace: str, key: str, ttl: float) -> bool:
        """Extend the TTL for an existing cached item (stale grace extension)."""
        _, meta_path = self._paths(namespace, key)
        if not meta_path.is_file():
            return False

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta_raw: object = json.load(f)
            if not isinstance(meta_raw, dict):
                return False
            meta: dict[str, object] = {str(k): v for k, v in meta_raw.items()}
            meta["expires_at"] = time.time() + ttl
            target_dir = meta_path.parent
            with tempfile.NamedTemporaryFile(dir=target_dir, delete=False, mode="w", encoding="utf-8") as f:
                json.dump(meta, f)
                tmp_meta = f.name
            os.replace(tmp_meta, meta_path)
            return True
        except Exception as e:
            logger.warning(f"Failed to touch disk cache for {namespace}/{key}: {e}")
            return False

    def clear(self, namespace: str | None = None) -> None:
        """Clear cache for a specific namespace or all namespaces."""
        target_dir = self.cache_dir / namespace if namespace else self.cache_dir
        if not target_dir.exists():
            return

        for p in target_dir.glob("**/*"):
            if p.is_file():
                try:
                    p.unlink(missing_ok=True)
                except Exception as e:
                    logger.debug(f"Failed to delete {p}: {e}")


class CachedAsset(NamedTuple):
    content: bytes
    content_type: str
    etag: str


@final
class AssetCacheService:
    """Fetches and caches upstream assets with a stale-while-revalidate strategy."""

    FEATHER_JS_URL: str = "https://cdn.jsdelivr.net/npm/feather-icons/dist/feather.min.js"
    FEATHER_SVG_URL_PREFIX: str = "https://cdn.jsdelivr.net/npm/feather-icons/dist/icons"

    disk_cache: DiskCache
    timeout: float
    default_ttl: float
    stale_retry_ttl: float
    ca_bundle: str | bool

    def __init__(
        self,
        disk_cache: DiskCache | None = None,
        timeout: float = 4.0,
        default_ttl: float = 86400 * 7,  # 7 days
        stale_retry_ttl: float = 3600.0,  # 1 hour grace if upstream fails
        ca_bundle: str | bool | None = None,
    ) -> None:
        self.disk_cache = disk_cache if disk_cache is not None else DiskCache()
        self.timeout = timeout
        self.default_ttl = default_ttl
        self.stale_retry_ttl = stale_retry_ttl

        if ca_bundle is None and os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
            self.ca_bundle = "/etc/ssl/certs/ca-certificates.crt"
        else:
            self.ca_bundle = ca_bundle if ca_bundle is not None else True

    def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            verify=self.ca_bundle,
            timeout=self.timeout,
            headers={"User-Agent": "HomelabPortal/1.0 (AssetCache)"},
        )

    async def _fetch_upstream(
        self, url: str, etag: str | None = None
    ) -> tuple[int, bytes | None, str | None, str | None]:
        """Fetch asset upstream with optional ETag conditional request."""
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = f'"{etag.strip(chr(34))}"'

        try:
            async with self._get_client() as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 304:
                    return 304, None, None, etag

                if resp.status_code == 200:
                    raw_etag = resp.headers.get("etag", "").strip('"')
                    if not raw_etag:
                        raw_etag = hashlib.md5(resp.content).hexdigest()
                    content_type = resp.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
                    return 200, resp.content, content_type, raw_etag

                logger.debug(f"Upstream fetch failed for {url} with status {resp.status_code}")
                return resp.status_code, None, None, None
        except Exception as e:
            logger.debug(f"Exception during upstream fetch of {url}: {e}")
            return 0, None, None, None

    async def get_asset(
        self,
        namespace: str,
        key: str,
        url: str,
        default_content_type: str = "application/octet-stream",
        ttl: float | None = None,
    ) -> CachedAsset | None:
        """Retrieve an asset using stale-while-revalidate."""
        effective_ttl = ttl if ttl is not None else self.default_ttl
        cached = self.disk_cache.get(namespace, key)

        if cached is not None:
            data, meta = cached
            raw_exp = meta.get("expires_at", 0)
            expires_at = float(raw_exp) if isinstance(raw_exp, (int, float)) else 0.0
            raw_etag = meta.get("etag")
            cached_etag = str(raw_etag) if raw_etag is not None else hashlib.md5(data).hexdigest()
            raw_type = meta.get("content_type")
            content_type = str(raw_type) if raw_type is not None else default_content_type

            # If still fresh, return immediately
            if time.time() < expires_at:
                return CachedAsset(content=data, content_type=content_type, etag=cached_etag)

            # Stale: revalidate upstream
            status, new_data, new_type, new_etag = await self._fetch_upstream(url, etag=cached_etag)
            if status == 304:
                # Upstream not modified: touch cache and serve existing
                _ = self.disk_cache.touch(namespace, key, effective_ttl)
                return CachedAsset(content=data, content_type=content_type, etag=cached_etag)
            elif status == 200 and new_data is not None and new_etag is not None:
                final_type = new_type or default_content_type
                self.disk_cache.put(namespace, key, new_data, final_type, new_etag, effective_ttl, {"url": url})
                return CachedAsset(content=new_data, content_type=final_type, etag=new_etag)
            else:
                # Network error, timeout, 5xx, or offline:
                # Reset TTL to grace period and serve stale from disk
                logger.info(f"Upstream revalidation failed for {url}; serving stale disk cache")
                _ = self.disk_cache.touch(namespace, key, self.stale_retry_ttl)
                return CachedAsset(content=data, content_type=content_type, etag=cached_etag)

        # Cold start: not on disk, fetch from upstream
        status, new_data, new_type, new_etag = await self._fetch_upstream(url)
        if status == 200 and new_data is not None and new_etag is not None:
            final_type = new_type or default_content_type
            self.disk_cache.put(namespace, key, new_data, final_type, new_etag, effective_ttl, {"url": url})
            return CachedAsset(content=new_data, content_type=final_type, etag=new_etag)

        return None

    async def get_feather_js(self) -> CachedAsset | None:
        """Retrieve Feather icons JavaScript bundle."""
        return await self.get_asset(
            namespace="vendor",
            key="feather.min.js",
            url=self.FEATHER_JS_URL,
            default_content_type="application/javascript",
        )

    async def get_feather_icon(self, icon_name: str) -> CachedAsset | None:
        """Retrieve a specific Feather icon SVG."""
        from app.icons import normalize_icon_name

        normalized = normalize_icon_name(icon_name)
        if not normalized:
            return None

        url = f"{self.FEATHER_SVG_URL_PREFIX}/{normalized}.svg"
        return await self.get_asset(
            namespace="feather_svg",
            key=f"{normalized}.svg",
            url=url,
            default_content_type="image/svg+xml",
        )
