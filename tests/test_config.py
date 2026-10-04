import pytest
from app.config import PortalConfig, ServiceConfig, SubnetConfig, load_config


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
        _ = SubnetConfig(cidr="invalid-cidr", name="LAN", network_class="internal")


def test_service_public_default():
    config = PortalConfig(
        services=[
            ServiceConfig(name="Public Service", url="https://pub.com", category="general"),
            ServiceConfig(
                name="Restricted Service",
                url="https://priv.com",
                category="general",
                access={"groups": ["admins"]},
            ),
            ServiceConfig(
                name="User Restricted Service",
                url="https://user.com",
                category="general",
                access={"users": ["bwyatt"]},
            ),
        ]
    )
    assert config.services[0].public is True
    assert config.services[1].public is False
    assert config.services[2].public is False


def test_load_example_config():
    config = load_config("config.yml.example")
    assert len(config.categories) > 0
    assert len(config.services) > 0
    assert "management" in config.network_classes

def test_category_nested_services_ordering_and_defaults() -> None:
    raw = {
        "categories": [
            {
                "id": "second_cat",
                "name": "Second Category",
                "services": [
                    {"name": "Svc 2A", "url": "https://2a"},
                    {"name": "Svc 2B", "url": "https://2b", "order": 5},
                ]
            },
            {
                "id": "first_cat",
                "name": "First Category",
                "services": [
                    {"name": "Svc 1A", "url": "https://1a"},
                ]
            }
        ]
    }
    cfg = PortalConfig.model_validate(raw)
    assert len(cfg.categories) == 2
    # Natural order preserved
    assert cfg.categories[0].id == "second_cat"
    assert cfg.categories[0].order == 10
    assert cfg.categories[1].id == "first_cat"
    assert cfg.categories[1].order == 20

    # Services nested merged and ordered
    assert len(cfg.services) == 3
    s2a = cfg.get_service_by_id("svc-2a")
    assert s2a is not None
    assert s2a.category == "second_cat"
    assert s2a.order == 10

    s2b = cfg.get_service_by_id("svc-2b")
    assert s2b is not None
    assert s2b.category == "second_cat"
    assert s2b.order == 5
