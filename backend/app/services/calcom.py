"""Cal.com v2 adapter: availability slots + bookings for the voice/SMS agents.

Auth: CALCOM_API_KEY (Bearer, `cal_` test / `cal_live_` live) + optional
CALCOM_BASE_URL (default https://api.cal.com, self-hosted override for the
Oracle box later). Every call needs header `cal-api-version: 2026-02-25`.

Design mirrors services/fub.py: credentials read at call time, clean
RuntimeError when unconfigured so routes degrade to manual/hold-ledger mode,
never raises on import. No new dependencies (httpx already required).
"""
from __future__ import annotations

import os
from typing import Any, Optional

_CAL_API_VERSION = "2026-02-25"


def _creds() -> tuple[str, str]:
    base = (os.getenv("CALCOM_BASE_URL", "https://api.cal.com").strip()
            or "https://api.cal.com").rstrip("/")
    key = (os.getenv("CALCOM_API_KEY", "") or "").strip()
    if not key:
        raise RuntimeError("Cal.com not configured (CALCOM_API_KEY missing)")
    return base, key


def is_configured() -> bool:
    try:
        _creds()
        return True
    except RuntimeError:
        return False


def _headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "cal-api-version": _CAL_API_VERSION}


async def get_slots(event_type_id: int, start: str, end: str,
                    time_zone: str = "Europe/London") -> list:
    """Available slots for an event type between ISO datetimes. Returns list."""
    import httpx

    base, key = _creds()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                f"{base}/v2/slots",
                headers=_headers(key),
                params={"eventTypeId": event_type_id, "start": start,
                        "end": end, "timeZone": time_zone},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise RuntimeError(f"Cal.com slots failed: {e}") from e
    if isinstance(data, dict):
        slots = data.get("data", data.get("slots", []))
        return slots if isinstance(slots, list) else []
    return data if isinstance(data, list) else []


async def create_booking(event_type_id: int, start: str, name: str,
                         email: str, phone: Optional[str] = None,
                         notes: str = "",
                         time_zone: str = "Europe/London") -> dict:
    """Book a slot. Returns the booking dict (uid/id). Raises on failure."""
    import httpx

    base, key = _creds()
    attendee: dict[str, Any] = {"name": name, "email": email,
                                "timeZone": time_zone}
    if (phone or "").strip():
        attendee["phoneNumber"] = phone.strip()
    payload: dict[str, Any] = {
        "eventTypeId": event_type_id,
        "start": start,
        "attendee": attendee,
        "timeZone": time_zone,
    }
    if notes.strip():
        payload["description"] = notes.strip()[:500]
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(f"{base}/v2/bookings",
                                  headers=_headers(key), json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise RuntimeError(f"Cal.com booking failed: {e}") from e
    if isinstance(data, dict):
        body = data.get("data", data)
        return body if isinstance(body, dict) else {"result": body}
    return {"result": data}


async def cancel_booking(uid: str, reason: str = "") -> dict:
    """Cancel by booking uid. Returns the response dict."""
    import httpx

    base, key = _creds()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(f"{base}/v2/bookings/{uid}/cancel",
                                  headers=_headers(key),
                                  json={"reason": reason[:500]} if reason else {})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise RuntimeError(f"Cal.com cancel failed: {e}") from e
    return data if isinstance(data, dict) else {"result": data}
