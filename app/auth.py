"""Authentication context parsing and user model."""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from fastapi import Request

from app.config import AuthConfig


@dataclass
class UserContext:
    authenticated: bool = False
    username: str | None = None
    display_name: str | None = None
    email: str | None = None
    groups: list[str] = field(default_factory=list)

    def has_group(self, group: str) -> bool:
        return group.lower() in [g.lower() for g in self.groups]

    def has_any_group(self, required_groups: list[str]) -> bool:
        user_groups = {g.lower() for g in self.groups}
        req_groups = {g.lower() for g in required_groups}
        return bool(user_groups.intersection(req_groups))

    def has_all_groups(self, required_groups: list[str]) -> bool:
        user_groups = {g.lower() for g in self.groups}
        req_groups = {g.lower() for g in required_groups}
        return req_groups.issubset(user_groups)

    def matches_user(self, allowed_users: list[str]) -> bool:
        if not self.username:
            return False
        return self.username.lower() in [u.lower() for u in allowed_users]


def get_user_context(request: Request, auth_config: AuthConfig) -> UserContext:
    """Extract authenticated user info and group memberships from headers."""
    if not auth_config.enabled:
        return UserContext(authenticated=False, username=None, display_name=None, email=None, groups=[])

    user_header = auth_config.header_user.lower()
    username = request.headers.get(user_header)
    if not username:
        return UserContext(authenticated=False, username=None, display_name="Anonymous", email=None, groups=[])

    username = username.strip()
    name_header = auth_config.header_name.lower()
    email_header = auth_config.header_email.lower()
    groups_header = auth_config.header_groups.lower()

    display_name = request.headers.get(name_header, "").strip() or username
    email = request.headers.get(email_header, "").strip() or None

    raw_groups = request.headers.get(groups_header, "")
    groups: list[str] = []
    if raw_groups:
        groups = [
            g.strip()
            for g in raw_groups.split(auth_config.header_group_delimiter)
            if g.strip()
        ]

    return UserContext(
        authenticated=True,
        username=username,
        display_name=display_name,
        email=email,
        groups=groups,
    )


def resolve_auth_url(url_template: str | None, request: Request | None) -> str | None:
    """Resolve dynamic placeholders in an authentication URL template using request headers.

    Supported variables (syntax: $var, ${var}, or {var}):
      - scheme: 'https' or 'http' (honors X-Forwarded-Proto, X-Forwarded-Scheme)
      - http_host: host with port if specified in Host / X-Forwarded-Host
      - host: hostname without port
      - request_uri: request path with query string (honors X-Forwarded-Uri)
      - uri: alias for request_uri
      - url: full URL ($scheme://$http_host$request_uri)
      - escaped_url: URL-encoded full URL for query parameter safety
    """
    if not url_template:
        return None
    if not request:
        return url_template

    raw_scheme = (
        request.headers.get("x-forwarded-proto")
        or request.headers.get("x-forwarded-scheme")
        or request.url.scheme
        or "http"
    )
    scheme = raw_scheme.split(",")[0].strip()

    raw_host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
        or "localhost"
    )
    http_host = raw_host.split(",")[0].strip()
    host = http_host.split(":")[0] if ":" in http_host else http_host

    uri = request.headers.get("x-forwarded-uri")
    if not uri:
        path = request.url.path or "/"
        query = request.url.query
        uri = f"{path}?{query}" if query else path

    full_url = f"{scheme}://{http_host}{uri}"

    var_map: dict[str, str] = {
        "scheme": scheme,
        "http_host": http_host,
        "host": host,
        "request_uri": uri,
        "uri": uri,
        "url": full_url,
        "escaped_url": urllib.parse.quote(full_url, safe=""),
    }

    pattern = re.compile(r"\$\{([a-zA-Z0-9_]+)\}|\$([a-zA-Z0-9_]+)|\{([a-zA-Z0-9_]+)\}")

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1) or match.group(2) or match.group(3)
        return var_map.get(var_name, match.group(0))

    return pattern.sub(_replace, url_template)

