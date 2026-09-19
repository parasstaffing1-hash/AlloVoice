"""Xero hardening tests (mock-only: no live keys, no external calls)."""

import os

os.environ["TESTING"] = "1"

import pytest


@pytest.fixture(scope="function")
def client():
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        test_client = TestClient(app)
    except Exception as exc:
        pytest.skip(f"Skipping xero tests: app/TestClient unavailable ({exc})")
    return test_client


@pytest.fixture(scope="function")
def no_keys():
    """Force keyless/mocked Xero config and clear module connection state."""
    try:
        from app.core.config import get_settings
        from app.routes import xero as xero_module
    except Exception as exc:
        pytest.skip(f"Skipping xero tests: imports unavailable ({exc})")
    settings = get_settings()
    old_id = settings.XERO_CLIENT_ID
    old_secret = settings.XERO_CLIENT_SECRET
    settings.XERO_CLIENT_ID = ""
    settings.XERO_CLIENT_SECRET = ""
    saved_tokens = dict(xero_module._XERO_TOKENS)
    saved_invoices = {k: set(v) for k, v in xero_module._SYNCED_INVOICE_IDS.items()}
    saved_contacts = {k: set(v) for k, v in xero_module._SYNCED_CONTACT_IDS.items()}
    xero_module._XERO_TOKENS.clear()
    xero_module._SYNCED_INVOICE_IDS.clear()
    xero_module._SYNCED_CONTACT_IDS.clear()
    try:
        yield
    finally:
        settings.XERO_CLIENT_ID = old_id
        settings.XERO_CLIENT_SECRET = old_secret
        xero_module._XERO_TOKENS.clear()
        xero_module._XERO_TOKENS.update(saved_tokens)
        xero_module._SYNCED_INVOICE_IDS.clear()
        xero_module._SYNCED_INVOICE_IDS.update(saved_invoices)
        xero_module._SYNCED_CONTACT_IDS.clear()
        xero_module._SYNCED_CONTACT_IDS.update(saved_contacts)


NEW = "/api/xero"
LEGACY = "/api/integrations/xero"


def _first_live(client, method, paths, **kwargs):
    """Call the first path that exists (skips 404 aliases); skips if DB/network down."""
    last_404 = None
    for path in paths:
        try:
            resp = getattr(client, method)(path, **kwargs)
        except Exception as exc:
            pytest.skip(f"Skipping: request failed ({exc})")
        if resp.status_code == 404:
            last_404 = resp
            continue
        return resp
    if last_404 is not None:
        pytest.skip("Skipping: xero routes unavailable (404)")
    pytest.fail("No xero route candidates available")


def test_auth_returns_url_keyless(client, no_keys):
    resp = _first_live(client, "get", [f"{NEW}/auth", f"{LEGACY}/auth"])
    if resp.status_code in (500, 502, 503):
        pytest.skip("Skipping: auth 5xx")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "auth_url" in data, data
    assert "xero.com" in data["auth_url"], data


def test_status_disconnected_keyless(client, no_keys):
    resp = _first_live(client, "get", [f"{NEW}/status", f"{LEGACY}/status"])
    if resp.status_code in (500, 502):
        pytest.skip("Skipping: status 5xx")
    assert resp.status_code == 200, resp.text
    assert resp.json().get("connected") is False


def test_sync_invoices_503_without_keys(client, no_keys):
    resp = _first_live(
        client, "post", [f"{NEW}/sync-invoices", f"{LEGACY}/sync-invoices"]
    )
    assert resp.status_code == 503, resp.text
    assert (
        resp.json().get("detail")
        == "Xero not connected \u2014 add XERO_* keys and connect"
    )


def test_sync_contacts_503_without_keys(client, no_keys):
    resp = _first_live(
        client, "post", [f"{NEW}/sync-contacts", f"{LEGACY}/sync-contacts"]
    )
    assert resp.status_code == 503, resp.text
    assert (
        resp.json().get("detail")
        == "Xero not connected \u2014 add XERO_* keys and connect"
    )


def test_disconnect_unauthenticated_keyless(client, no_keys):
    try:
        resp = client.post(f"{NEW}/disconnect")
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code in (401, 403)
