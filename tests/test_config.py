import pytest
from app.config import PortalConfig, SubnetConfig, load_config


def test_default_config():
    config = PortalConfig()
    assert config.ui.title == "Homelab Portal"
    assert config.ui.theme == "fiber-optic"
    assert config.auth.enabled is False
    assert "127.0.0.1/32" in config.network.trusted_proxies


def test_subnet_validation():
    # Valid CIDR
    s = SubnetConfig(cidr="192.168.1.0/24", name="LAN", network_class="internal")
    assert s.cidr == "192.168.1.0/24"

    # Invalid CIDR
    with pytest.raises(ValueError):
        SubnetConfig(cidr="invalid-cidr", name="LAN", network_class="internal")


def test_service_public_default():
    config = PortalConfig(
        services=[
            {"name": "Public Service", "url": "https://pub.com", "category": "general"},
            {
                "name": "Restricted Service",
                "url": "https://priv.com",
                "category": "general",
                "requires_groups": ["admins"],
            },
        ]
    )
    assert config.services[0].public is True
    assert config.services[1].public is False


def test_load_example_config():
    config = load_config("config.yml.example")
    assert len(config.categories) > 0
    assert len(config.services) > 0
    assert "management" in config.network_classes
