from unittest.mock import Mock
from app.config import NetworkClassConfig, NetworkConfig, PortalConfig, SubnetConfig
from app.network import get_client_ip, resolve_location


def test_get_client_ip_direct():
    req = Mock()
    req.client.host = "192.168.1.50"
    req.headers = {}
    net_cfg = NetworkConfig(trusted_proxies=["127.0.0.1/32"])

    ip = get_client_ip(req, net_cfg)
    assert ip == "192.168.1.50"


def test_get_client_ip_trusted_proxy_chain():
    req = Mock()
    # Connecting directly from reverse proxy
    req.client.host = "10.0.0.10"
    # Header: client -> gateway -> proxy
    req.headers = {"x-forwarded-for": "203.0.113.195, 10.0.0.5, 10.0.0.10"}
    net_cfg = NetworkConfig(trusted_proxies=["10.0.0.0/24"])

    ip = get_client_ip(req, net_cfg)
    assert ip == "203.0.113.195"


def test_get_client_ip_untrusted_direct_ignores_header():
    req = Mock()
    # Direct attacker trying to spoof X-Forwarded-For
    req.client.host = "198.51.100.2"
    req.headers = {"x-forwarded-for": "10.0.0.1"}
    net_cfg = NetworkConfig(trusted_proxies=["10.0.0.0/24"])

    ip = get_client_ip(req, net_cfg)
    assert ip == "198.51.100.2"


def test_resolve_location_longest_prefix_match():
    config = PortalConfig(
        network_classes={
            "internal": NetworkClassConfig(name="Internal LAN", icon="home"),
            "management": NetworkClassConfig(name="Admin Subnet", icon="shield"),
        },
        subnets=[
            SubnetConfig(cidr="10.0.0.0/16", name="Broad 10/16", network_class="internal"),
            SubnetConfig(cidr="10.0.5.0/24", name="Specific Admin 10.0.5/24", network_class="management"),
        ],
    )

    # IP in specific /24 should match management
    loc1 = resolve_location("10.0.5.42", config)
    assert loc1.network_class == "management"
    assert loc1.subnet_name == "Specific Admin 10.0.5/24"

    # IP in broader /16 should match internal
    loc2 = resolve_location("10.0.20.1", config)
    assert loc2.network_class == "internal"
    assert loc2.subnet_name == "Broad 10/16"

    # External IP fallback
    loc3 = resolve_location("8.8.8.8", config)
    assert loc3.network_class == "external"
