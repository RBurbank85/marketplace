import asyncio
import sqlite3
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from api.main import app
from api import deps
from api.deps import get_db
from config.settings import settings


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_db_override():
        return session

    app.dependency_overrides[get_db] = get_db_override
    client = TestClient(app, headers={"X-API-Key": settings.api_key})
    yield client
    app.dependency_overrides.clear()


def test_root(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "MAIE / Market Desk" in response.text


def test_documented_fastapi_entrypoint_and_public_assets(client: TestClient):
    assert isinstance(app, FastAPI)

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "MAIE / Market Desk" in dashboard.text

    dashboard_script = client.get("/dashboard/assets/dashboard.js")
    assert dashboard_script.status_code == 200
    assert "loadDashboard" in dashboard_script.text

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == "MAIE API"


def test_protected_endpoint_requires_configured_api_key(client: TestClient):
    client.headers.pop("X-API-Key")
    response = client.get("/listings/")
    assert response.status_code == 401
    assert response.json()["detail"] == "API key required for this endpoint"


def test_protected_endpoint_rejects_invalid_api_key(client: TestClient):
    response = client.get("/listings/", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Could not validate API key"


def test_protected_endpoint_accepts_configured_api_key(client: TestClient):
    response = client.get("/listings/", headers={"X-API-Key": settings.api_key})
    assert response.status_code == 200


def test_list_listings_empty(client: TestClient):
    response = client.get("/listings/")
    assert response.status_code == 200
    assert response.json() == []


def test_create_listing(client: TestClient):
    response = client.post(
        "/listings/",
        json={
            "title": "Test Listing",
            "price": 100.0,
            "source": "test",
            "external_id": "test-1",
            "url": "http://test.com",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Listing"
    assert data["price"] == 100.0
    assert "id" in data


def test_get_config(client: TestClient):
    response = client.get("/config/")
    assert response.status_code == 200
    data = response.json()
    assert "app_name" in data
    assert "ai_api_key" not in data
    assert "api_key" not in data
    assert "secret_key" not in data


def test_api_auth_can_be_intentionally_disabled(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "api_auth_enabled", False)
    client.headers.pop("X-API-Key")

    response = client.get("/listings/")

    assert response.status_code == 200


def test_list_collectors(client: TestClient):
    response = client.get("/collectors/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Should have at least one collector if they are discovered
    assert len(data) > 0


def test_list_categories(client: TestClient):
    response = client.get("/categories/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_scheduler_status(client: TestClient):
    response = client.get("/scheduler/status")
    assert response.status_code == 200
    data = response.json()
    assert "running" in data


def test_analytics_requires_snapshot_then_syncs_and_reads(
    client: TestClient, tmp_path, monkeypatch
):
    operational = tmp_path / "operational.db"
    warehouse = tmp_path / "analytics.duckdb"
    sqlite3.connect(operational).close()
    monkeypatch.setattr(settings, "sqlite_path", operational)
    monkeypatch.setattr(settings, "analytics_warehouse_path", warehouse)

    missing = client.get("/analytics/daily-listing-volume")
    assert missing.status_code == 409
    assert missing.json() == {
        "detail": {
            "code": "analytics_snapshot_required",
            "message": "Analytics data is not available yet. Run 'maie analytics sync' and try again.",
        }
    }

    synced = client.post("/analytics/sync")
    assert synced.status_code == 200
    assert synced.json()["tables"] == {}
    assert warehouse.exists()
    assert client.get("/analytics/daily-listing-volume").json() == []


def test_analytics_sync_endpoint_requires_api_key(client: TestClient):
    client.headers.pop("X-API-Key")
    response = client.post("/analytics/sync")
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [("success", 200), ("skipped", 200), ("failed", 500)],
)
def test_scheduler_run_awaits_service_and_maps_result(
    client: TestClient, status: str, expected_code: int
):
    class FakeScheduler:
        async def run_job(self, collector_name: str) -> dict[str, Any]:
            return {"collector": collector_name, "status": status}

    app.dependency_overrides[deps.get_scheduler_service] = FakeScheduler
    response = client.post("/scheduler/run/test")

    assert response.status_code == expected_code
    if expected_code == 200:
        assert response.json()["status"] == status


@pytest.fixture
def isolated_rate_limiter(monkeypatch):
    deps._rate_limiter.clear()
    monkeypatch.setattr(settings, "rate_limit_requests_per_minute", 2)
    yield
    deps._rate_limiter.clear()


def test_rate_limiter_allows_requests_below_limit(
    client: TestClient, isolated_rate_limiter
):
    assert client.get("/listings/").status_code == 200
    assert client.get("/listings/").status_code == 200


def test_rate_limiter_rejects_first_request_over_limit(
    client: TestClient, isolated_rate_limiter
):
    client.get("/listings/")
    client.get("/listings/")

    response = client.get("/listings/")

    assert response.status_code == 429
    assert response.json()["detail"] == "Rate limit exceeded. Try again later."


def test_rate_limiter_allows_request_after_window_expiry(
    client: TestClient, isolated_rate_limiter, monkeypatch
):
    current_time = [100.0]
    monkeypatch.setattr(deps.time, "monotonic", lambda: current_time[0])
    settings.rate_limit_requests_per_minute = 1

    assert client.get("/listings/").status_code == 200
    assert client.get("/listings/").status_code == 429

    current_time[0] += 60.0
    assert client.get("/listings/").status_code == 200


def test_rate_limiter_tracks_separate_clients(isolated_rate_limiter):
    def request_for(host: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/listings/",
                "headers": [],
                "client": (host, 12345),
            }
        )

    settings.rate_limit_requests_per_minute = 1
    asyncio.run(deps.rate_limiter(request_for("192.0.2.1")))
    asyncio.run(deps.rate_limiter(request_for("192.0.2.2")))


@pytest.mark.parametrize("disabled_limit", [None, 0])
def test_rate_limiter_can_be_disabled(disabled_limit, isolated_rate_limiter):
    settings.rate_limit_requests_per_minute = disabled_limit
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/listings/",
            "headers": [],
            "client": ("192.0.2.3", 12345),
        }
    )

    asyncio.run(deps.rate_limiter(request))
    asyncio.run(deps.rate_limiter(request))
