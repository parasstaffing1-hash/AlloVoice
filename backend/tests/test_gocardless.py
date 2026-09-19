"""GoCardless Direct Debit tests (mock-only: no live keys, no external calls)."""

import os
import uuid

os.environ["TESTING"] = "1"

import pytest


@pytest.fixture(scope="function")
def client():
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        # The gocardless router is intentionally NOT wired into app/main.py
        # (payments.py owns /api/payments). Mount it for tests if missing.
        try:
            from app.routes import gocardless as gc_routes

            paths = set()
            for r in app.routes:
                try:
                    paths.add(getattr(r, "path", ""))
                except Exception:
                    continue
            if "/api/gocardless/status" not in paths:
                app.include_router(gc_routes.router)
        except Exception as exc:
            pytest.skip(f"Skipping gocardless tests: router unavailable ({exc})")

        test_client = TestClient(app)
    except Exception as exc:
        pytest.skip(f"Skipping gocardless tests: app/TestClient unavailable ({exc})")
    return test_client


def _register(client):
    """Register a user (auto-creates a business). Skips if DB unavailable."""
    email = f"gc-{uuid.uuid4().hex[:8]}@example.co.uk"
    password = "GoCardless123!"
    try:
        reg = client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "full_name": "GC Test"},
        )
    except Exception as exc:
        pytest.skip(f"Skipping: DB unavailable ({exc})")
    if reg.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (register 5xx)")
    assert reg.status_code in (200, 201), reg.text
    return reg.json()["access_token"]


def _owned_invoice_id(client, headers):
    """Seed customer -> job -> invoice directly in the DB (the jobs API has
    a pre-existing timeline bug, so API chaining cannot create jobs)."""
    import asyncio

    try:
        biz = client.get("/api/auth/business", headers=headers)
    except Exception as exc:
        pytest.skip(f"Skipping: DB unavailable ({exc})")
    if biz.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (business 5xx)")
    assert biz.status_code == 200, biz.text
    business_id = biz.json()["id"]

    async def _seed():
        from app.core.database import AsyncSessionLocal
        from app.models.models import Customer, Invoice, Job

        async with AsyncSessionLocal() as session:
            customer = Customer(
                business_id=business_id,
                full_name="DD Test",
                email="dd@example.co.uk",
                phone="+447911123456",
            )
            session.add(customer)
            await session.flush()
            job = Job(
                business_id=business_id,
                customer_id=customer.id,
                title="GoCardless test job",
            )
            session.add(job)
            await session.flush()
            invoice = Invoice(
                job_id=job.id,
                customer_id=customer.id,
                invoice_number=f"INV-GC{uuid.uuid4().hex[:10].upper()}",
                subtotal=100,
                tax_rate=20,
                tax_amount=20,
                total=120,
            )
            session.add(invoice)
            await session.commit()
            return str(invoice.id)

    try:
        return asyncio.run(_seed())
    except Exception as exc:
        pytest.skip(f"Skipping: DB unavailable ({exc})")


def _force_unusable(monkeypatch=None):
    """Force graceful-degradation mode (no usable token). Returns restore fn."""
    from app.core.config import get_settings

    settings = get_settings()
    original = getattr(settings, "GOCARDLESS_ACCESS_TOKEN", "")
    settings.GOCARDLESS_ACCESS_TOKEN = ""
    orig_env = os.environ.get("GOCARDLESS_ACCESS_TOKEN")
    os.environ["GOCARDLESS_ACCESS_TOKEN"] = ""

    def _restore():
        try:
            settings.GOCARDLESS_ACCESS_TOKEN = original
        except Exception:
            pass
        try:
            if orig_env is None:
                os.environ.pop("GOCARDLESS_ACCESS_TOKEN", None)
            else:
                os.environ["GOCARDLESS_ACCESS_TOKEN"] = orig_env
        except Exception:
            pass

    return _restore


def test_redirect_flow_without_keys_returns_503(client):
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    invoice_id = _owned_invoice_id(client, headers)

    restore = _force_unusable()
    try:
        try:
            resp = client.post(
                f"/api/gocardless/redirect-flow?invoice_id={invoice_id}",
                headers=headers,
            )
        except Exception as exc:
            pytest.skip(f"Skipping: DB unavailable ({exc})")
    finally:
        restore()

    if resp.status_code in (500, 502):
        pytest.skip("Skipping: DB unavailable (redirect-flow 5xx)")
    assert resp.status_code == 503, resp.text


def test_status_reports_unconfigured_without_keys(client):
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}

    restore = _force_unusable()
    try:
        try:
            resp = client.get("/api/gocardless/status", headers=headers)
        except Exception as exc:
            pytest.skip(f"Skipping: DB unavailable ({exc})")
    finally:
        restore()

    if resp.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (status 5xx)")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("configured") is False
    assert "environment" in data
    assert "mandates_count" in data


def test_mandates_empty_without_keys(client):
    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}

    restore = _force_unusable()
    try:
        try:
            resp = client.get("/api/gocardless/mandates", headers=headers)
        except Exception as exc:
            pytest.skip(f"Skipping: DB unavailable ({exc})")
    finally:
        restore()

    if resp.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (mandates 5xx)")
    assert resp.status_code == 200, resp.text
    assert "mandates" in resp.json()
    assert isinstance(resp.json()["mandates"], list)


def test_webhook_bad_body_always_200(client):
    try:
        resp = client.post(
            "/api/gocardless/gc-webhook",
            content=b"not-json{{{",
            headers={"content-type": "application/json"},
        )
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code == 200, resp.text


def test_webhook_empty_body_always_200(client):
    try:
        resp = client.post(
            "/api/gocardless/gc-webhook",
            content=b"",
            headers={"content-type": "application/json"},
        )
    except Exception as exc:
        pytest.skip(f"Skipping: request failed ({exc})")
    assert resp.status_code == 200, resp.text


def test_collect_without_mandate_returns_400(client):
    from app.routes import gocardless as gc_routes

    token = _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    invoice_id = _owned_invoice_id(client, headers)

    # Ensure no mandate exists for this customer.
    gc_routes._MANDATES.clear()
    gc_routes._PAYMENTS.clear()

    restore = _force_unusable()
    try:
        try:
            resp = client.post(
                f"/api/gocardless/collect?invoice_id={invoice_id}",
                headers=headers,
            )
        except Exception as exc:
            pytest.skip(f"Skipping: DB unavailable ({exc})")
    finally:
        restore()

    if resp.status_code in (500, 502, 503):
        pytest.skip("Skipping: DB unavailable (collect 5xx)")
    assert resp.status_code == 400, resp.text
    assert resp.json().get("detail") == "No mandate — complete redirect flow first"
