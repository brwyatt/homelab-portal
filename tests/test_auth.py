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
