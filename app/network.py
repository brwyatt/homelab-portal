"""Network resolution and client classification logic."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from fastapi import Request

from app.config import NetworkConfig, PortalConfig, SubnetConfig


@dataclass
class NetworkLocation:
    client_ip: str
    network_class: str
    network_class_name: str
    network_class_icon: str
    subnet_cidr: str | None
    subnet_name: str
    icon: str


def get_client_ip(request: Request, network_config: NetworkConfig) -> str:
    """Extract real client IP by walking X-Forwarded-For right-to-left
    past all trusted reverse proxies.
    """
    direct_ip = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("x-forwarded-for")
    if not forwarded_for:
        return direct_ip

    # Split and strip IP chain
    ips = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
    if not ips:
        return direct_ip

    trusted_networks = [
        ipaddress.ip_network(cidr, strict=False) for cidr in network_config.trusted_proxies
    ]

    def is_trusted(ip_str: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip_str)
            return any(addr in net for net in trusted_networks)
        except ValueError:
            return False

    # Also check if the direct connection is from a trusted proxy
    if not is_trusted(direct_ip):
        # Direct connection is not trusted; ignore X-Forwarded-For spoofing
        return direct_ip

    # Walk backwards from right to left through the X-Forwarded-For list
    for ip in reversed(ips):
        if not is_trusted(ip):
            return ip

    # If all IPs in XFF were trusted proxies, return the leftmost IP
    return ips[0]


def resolve_location(client_ip: str, config: PortalConfig) -> NetworkLocation:
    """Match client IP against configured subnets using Longest Prefix Match."""
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return NetworkLocation(
            client_ip=client_ip,
            network_class=config.network.fallback_class,
            network_class_name=config.network.fallback_name,
            network_class_icon=config.network.fallback_icon,
            subnet_cidr=None,
            subnet_name=config.network.fallback_name,
            icon=config.network.fallback_icon,
        )

    # Sort subnets by prefix length descending for longest prefix match
    parsed_subnets: list[tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, SubnetConfig]] = []
    for s in config.subnets:
        try:
            net = ipaddress.ip_network(s.cidr, strict=False)
            parsed_subnets.append((net, s))
        except ValueError:
            continue

    parsed_subnets.sort(key=lambda item: item[0].prefixlen, reverse=True)

    for net, subnet_cfg in parsed_subnets:
        if addr in net:
            class_cfg = config.network_classes.get(subnet_cfg.network_class)
            class_name = class_cfg.name if class_cfg else subnet_cfg.network_class.title()
            class_icon = class_cfg.icon if class_cfg else "network"
            icon = subnet_cfg.icon or class_icon

            return NetworkLocation(
                client_ip=client_ip,
                network_class=subnet_cfg.network_class,
                network_class_name=class_name,
                network_class_icon=class_icon,
                subnet_cidr=subnet_cfg.cidr,
                subnet_name=subnet_cfg.name,
                icon=icon,
            )

    # Fallback if no subnets match
    fallback_cls = config.network_classes.get(config.network.fallback_class)
    fallback_name = fallback_cls.name if fallback_cls else config.network.fallback_name
    fallback_icon = fallback_cls.icon if fallback_cls else config.network.fallback_icon

    return NetworkLocation(
        client_ip=client_ip,
        network_class=config.network.fallback_class,
        network_class_name=fallback_name,
        network_class_icon=fallback_icon,
        subnet_cidr=None,
        subnet_name=config.network.fallback_name,
        icon=fallback_icon,
    )
