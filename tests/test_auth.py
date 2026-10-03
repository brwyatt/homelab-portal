from unittest.mock import Mock
from app.auth import UserContext, get_user_context
from app.config import AuthConfig


def test_user_context_has_group():
    user = UserContext(
        authenticated=True,
        username="bryan",
        groups=["admins", "homelab", "developers"],
    )
    assert user.has_group("admins") is True
    assert user.has_group("ADMINS") is True  # Case insensitive
    assert user.has_group("guests") is False


def test_user_context_any_and_all_groups():
    user = UserContext(
        authenticated=True,
        username="bryan",
        groups=["admins", "monitoring"],
    )
    assert user.has_any_group(["monitoring", "other"]) is True
    assert user.has_any_group(["other", "unknown"]) is False

    assert user.has_all_groups(["admins", "monitoring"]) is True
    assert user.has_all_groups(["admins", "other"]) is False


def test_get_user_context_headers():
    auth_cfg = AuthConfig(enabled=True)
    req = Mock()
    req.headers = {
        "remote-user": "bryan",
        "remote-name": "Bryan Wyatt",
        "remote-email": "bryan@brwyatt.net",
        "remote-groups": "admins, homelab, sudo",
    }

    user = get_user_context(req, auth_cfg)
    assert user.authenticated is True
    assert user.username == "bryan"
    assert user.display_name == "Bryan Wyatt"
    assert user.email == "bryan@brwyatt.net"
    assert "admins" in user.groups
    assert "homelab" in user.groups
    assert "sudo" in user.groups


def test_get_user_context_disabled():
    auth_cfg = AuthConfig(enabled=False)
    req = Mock()
    req.headers = {"remote-user": "bryan"}

    user = get_user_context(req, auth_cfg)
    assert user.authenticated is False
    assert user.username is None


def test_resolve_auth_url_variables():
    from app.auth import resolve_auth_url
    from starlette.datastructures import Headers
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/dashboard",
        "query_string": b"tab=services",
        "headers": Headers({
            "host": "portal.home.brwyatt.net",
            "x-forwarded-proto": "https",
            "x-forwarded-host": "portal.home.brwyatt.net",
            "x-forwarded-uri": "/dashboard?tab=services",
        }).raw,
    }
    request = Request(scope)

    # Nginx-style variables
    template_nginx = "https://auth.home.brwyatt.net/?rd=$scheme://$http_host$request_uri"
    resolved = resolve_auth_url(template_nginx, request)
    assert resolved == "https://auth.home.brwyatt.net/?rd=https://portal.home.brwyatt.net/dashboard?tab=services"

    # Full URL variable
    template_url = "https://auth.home.brwyatt.net/?rd=${url}"
    resolved_url = resolve_auth_url(template_url, request)
    assert resolved_url == "https://auth.home.brwyatt.net/?rd=https://portal.home.brwyatt.net/dashboard?tab=services"

    # Escaped URL variable
    template_escaped = "https://auth.home.brwyatt.net/?rd={escaped_url}"
    resolved_escaped = resolve_auth_url(template_escaped, request)
    assert resolved_escaped == "https://auth.home.brwyatt.net/?rd=https%3A%2F%2Fportal.home.brwyatt.net%2Fdashboard%3Ftab%3Dservices"

    # Host without port
    scope_port = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": Headers({
            "host": "portal.home.brwyatt.net:8080",
            "x-forwarded-proto": "http",
        }).raw,
    }
    req_port = Request(scope_port)
    assert resolve_auth_url("http://auth/?rd=$scheme://$host$request_uri", req_port) == "http://auth/?rd=http://portal.home.brwyatt.net/"
    assert resolve_auth_url("http://auth/?rd=$scheme://$http_host$request_uri", req_port) == "http://auth/?rd=http://portal.home.brwyatt.net:8080/"

    # Static URL without placeholders
    static_url = "https://auth.home.brwyatt.net/login"
    assert resolve_auth_url(static_url, request) == static_url

    # None and empty handling
    assert resolve_auth_url(None, request) is None
    assert resolve_auth_url("", request) is None
    assert resolve_auth_url("https://auth.home.brwyatt.net", None) == "https://auth.home.brwyatt.net"

