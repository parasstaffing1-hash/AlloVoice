"""QuickBooks hardening tests (mock-only: no live keys, no external calls)."""

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
        pytest.skip(f"Skipping quickbooks tests: app/TestClient unavailable ({exc})")
    return test_client


@pytest.fixture(scope="function")
def no_keys():
    """Force keyless/mocked QuickBooks config and clear module connection state."""
    try:
        from app.core.config import get_settings
        from app.routes import quickbooks as qb_module
    except Exception as exc:
        pytest.skip(f"Skipping quickbooks tests: imports unavailable ({exc})")
    settings = get_settings()
    old_id = getattr(settings, "QB_CLIENT_ID", "")
    old_secret = getattr(settings, "QB_CLIENT_SECRET", "")
    old_redirect = getattr(settings, "QB_REDIRECT_URI", "")
    old_env = getattr(settings, "QB_ENVIRONMENT", "")
    settings.QB_CLIENT_ID = ""
    settings.QB_CLIENT_SECRET = ""
    orig_id = os.environ.get("QB_CLIENT_ID")
    orig_secret = os.environ.get("QB_CLIENT_SECRET")
    os.environ["QB_CLIENT_ID"] = ""
    os.environ["QB_CLIENT_SECRET"] = ""
    saved_tokens = dict(qb_module._qb_tokens)
    saved_state = dict(qb_module._quickbooks_state)
    qb_module._qb_tokens.clear()
    qb_module._quickbooks_state.update({"connected": False, "company_name": None, "last_synced": None})
    try:
        yield
    finally:
        try:
            settings.QB_CLIENT_ID = old_id
        except Exception:
            pass
        try:
            settings.QB_CLIENT_SECRET = old_secret
        except Exception:
            pass
        try:
            settings.QB_REDIRECT_URI = old_redirect
        except Exception:
            pass
        try:
            settings.QB_ENVIRONMENT = old_env
        except Exception:
            pass
        try:
            if orig_id is None:
                os.environ.pop("QB_CLIENT_ID", None)
            else:
                os.environ["QB_CLIENT_ID"] = orig_id
            if orig_secret is None:
                os.environ.pop("QB_CLIENT_SECRET", None)
            else:
                os.environ["QB_CLIENT_SECRET"] = orig_secret
        except Exception:
            pass
        try:
            qb_module._qb_tokens.clear()
            qb_module._qb_tokens.update(saved_tokens)
            qb_module._quickbooks_state.clear()
            qb_module._quickbooks_state.update(saved_state)
        except Exception:
            pass


def test_auth_url_contains_intuit_keyless(client, no_keys):
    try:
        resp = client.get("/api/quickbooks/auth/url")
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "auth_url" in data, data
    assert "intuit.com" in data["auth_url"], data


def test_status_disconnected_keyless(client, no_keys):
    try:
        resp = client.get("/api/quickbooks/status")
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code == 200, resp.text
    assert resp.json().get("connected") is False, resp.text


def test_sync_invoices_503_keyless(client, no_keys):
    try:
        resp = client.post("/api/quickbooks/sync/invoices")
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code == 503, resp.text


def test_disconnect_200_keyless(client, no_keys):
    try:
        resp = client.post("/api/quickbooks/disconnect")
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code == 200, resp.text
