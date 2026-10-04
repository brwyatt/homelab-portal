"""Service catalogue evaluation, authorization filtering, and category grouping."""
from __future__ import annotations

from dataclasses import dataclass
from app.auth import UserContext
from app.config import CategoryConfig, PortalConfig, ServiceConfig
from app.network import NetworkLocation


@dataclass
class GroupedCategory:
    id: str
    name: str
    icon: str
    order: int
    services: list[ServiceConfig]


def is_service_visible(
    service: ServiceConfig,
    user: UserContext,
    location: NetworkLocation,
) -> bool:
    """Evaluate whether a service should be displayed to the current client."""
    if not service.enabled:
        return False

    access = service.access
    if access is None:
        return True

    # 1. Network Location Filter
    if access.network_classes:
        if location.network_class not in access.network_classes:
            return False

    # 2. Authentication & Identity Filter (users / groups)
    has_user_filter = bool(access.users)
    has_group_filter = bool(access.groups)

    if not has_user_filter and not has_group_filter:
        return True

    if not user.authenticated:
        return False

    # Check user identity match
    user_match = user.matches_user(access.users) if has_user_filter else None

    # Check group membership match
    group_match: bool | None = None
    if has_group_filter:
        if access.require_all_groups:
            group_match = user.has_all_groups(access.groups)
        else:
            group_match = user.has_any_group(access.groups)

    # Evaluate combined rule
    if has_user_filter and has_group_filter:
        if access.match == "any":
            return bool(user_match or group_match)
        else:  # "all"
            return bool(user_match and group_match)

    if has_user_filter:
        return bool(user_match)

    if has_group_filter:
        return bool(group_match)

    return True


def get_accessible_services(
    config: PortalConfig,
    user: UserContext,
    location: NetworkLocation,
) -> list[GroupedCategory]:
    """Filter services by access rules and group them into categories."""
    # Filter visible services
    visible_services = [
        s for s in config.services if is_service_visible(s, user, location)
    ]

    # Map categories by ID
    category_map: dict[str, CategoryConfig] = {c.id: c for c in config.categories}

    # Group services by category ID
    services_by_cat: dict[str, list[ServiceConfig]] = {}
    for service in visible_services:
        services_by_cat.setdefault(service.category, []).append(service)

    # Build grouped list
    result: list[GroupedCategory] = []
    for cat_id, cat_services in services_by_cat.items():
        cat_cfg = category_map.get(cat_id)
        if cat_cfg:
            name = cat_cfg.name
            icon = cat_cfg.icon or "folder"
            order = cat_cfg.order
        else:
            name = cat_id.replace("_", " ").replace("-", " ").title()
            icon = "folder"
            order = 999

        # Sort services within this category by order then name
        cat_services.sort(key=lambda s: (s.order, s.name.lower()))

        result.append(
            GroupedCategory(
                id=cat_id,
                name=name,
                icon=icon,
                order=order,
                services=cat_services,
            )
        )

    # Sort categories by order then name
    result.sort(key=lambda c: (c.order, c.name.lower()))
    return result
