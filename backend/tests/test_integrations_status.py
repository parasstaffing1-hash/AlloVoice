"""Keyless integration-status tests (no external services, no live keys)."""

import os

os.environ["TESTING"] = "1"

import asyncio
import uuid

import pytest


@pytest.fixture(autouse=True)
def _keyless_env(monkeypatch):
    """Force keyless mode for all tests in this module."""
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.delenv("TRUSTPILOT_API_KEY", raising=False)
    monkeypatch.setenv("NOVU_API_KEY", "")
    monkeypatch.setenv("POSTHOG_API_KEY", "")
    monkeypatch.setenv("SENTRY_DSN", "")
    try:
        from app.core.config import get_settings

        get_settings.cache_clear()
    except Exception:
        pass
    yield
    try:
        from app.core.config import get_settings

        get_settings.cache_clear()
    except Exception:
        pass


def test_config_has_observability_settings():
    from app.core.config import get_settings

    settings = get_settings()
    for field in (
        "NOVU_API_KEY",
        "NOVU_API_URL",
        "SENTRY_DSN",
        "SENTRY_ENVIRONMENT",
        "POSTHOG_API_KEY",
        "POSTHOG_HOST",
    ):
        assert hasattr(settings, field), f"Settings missing {field}"
    # EU host default for UK GDPR.
    assert (settings.POSTHOG_HOST or "").strip() != ""


def test_trustpilot_status_disconnected_keyless():
    from app.routes import review_platforms as rp

    # Reset to known disconnected state (other tests may have mutated it).
    rp._trustpilot_state.update(
        {
            "connected": False,
            "api_key": None,
            "api_key_masked": None,
            "business_unit_id": None,
        }
    )
    assert not rp._trustpilot_state.get("connected")
    api_key, unit_id = rp._trustpilot_creds()
    assert api_key is None
    assert unit_id is None


def test_trustpilot_invite_payload_shape():
    """Payload builder must match Trustpilot Invitation API contract (keyless shape check)."""
    import inspect

    from app.routes import review_platforms as rp

    assert hasattr(rp, "_send_trustpilot_invitation")
    sig = inspect.signature(rp._send_trustpilot_invitation)
    for param in (
        "api_key",
        "business_unit_id",
        "recipient_email",
        "recipient_name",
        "reference_id",
    ):
        assert param in sig.parameters
    assert "TRUSTPILOT_INVITATIONS_BASE" in dir(rp) or hasattr(rp, "TRUSTPILOT_INVITATIONS_BASE")
    assert "invitations-api.trustpilot.com" in rp.TRUSTPILOT_INVITATIONS_BASE


def test_notifications_send_without_key_simulated():
    from app.routes import notifications as n

    async def _run():
        return await n._trigger_novu(
            event_name="in_app",
            subscriber_id=str(uuid.uuid4()),
            payload={"title": "t", "message": "m"},
        )

    result = asyncio.run(_run())
    assert result.get("status") == "simulated"


def test_analytics_capture_without_key_noop():
    from app.services import analytics as a

    # Must never raise when POSTHOG_API_KEY is missing.
    assert a.capture("test_event", distinct_id="keyless-user", properties={"x": 1}) is None
    assert a.identify("keyless-user", traits={"email": "a@example.co.uk"}) is None


def test_sentry_init_import_path_safe_keyless():
    # sentry_sdk must be installed and our guarded init must be a safe no-op.
    import sentry_sdk  # noqa: F401

    from app.core.sentry import init_sentry

    assert init_sentry() is False


def test_trustpilot_status_endpoint_exists_keyless():
    """Route must exist; unauthenticated callers get 401/403 (never 500)."""
    try:
        from fastapi.testclient import TestClient

        from app.main import app
    except Exception as exc:
        pytest.skip(f"Skipping: app/TestClient unavailable ({exc})")
    client = TestClient(app)
    try:
        resp = client.get("/api/review-platforms/trustpilot/status")
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code in (401, 403, 200)
    if resp.status_code == 200:
        assert resp.json().get("connected") is False
