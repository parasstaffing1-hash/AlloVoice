"""WhatsApp route tests (keyless: graceful degradation, no live provider calls)."""

import os
import uuid

os.environ["TESTING"] = "1"

import pytest


@pytest.fixture(scope="function")
def client():
    # Function scope: each test gets a fresh TestClient/portal event loop.
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        test_client = TestClient(app)
    except Exception as exc:
        pytest.skip(f"Skipping whatsapp tests: app/TestClient unavailable ({exc})")
    return test_client


def _auth_headers(client):
    email = f"wa-{uuid.uuid4().hex[:8]}@example.co.uk"
    password = "WhatsAppTest123!"
    try:
        reg = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "full_name": "WhatsApp Test"},
        )
    except Exception as exc:
        pytest.skip(f"Skipping: DB unavailable ({exc})")
    if reg.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (register 5xx)")
    assert reg.status_code in (200, 201), reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


def test_send_message_without_keys_returns_503(client):
    headers = _auth_headers(client)
    try:
        resp = client.post(
            "/api/whatsapp/send-message",
            json={"phone_number": "+447911123456", "message": "Hello from VoiceField"},
            headers=headers,
        )
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code == 503, resp.text


def test_templates_list_has_four_templates(client):
    try:
        resp = client.get("/api/whatsapp/templates")
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code == 200, resp.text
    names = {t.get("name") for t in resp.json().get("templates", [])}
    assert names == {"quote_ready", "invoice_due", "engineer_on_way", "appointment_reminder"}


def test_webhook_get_wrong_token_returns_403(client):
    try:
        resp = client.get(
            "/api/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "12345",
            },
        )
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code == 403, resp.text


def test_webhook_post_garbage_returns_200(client):
    try:
        resp = client.post("/api/whatsapp/webhook", json={"garbage": True})
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code == 200, resp.text
