"""Follow Up Boss (FUB) sync client (Allo).

Docs: https://docs.followupboss.com/ (base https://api.followupboss.com/v1,
HTTP Basic auth where the username is the API key and the password is the
API secret — per FUB's Authentication docs).

Design notes:
  - Credentials (FUB_API_KEY / FUB_API_SECRET) are read from the
    environment AT CALL TIME (never at import), so this module NEVER
    raises on import and missing creds degrade cleanly to manual mode.
  - config.py was intentionally NOT touched (new-files-only constraint);
    the integrator may later add FUB_API_KEY/FUB_API_SECRET to Settings —
    if present they are picked up via getattr, else os.environ is used.
  - No route wiring here. If the integrator wants routes later, mount
    them under /api/fub (e.g. backend/app/routes/fub.py) calling
    push_person / push_appointment and catching RuntimeError to degrade
    to manual mode.

Route degradation pattern (for the integrator):
    try:
        person = await fub.push_person(name, phone, email, tags)
    except RuntimeError as e:  # "Follow Up Boss not configured"
        return {"ok": True, "mode": "manual", "detail": str(e)}
"""

import os
from typing import Dict, List, Optional

import httpx

FUB_BASE = "https://api.followupboss.com/v1"
FUB_TIMEOUT_S = 20.0


def _creds() -> tuple:
    """Read (key, secret) at call time. Never raises."""
    key = ""
    secret = ""
    try:
        from app.core.config import get_settings

        settings = get_settings()
        key = str(getattr(settings, "FUB_API_KEY", "") or "").strip()
        secret = str(getattr(settings, "FUB_API_SECRET", "") or "").strip()
    except Exception:
        key, secret = "", ""
    if not key:
        key = (os.getenv("FUB_API_KEY") or "").strip()
    if not secret:
        secret = (os.getenv("FUB_API_SECRET") or "").strip()
    return key, secret


def is_configured() -> bool:
    """True when an API key is present. Never raises."""
    try:
        key, _ = _creds()
        return bool(key)
    except Exception:
        return False


def _require_creds() -> tuple:
    key, secret = _creds()
    if not key:
        raise RuntimeError("Follow Up Boss not configured")
    return key, secret


def _split_name(name: str) -> Dict[str, str]:
    parts = (name or "").strip().split()
    if not parts:
        return {"firstName": "Unknown", "lastName": ""}
    if len(parts) == 1:
        return {"firstName": parts[0], "lastName": ""}
    return {"firstName": parts[0], "lastName": " ".join(parts[1:])}


async def push_person(
    name: str,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> dict:
    """Create a person in FUB (POST /v1/people).

    Raises RuntimeError("Follow Up Boss not configured") when the API key
    is missing so routes can degrade to manual mode; httpx.HTTPError
    propagates for transport/API failures (callers should catch).
    """
    key, secret = _require_creds()
    payload: Dict[str, object] = _split_name(name)
    payload["stage"] = "Lead"
    payload["source"] = "Allo"
    if phone:
        payload["phones"] = [{"value": phone}]
    if email:
        payload["emails"] = [{"value": email}]
    if tags:
        payload["tags"] = list(tags)
    async with httpx.AsyncClient(timeout=FUB_TIMEOUT_S) as client:
        resp = await client.post(
            f"{FUB_BASE}/people",
            auth=(key, secret),
            json=payload,
        )
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text[:1000]}


async def push_appointment(
    person_id,
    starts_at: str,
    note: str = "",
    ends_at: Optional[str] = None,
    title: str = "Allo appointment",
) -> dict:
    """Create an appointment in FUB (POST /v1/appointments).

    person_id: FUB person id; starts_at/ends_at: UTC ISO-8601 strings
    (e.g. "2026-09-28T14:00:00Z"). Same RuntimeError contract as
    push_person when unconfigured.
    """
    key, secret = _require_creds()
    payload: Dict[str, object] = {
        "title": title,
        "description": note or "",
        "start": starts_at,
        "allDay": False,
        "invitees": [{"personId": person_id}],
    }
    if ends_at:
        payload["end"] = ends_at
    async with httpx.AsyncClient(timeout=FUB_TIMEOUT_S) as client:
        resp = await client.post(
            f"{FUB_BASE}/appointments",
            auth=(key, secret),
            json=payload,
        )
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text[:1000]}
