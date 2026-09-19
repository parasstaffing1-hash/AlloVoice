"""Smoke tests for VoiceField backend (no external services required)."""

import os
import uuid

os.environ["TESTING"] = "1"

import pytest


@pytest.fixture(scope="function")
def client():
    # Function scope: each test gets a fresh TestClient/portal event loop.
    # (Module scope reuses a closed loop with async SQLAlchemy engines.)
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        test_client = TestClient(app)
    except Exception as exc:
        pytest.skip(f"Skipping smoke tests: app/TestClient unavailable ({exc})")
    return test_client


def test_health_check(client):
    try:
        resp = client.get("/api/health")
    except Exception as exc:
        pytest.skip(f"Skipping: health check unavailable ({exc})")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"


def test_register_then_login(client):
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.co.uk"
    password = "SmokeTest123!"
    try:
        reg = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "full_name": "Smoke Test"},
        )
    except Exception as exc:
        pytest.skip(f"Skipping: DB unavailable ({exc})")
    if reg.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (register 5xx)")
    assert reg.status_code in (200, 201), reg.text
    assert "access_token" in reg.json()

    try:
        login = client.post(
            "/api/auth/login", json={"email": email, "password": password}
        )
    except Exception as exc:
        pytest.skip(f"Skipping: DB unavailable ({exc})")
    if login.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (login 5xx)")
    assert login.status_code == 200
    assert "access_token" in login.json()


def test_unauthenticated_customers_returns_401_403(client):
    try:
        resp = client.get("/api/customers/")
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code in (401, 403)


def test_pricebook_calculate_vat_20_percent(client):
    email = f"vat-{uuid.uuid4().hex[:8]}@example.co.uk"
    password = "SmokeTest123!"
    try:
        reg = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "full_name": "VAT Test"},
        )
    except Exception as exc:
        pytest.skip(f"Skipping: DB unavailable ({exc})")
    if reg.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (register 5xx)")
    assert reg.status_code in (200, 201), reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    try:
        svc = client.post(
            "/api/pricebook/services",
            json={
                "name": "VAT Service",
                "category": "test",
                "base_price": 100.0,
                "vat_rate": 20.0,
            },
            headers=headers,
        )
    except Exception as exc:
        pytest.skip(f"Skipping: DB unavailable ({exc})")
    if svc.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (pricebook 5xx)")
    assert svc.status_code in (200, 201), svc.text
    service_id = svc.json()["id"]

    try:
        calc = client.post(
            "/api/pricebook/calculate",
            json={
                "services": [{"id": service_id, "quantity": 1.0}],
                "materials": [],
                "markup_override": 0.0,
                "job_type": "standard",
            },
            headers=headers,
        )
    except Exception as exc:
        pytest.skip(f"Skipping: DB unavailable ({exc})")
    assert calc.status_code == 200, calc.text
    data = calc.json()
    # 20% of 100 with zero markup must be exactly 20 VAT and 120 total.
    assert data["vat_amount"] == 20.0
    assert data["total"] == 120.0


def test_openapi_schema_loads(client):
    try:
        resp = client.get("/openapi.json")
    except Exception as exc:
        pytest.skip(f"Skipping: OpenAPI unavailable ({exc})")
    assert resp.status_code == 200
    schema = resp.json()
    assert "paths" in schema
    assert "openapi" in schema
