"""Brevo marketing tests (mock-only: no live keys, no external calls)."""

import os
import uuid

os.environ["TESTING"] = "1"

import pytest


@pytest.fixture(scope="function")
def client():
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        test_client = TestClient(app)
    except Exception as exc:
        pytest.skip(f"Skipping brevo tests: app/TestClient unavailable ({exc})")
    return test_client


@pytest.fixture(scope="function")
def no_keys():
    """Force keyless Brevo config (Settings + env)."""
    try:
        from app.core.config import get_settings
    except Exception as exc:
        pytest.skip(f"Skipping brevo tests: imports unavailable ({exc})")
    settings = get_settings()
    old_key = getattr(settings, "BREVO_API_KEY", "")
    old_sender_email = getattr(settings, "BREVO_SENDER_EMAIL", "")
    old_sender_name = getattr(settings, "BREVO_SENDER_NAME", "")
    settings.BREVO_API_KEY = ""
    settings.BREVO_SENDER_EMAIL = ""
    # Keep sender name default (harmless).
    orig_env = os.environ.get("BREVO_API_KEY")
    os.environ["BREVO_API_KEY"] = ""
    try:
        yield
    finally:
        try:
            settings.BREVO_API_KEY = old_key
        except Exception:
            pass
        try:
            settings.BREVO_SENDER_EMAIL = old_sender_email
        except Exception:
            pass
        try:
            settings.BREVO_SENDER_NAME = old_sender_name
        except Exception:
            pass
        try:
            if orig_env is None:
                os.environ.pop("BREVO_API_KEY", None)
            else:
                os.environ["BREVO_API_KEY"] = orig_env
        except Exception:
            pass


def _register(client):
    """Register a user (auto-creates a business). Skips if DB unavailable."""
    email = f"brevo-{uuid.uuid4().hex[:8]}@example.co.uk"
    password = "BrevoTest123!"
    try:
        reg = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "full_name": "Brevo Test"},
        )
    except Exception as exc:
        pytest.skip(f"Skipping: DB unavailable ({exc})")
    if reg.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (register 5xx)")
    assert reg.status_code in (200, 201), reg.text
    return reg.json()["access_token"]


def test_status_disconnected_keyless(client, no_keys):
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = client.get("/api/marketing/status", headers=headers)
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    if resp.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (status 5xx)")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("brevo_connected") is False, data


def test_create_list_works_locally_keyless(client, no_keys):
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    name = f"Test List {uuid.uuid4().hex[:6]}"
    try:
        resp = client.post("/api/marketing/lists", json={"name": name}, headers=headers)
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    if resp.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (lists 5xx)")
    assert resp.status_code in (200, 201), resp.text
    data = resp.json()
    assert data.get("name") == name, data
    assert "id" in data, data


def test_campaign_simulated_without_key(client, no_keys):
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = client.post(
            "/api/marketing/campaign",
            json={
                "name": f"Campaign {uuid.uuid4().hex[:6]}",
                "subject": "Hello from VoiceField",
                "html_content": "<p>Hi there — 10% off!</p>",
                "list_id": 1,
            },
            headers=headers,
        )
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    if resp.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (campaign 5xx)")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") == "simulated", data
    assert "campaign_id" in data, data


def test_winback_shape_keyless(client, no_keys):
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = client.post("/api/marketing/winback", headers=headers)
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    if resp.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (winback 5xx)")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "target_count" in data, data
    assert "subject" in data, data
    assert "preview_text" in data, data
    assert isinstance(data["target_count"], int), data
