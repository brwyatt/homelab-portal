"""Service catalogue evaluation, authorization filtering, and category grouping."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
from app.auth import UserContext
from app.config import CategoryConfig, PortalConfig, ServiceConfig
from app.network import NetworkLocation


@dataclass
class GroupedCategory:
    id: str
    name: str
    icon: str
    order: int
    services: List[ServiceConfig]


def is_service_visible(
    service: ServiceConfig,
    user: UserContext,
    location: NetworkLocation,
) -> bool:
    """Evaluate whether a service should be displayed to the current client."""
    if not service.enabled:
        return False

    # 1. Network Location Filter
    if service.network_classes:
        if location.network_class not in service.network_classes:
            return False

    # 2. Authentication & Group Filter
    if service.requires_groups:
        if not user.authenticated:
            return False
        if service.require_all_groups:
            if not user.has_all_groups(service.requires_groups):
                return False
        else:
            if not user.has_any_group(service.requires_groups):
                return False

    return True


def get_accessible_services(
    config: PortalConfig,
    user: UserContext,
    location: NetworkLocation,
) -> List[GroupedCategory]:
    """Filter services by access rules and group them into categories."""
    # Filter visible services
    visible_services = [
        s for s in config.services if is_service_visible(s, user, location)
    ]

    # Map categories by ID
    category_map: Dict[str, CategoryConfig] = {c.id: c for c in config.categories}

    # Group services by category ID
    services_by_cat: Dict[str, List[ServiceConfig]] = {}
    for service in visible_services:
        services_by_cat.setdefault(service.category, []).append(service)

    # Build grouped list
    result: List[GroupedCategory] = []
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
