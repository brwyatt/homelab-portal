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
    if not access:
        return True

    if access.network_classes and location.network_class not in access.network_classes:
        return False

    if not (access.users or access.groups):
        return True

    if not user.authenticated:
        return False

    checks: list[bool] = []
    if access.users:
        checks.append(user.matches_user(access.users))
    if access.groups:
        match_fn = user.has_all_groups if access.require_all_groups else user.has_any_group
        checks.append(match_fn(access.groups))

    return any(checks) if access.match == "any" else all(checks)


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
