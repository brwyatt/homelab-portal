"""Tests for /api/status endpoint."""
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app, config
from app.config import ServiceConfig, HealthCheckConfig, CategoryConfig


@pytest.mark.asyncio
async def test_api_status_endpoint():
    # Configure test category and services
    config.categories = [
        CategoryConfig(
            id="test-cat",
            name="Test Category",
            services=[
                ServiceConfig(
                    name="Service Without Health",
                    url="https://nohealth.local",
                ),
            ],
        )
    ]
    config.services = []
    config.sync_categories_and_services()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "statuses" in data
        assert "service-without-health" in data["statuses"]
        assert data["statuses"]["service-without-health"]["status"] == "unknown"
