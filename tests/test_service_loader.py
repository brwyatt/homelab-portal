from app.auth import UserContext
from app.config import AccessConfig, CategoryConfig, PortalConfig, ServiceConfig
from app.network import NetworkLocation
from app.service_loader import get_accessible_services, is_service_visible


def test_is_service_visible_network_class():
    loc_internal = NetworkLocation(
        client_ip="192.168.1.10",
        network_class="internal",
        network_class_name="Internal",
        network_class_icon="home",
        subnet_cidr="192.168.1.0/24",
        subnet_name="LAN",
        icon="home",
    )
    loc_external = NetworkLocation(
        client_ip="1.2.3.4",
        network_class="external",
        network_class_name="External",
        network_class_icon="globe",
        subnet_cidr=None,
        subnet_name="External",
        icon="globe",
    )
    user = UserContext(authenticated=False)

    service_restricted = ServiceConfig(
        name="Internal Only",
        url="https://int.local",
        category="core",
        access=AccessConfig(network_classes=["internal", "management"]),
    )

    assert is_service_visible(service_restricted, user, loc_internal) is True
    assert is_service_visible(service_restricted, user, loc_external) is False


def test_is_service_visible_groups():
    loc = NetworkLocation(
        client_ip="10.0.0.1",
        network_class="internal",
        network_class_name="Internal",
        network_class_icon="home",
        subnet_cidr=None,
        subnet_name="LAN",
        icon="home",
    )
    anon = UserContext(authenticated=False)
    user_regular = UserContext(authenticated=True, username="alice", groups=["users"])
    user_admin = UserContext(authenticated=True, username="bryan", groups=["users", "admins"])

    svc = ServiceConfig(
        name="Admin Panel",
        url="https://admin.local",
        category="core",
        access=AccessConfig(groups=["admins"]),
    )

    assert is_service_visible(svc, anon, loc) is False
    assert is_service_visible(svc, user_regular, loc) is False
    assert is_service_visible(svc, user_admin, loc) is True


def test_is_service_visible_users_and_groups():
    loc = NetworkLocation(
        client_ip="10.0.0.1",
        network_class="internal",
        network_class_name="Internal",
        network_class_icon="home",
        subnet_cidr=None,
        subnet_name="LAN",
        icon="home",
    )
    user_bob = UserContext(authenticated=True, username="bob", groups=["users"])
    user_alice = UserContext(authenticated=True, username="alice", groups=["users", "admins"])
    user_carol = UserContext(authenticated=True, username="carol", groups=["admins"])

    # Match ALL (default): user in users AND group in groups
    svc_all = ServiceConfig(
        name="Bob Admin Only",
        url="https://bob.local",
        category="core",
        access=AccessConfig(users=["bob"], groups=["admins"], match="all"),
    )
    assert is_service_visible(svc_all, user_bob, loc) is False  # Bob lacks admins group
    assert is_service_visible(svc_all, user_alice, loc) is False  # Alice has admin but is not bob
    user_bob_admin = UserContext(authenticated=True, username="bob", groups=["admins"])
    assert is_service_visible(svc_all, user_bob_admin, loc) is True

    # Match ANY: user in users OR group in groups
    svc_any = ServiceConfig(
        name="Bob or Admins",
        url="https://shared.local",
        category="core",
        access=AccessConfig(users=["bob"], groups=["admins"], match="any"),
    )
    assert is_service_visible(svc_any, user_bob, loc) is True   # Bob matches user
    assert is_service_visible(svc_any, user_carol, loc) is True # Carol matches admins group
    user_eve = UserContext(authenticated=True, username="eve", groups=["users"])
    assert is_service_visible(svc_any, user_eve, loc) is False  # Eve matches neither


def test_get_accessible_services_grouping():
    config = PortalConfig(
        categories=[
            CategoryConfig(id="b_cat", name="Category B", order=20),
            CategoryConfig(id="a_cat", name="Category A", order=10),
        ],
        services=[
            ServiceConfig(name="Svc B1", url="http://b1", category="b_cat", order=10),
            ServiceConfig(name="Svc A2", url="http://a2", category="a_cat", order=20),
            ServiceConfig(name="Svc A1", url="http://a1", category="a_cat", order=10),
        ],
    )
    user = UserContext(authenticated=True)
    loc = NetworkLocation(
        client_ip="127.0.0.1",
        network_class="internal",
        network_class_name="Internal",
        network_class_icon="home",
        subnet_cidr=None,
        subnet_name="Local",
        icon="home",
    )

    grouped = get_accessible_services(config, user, loc)
    assert len(grouped) == 2
    # Category A should be first due to order=10
    assert grouped[0].id == "a_cat"
    assert grouped[0].services[0].name == "Svc A1"
    assert grouped[0].services[1].name == "Svc A2"

    assert grouped[1].id == "b_cat"
