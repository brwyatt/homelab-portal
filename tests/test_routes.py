import pytest
from fastapi.testclient import TestClient
from app.main import app, reload_configuration


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    # Load example config for tests
    monkeypatch.setenv("PORTAL_CONFIG_PATH", "config.yml.example")
    _ = reload_configuration()
    return TestClient(app)


def test_healthz(client: TestClient):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_readyz(client: TestClient):
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ready"}


def test_serve_theme_fiber_optic(client: TestClient):
    res = client.get("/theme.css")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/css")
    assert "#101c2a" in res.text or "#34c3b1" in res.text


def test_api_context(client: TestClient):
    res = client.get("/api/context")
    assert res.status_code == 200
    data = res.json()
    assert "client_ip" in data
    assert "location" in data
    assert "user" in data


def test_index_page(client: TestClient):
    res = client.get("/")
    assert res.status_code == 200
    assert "Homelab Portal" in res.text
    assert 'id="service-search"' in res.text


def test_index_page_login_url_variable_substitution(client: TestClient):
    from app.main import config
    config.auth.enabled = True
    config.auth.login_url = "https://auth.example.com/?rd=$scheme://$http_host$request_uri"
    config.ui.show_user_badge = True

    res = client.get(
        "/",
        headers={
            "Host": "home.brwyatt.net",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "home.brwyatt.net",
        },
    )
    assert res.status_code == 200
    assert 'href="https://auth.example.com/?rd=https://home.brwyatt.net/"' in res.text
