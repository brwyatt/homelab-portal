"""Authentication context parsing and user model."""
from __future__ import annotations

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
