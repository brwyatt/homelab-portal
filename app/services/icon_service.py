import hashlib
import os
import re
import time
import urllib.parse
from typing import NamedTuple

import httpx

from app.cache import AssetCacheService
from app.config import ServiceConfig


class CachedIcon(NamedTuple):
    content: bytes
    media_type: str
    etag: str
    expires_at: float


class IconService:
    cache_ttl: float
    negative_ttl: float
    timeout: float
    asset_cache: AssetCacheService

    def __init__(
        self,
        cache_ttl: float = 86400.0,
        negative_ttl: float = 300.0,
        timeout: float = 3.0,
        ca_bundle: str | None = None,
        asset_cache: AssetCacheService | None = None,
    ) -> None:
        self.cache_ttl = cache_ttl
        self.negative_ttl = negative_ttl
        self.timeout = timeout
        self.asset_cache = asset_cache if asset_cache is not None else AssetCacheService()
        if ca_bundle is None and os.path.exists("/etc/ssl/certs/ca-certificates.crt"):
            self.ca_bundle: str | bool = "/etc/ssl/certs/ca-certificates.crt"
        else:
            self.ca_bundle = ca_bundle if ca_bundle is not None else True

        self._cache: dict[str, CachedIcon] = {}
        self._negative_cache: dict[str, float] = {}

    def clear_cache(self) -> None:
        """Clear in-memory and negative cache."""
        self._cache.clear()
        self._negative_cache.clear()

    def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            verify=self.ca_bundle,
            timeout=self.timeout,
            headers={"User-Agent": "HomelabPortal/1.0 (FaviconFetcher)"},
        )

    async def _safe_fetch(
        self, client: httpx.AsyncClient, url: str, max_redirects: int = 3
    ) -> tuple[httpx.Response | None, str]:
        """Fetch URL following only same-domain redirects."""
        orig_netloc = urllib.parse.urlparse(url).netloc
        curr_url = url

        for _ in range(max_redirects + 1):
            try:
                resp = await client.get(curr_url, follow_redirects=False)
            except Exception:
                return None, curr_url

            if resp.is_redirect and "location" in resp.headers:
                loc = resp.headers["location"]
                target = urllib.parse.urljoin(curr_url, loc)
                target_parsed = urllib.parse.urlparse(target)

                # Block cross-domain redirects (e.g., Authelia or external login portals)
                if target_parsed.netloc != orig_netloc:
                    return None, curr_url

                curr_url = target
            else:
                return resp, curr_url

        return None, curr_url

    def _extract_icon_urls(self, html: str, base_url: str) -> list[str]:
        link_tags = re.findall(r"<link\b[^>]*>", html, re.IGNORECASE)
        apple_icons: list[str] = []
        standard_icons: list[str] = []

        for tag in link_tags:
            rel_match = re.search(r"""\brel=(?:["']([^"']+)["']|([^\s>]+))""", tag, re.IGNORECASE)
            href_match = re.search(r"""\bhref=(?:["']([^"']+)["']|([^\s>]+))""", tag, re.IGNORECASE)
            if not rel_match or not href_match:
                continue

            rel_str = rel_match.group(1) or rel_match.group(2) or ""
            href = href_match.group(1) or href_match.group(2) or ""
            if not href:
                continue

            rel_tokens = rel_str.lower().split()
            full_url = urllib.parse.urljoin(base_url, href)

            if "apple-touch-icon" in rel_tokens or "apple-touch-icon-precomposed" in rel_tokens:
                apple_icons.append(full_url)
            elif "icon" in rel_tokens:
                standard_icons.append(full_url)

        # Prioritize apple_icons (often crisp 180x180 PNG), then standard icons
        candidates: list[str] = []
        seen = set()
        for u in apple_icons + standard_icons:
            if u not in seen:
                seen.add(u)
                candidates.append(u)

        return candidates

    def _is_image_data(self, content: bytes) -> bool:
        if not content:
            return False
        # PNG, ICO, GIF, JPEG, WebP, or SVG
        if (
            content.startswith(b"\x89PNG\r\n\x1a\n")
            or content.startswith(b"\x00\x00\x01\x00")
            or content.startswith(b"GIF87a")
            or content.startswith(b"GIF89a")
            or content.startswith(b"\xff\xd8\xff")
            or (content.startswith(b"RIFF") and b"WEBP" in content[:16])
            or b"<svg" in content[:1024].lower()
        ):
            return True
        return False

    def _detect_image_type(self, content: bytes) -> str:
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if content.startswith(b"\x00\x00\x01\x00"):
            return "image/x-icon"
        if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
            return "image/gif"
        if content.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if content.startswith(b"RIFF") and b"WEBP" in content[:16]:
            return "image/webp"
        if b"<svg" in content[:1024].lower():
            return "image/svg+xml"
        return "image/x-icon"

    async def _fetch_image(self, client: httpx.AsyncClient, url: str) -> tuple[bytes, str] | None:
        resp, _ = await self._safe_fetch(client, url, max_redirects=2)
        if resp is None or resp.status_code != 200:
            return None

        content_type = resp.headers.get("content-type", "").lower()
        content = resp.content

        # Verify image content type or magic bytes
        if not (
            content_type.startswith("image/")
            or "icon" in content_type
            or content_type == "application/octet-stream"
            or self._is_image_data(content)
        ):
            return None

        if not self._is_image_data(content) and not content_type.startswith("image/"):
            return None

        if not content_type or content_type == "application/octet-stream":
            content_type = self._detect_image_type(content)

        return content, content_type

    def _load_local_static(self, path: str) -> tuple[bytes, str] | None:
        clean_path = path.lstrip("/")
        if clean_path.startswith("static/"):
            clean_path = clean_path[len("static/") :]
        full_path = os.path.join(os.path.dirname(__file__), "..", "static", clean_path)
        if os.path.isfile(full_path):
            try:
                with open(full_path, "rb") as f:
                    content = f.read()
                return content, self._detect_image_type(content)
            except Exception:
                return None
        return None

    async def get_icon(self, service: ServiceConfig) -> CachedIcon | None:
        now = time.time()
        service_key = service.service_id

        # 1. In-memory cache hit
        if service_key in self._cache:
            cached = self._cache[service_key]
            if cached.expires_at > now:
                return cached
            del self._cache[service_key]

        # 1b. Persistent disk cache hit (favicons survive restarts)
        disk_cached = self.asset_cache.disk_cache.get("favicons", service.service_id)
        if disk_cached:
            data, meta = disk_cached
            expires_at = meta.get("expires_at", 0)
            if now < expires_at:
                cached = CachedIcon(
                    content=data,
                    media_type=meta.get("content_type", "image/png"),
                    etag=meta.get("etag", hashlib.md5(data).hexdigest()),
                    expires_at=expires_at,
                )
                self._cache[service_key] = cached
                return cached

        # 2. Negative cache hit
        if service_key in self._negative_cache:
            if self._negative_cache[service_key] > now:
                return None
            del self._negative_cache[service_key]

        async with self._get_client() as client:
            # Step 1: Discover via HTML <link rel="*icon*">
            resp, final_url = await self._safe_fetch(client, service.url, max_redirects=3)
            if resp is not None and resp.status_code == 200:
                html = resp.text
                candidate_urls = self._extract_icon_urls(html, final_url)
                for candidate in candidate_urls:
                    img_result = await self._fetch_image(client, candidate)
                    if img_result:
                        content, media_type = img_result
                        etag = hashlib.md5(content).hexdigest()
                        cached = CachedIcon(
                            content=content,
                            media_type=media_type,
                            etag=etag,
                            expires_at=now + self.cache_ttl,
                        )
                        self._cache[service_key] = cached
                        return cached

            # Step 2: Fallback to root /favicon.svg, then /favicon.ico
            for fallback_path in ("/favicon.svg", "/favicon.ico"):
                root_fallback = urllib.parse.urljoin(service.url, fallback_path)
                img_result = await self._fetch_image(client, root_fallback)
                if img_result:
                    content, media_type = img_result
                    etag = hashlib.md5(content).hexdigest()
                    cached = CachedIcon(
                        content=content,
                        media_type=media_type,
                        etag=etag,
                        expires_at=now + self.cache_ttl,
                    )
                    self._cache[service_key] = cached
                    self.asset_cache.disk_cache.put(
                        "favicons", service.service_id, content, media_type, etag, self.cache_ttl
                    )
                    return cached

            # Step 3: Fallback to fallback_icon (or icon)
            fallback = service.fallback_icon or service.icon
            if fallback:
                if fallback.startswith("/"):
                    local_img = self._load_local_static(fallback)
                    if local_img:
                        content, media_type = local_img
                        etag = hashlib.md5(content).hexdigest()
                        cached = CachedIcon(
                            content=content,
                            media_type=media_type,
                            etag=etag,
                            expires_at=now + self.cache_ttl,
                        )
                        self._cache[service_key] = cached
                        return cached
                elif fallback.startswith("http://") or fallback.startswith("https://"):
                    img_result = await self._fetch_image(client, fallback)
                    if img_result:
                        content, media_type = img_result
                        etag = hashlib.md5(content).hexdigest()
                        cached = CachedIcon(
                            content=content,
                            media_type=media_type,
                            etag=etag,
                            expires_at=now + self.cache_ttl,
                        )
                        self._cache[service_key] = cached
                        self.asset_cache.disk_cache.put(
                            "favicons", service.service_id, content, media_type, etag, self.cache_ttl
                        )
                        return cached
                else:
                    # Named Feather icon fallback resolved via asset cache
                    feather_asset = await self.asset_cache.get_feather_icon(fallback)
                    if feather_asset:
                        cached = CachedIcon(
                            content=feather_asset.content,
                            media_type=feather_asset.content_type,
                            etag=feather_asset.etag,
                            expires_at=now + self.cache_ttl,
                        )
                        self._cache[service_key] = cached
                        return cached

        # Step 4: No icon found; record negative cache
        self._negative_cache[service_key] = now + self.negative_ttl
        return None
