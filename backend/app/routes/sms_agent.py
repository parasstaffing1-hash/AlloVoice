"""SMS conversation agent (Allo).

Prefix: /api/sms-agent

Twilio inbound SMS webhook + deterministic SMS brain over the
`voice-real-estate-uk` pack. All endpoints are PUBLIC (no auth) — Twilio
webhooks cannot carry our JWT; this mirrors routes/telephony.py's webhook
style (form fields, TwiML responses, no auth on the webhook).

Flow (POST /inbound, form fields From/Body):
  1. normalize sender (best-effort E.164 via app.services.phone, falling
     back to the raw stripped value so Twilio test numbers still work);
  2. STOP / opt-out exact-word match -> record opt-out (in-memory set +
     best-effort gdpr_consents row) and reply the unsubscribed TwiML;
  3. consent gate: previously opted-out senders get the unsubscribed
     message (best-effort DB lookup, failures = allow);
  4. quiet hours (US Eastern 21:00-08:00) -> log as queued, empty TwiML;
  5. deterministic brain: _faq_scores / _has_booking_intent / guards /
     _make_lead_reference imported from app.routes.agents (never copied),
     answered against backend/templates/voice/real-estate.json loaded
     directly from disk (no DB), no LLM calls;
  6. reply TwiML <Message> truncated to <=320 chars; best-effort sms_logs.

Never 500s: every failure path returns a (possibly empty) TwiML
<Response/>. No new dependencies, no new DB tables, no LLM calls.

Schema notes / stubbed bits:
  * gdpr_consents.user_id is NOT NULL and has no phone column, so a sender
    with no matching users.phone row cannot be persisted there — the
    opt-out is still honoured via the in-memory _OPTED_OUT_NUMBERS set
    (plus a best-effort row whenever a matching user exists).
  * sms_logs.business_id is NOT NULL and the webhook carries no business
    context, so log writes use business_id=None and may be rejected by
    the DB — swallowed as best-effort (same pattern as routes/sms.py).
  * Twilio request-signature validation is intentionally NOT enforced
    (the spec'd flow has no shared-secret step); the integrator can add
    it later following routes/telephony.py::_valid_twilio_signature.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.models import GdprConsent, SmsLog, User
from app.routes.agents import (
    _FAQ_SHORT_CIRCUIT_SCORE,
    _ensure_price_answer,
    _ensure_redirect,
    _ensure_safety_reply,
    _faq_fallback,
    _faq_scores,
    _has_booking_intent,
    _make_lead_reference,
)
from app.services.phone import normalize_phone

router = APIRouter(prefix="/api/sms-agent", tags=["sms-agent"])

_MAX_SMS_CHARS = 320
_PACK_ID = "voice-real-estate-uk"

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PACK_PATH = _BACKEND_DIR / "templates" / "voice" / "real-estate.json"

_UNSUBSCRIBED_MESSAGE = (
    "You are unsubscribed and will receive no further messages from Allo."
)

_STOP_WORDS = frozenset({"stop", "stopall", "unsubscribe", "cancel", "end", "quit"})

# In-memory opt-out cache: phone -> opted out. Always written on STOP so
# the consent gate works even when the sender has no users row to persist
# against (see module docstring). Best-effort only; resets on restart.
_OPTED_OUT_NUMBERS: set = set()


# ---------------------------------------------------------------------------
# Pack loading (import-time + per-request fallback, disk only, no DB)
# ---------------------------------------------------------------------------


def _load_pack_from_disk() -> dict:
    try:
        with open(_PACK_PATH, "r", encoding="utf-8") as fh:
            pack = json.load(fh)
        if isinstance(pack, dict):
            return pack
    except Exception:
        pass
    return {}


_PACK: dict = _load_pack_from_disk()


def _get_pack() -> dict:
    """Return the real-estate pack, re-reading from disk if cache is empty."""
    global _PACK
    if _PACK:
        return _PACK
    try:
        fresh = _load_pack_from_disk()
        if fresh:
            _PACK = fresh
    except Exception:
        pass
    return _PACK


# ---------------------------------------------------------------------------
# TwiML (plain string templates + escaping, no twilio lib)
# ---------------------------------------------------------------------------


def _twiml(message: Optional[str]) -> Response:
    try:
        text = (message or "").strip()
    except Exception:
        text = ""
    if text:
        # Truncate BEFORE escaping: cutting an escaped entity (e.g. "&amp;")
        # mid-sequence would emit malformed XML that Twilio rejects.
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?><Response><Message>'
            + _xml_escape(text[:_MAX_SMS_CHARS], {'"': "&quot;"})
            + "</Message></Response>"
        )
    else:
        xml = '<?xml version="1.0" encoding="UTF-8"?><Response/>'
    return Response(content=xml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Helpers: sender, STOP match, quiet hours
# ---------------------------------------------------------------------------


def _normalize_sender(raw: Optional[str]) -> str:
    """Best-effort E.164; falls back to the raw stripped value. Never raises."""
    try:
        s = (raw or "").strip()
    except Exception:
        return ""
    if not s:
        return ""
    try:
        return normalize_phone(s)
    except Exception:
        return s


def _is_opt_out(body: Optional[str]) -> bool:
    """Exact-word STOP match (case-insensitive). Never raises.

    The whole trimmed body must be one keyword; "cancel my viewing" must
    NOT opt the sender out, so substring/word-in-sentence matching is
    deliberately avoided. Trailing punctuation ("STOP!") is tolerated.
    """
    try:
        text = (body or "").strip().lower().strip(" \t\n\r.!?,;:")
        return text in _STOP_WORDS
    except Exception:
        return False


def _current_et_hour() -> Optional[int]:
    """Current hour in America/New_York, or None if tz data is unavailable."""
    try:
        from zoneinfo import ZoneInfo

        try:
            tz = ZoneInfo("America/New_York")
        except Exception:
            return None
        return datetime.now(tz).hour
    except Exception:
        return None


def _is_quiet_hour(hour: int) -> bool:
    """True for 21:00-08:00 US Eastern. Never raises."""
    try:
        h = int(hour)
    except Exception:
        return False
    return h >= 21 or h < 8


def _in_quiet_hours() -> bool:
    """Quiet-hours gate. Unknown tz -> False (fail open). Never raises."""
    try:
        hour = _current_et_hour()
        if hour is None:
            return False
        return _is_quiet_hour(hour)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Best-effort DB helpers (never raise; DB failures = allow/skip)
# ---------------------------------------------------------------------------


async def _record_opt_out(sender: str, request: Request) -> None:
    """Persist an SMS opt-out. Always updates the in-memory set; the
    gdpr_consents row is written only when a matching users row exists."""
    try:
        _OPTED_OUT_NUMBERS.add(sender)
    except Exception:
        pass
    try:
        try:
            ip = request.client.host if getattr(request, "client", None) else None
        except Exception:
            ip = None
        try:
            ua = request.headers.get("user-agent") if request.headers else None
        except Exception:
            ua = None
        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(
                    select(User).where(User.phone == sender)
                )
                user = result.scalars().first()
                if user is None:
                    return
                session.add(
                    GdprConsent(
                        user_id=user.id,
                        consent_type="sms",
                        granted=False,
                        ip_address=ip,
                        user_agent=ua,
                    )
                )
                await session.commit()
            except Exception:
                try:
                    await session.rollback()
                except Exception:
                    pass
    except Exception:
        pass


async def _sender_opted_out(sender: str) -> bool:
    """True if the sender previously opted out. Failures = False (allow)."""
    try:
        if sender in _OPTED_OUT_NUMBERS:
            return True
    except Exception:
        pass
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User.id).where(User.phone == sender)
            )
            user_ids = list(result.scalars().all())
            if not user_ids:
                return False
            latest = await session.execute(
                select(GdprConsent)
                .where(
                    GdprConsent.user_id.in_(user_ids),
                    GdprConsent.consent_type.ilike("%sms%"),
                )
                .order_by(GdprConsent.created_at.desc())
                .limit(1)
            )
            row = latest.scalars().first()
            if row is not None and row.granted is False:
                try:
                    _OPTED_OUT_NUMBERS.add(sender)
                except Exception:
                    pass
                return True
            return False
    except Exception:
        return False


async def _log_sms(to_phone: str, message: str, status: str) -> None:
    """Best-effort sms_logs row. Never raises (business_id=None may be
    rejected by the DB — swallowed by design)."""
    try:
        async with AsyncSessionLocal() as session:
            try:
                session.add(
                    SmsLog(
                        business_id=None,
                        to_phone=(to_phone or "")[:20],
                        message=(message or "")[:1600],
                        status=(status or "queued")[:20],
                    )
                )
                await session.commit()
            except Exception:
                try:
                    await session.rollback()
                except Exception:
                    pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Deterministic brain (imported helpers only, no LLM)
# ---------------------------------------------------------------------------


def _truncate(text: str, limit: int) -> str:
    try:
        t = (text or "").strip()
    except Exception:
        return ""
    if len(t) <= limit:
        return t
    if limit <= 3:
        return t[:limit]
    return t[: limit - 3].rstrip() + "..."


def _brain_answer(pack: dict, body: str) -> str:
    """FAQ short-circuit, else pack fallback, then guards + booking ref."""
    try:
        message = (body or "").strip()
    except Exception:
        message = ""
    reply = ""
    try:
        scored = _faq_scores(pack or {}, message)
        if scored and scored[0][0] >= _FAQ_SHORT_CIRCUIT_SCORE:
            reply = ((scored[0][1] or {}).get("a") or "").strip()
    except Exception:
        reply = ""
    if not reply:
        try:
            reply = (_faq_fallback(pack or {}, message) or "").strip()
        except Exception:
            reply = ""
    if not reply:
        try:
            reply = ((pack or {}).get("greeting") or "").strip()
        except Exception:
            reply = ""
    if not reply:
        reply = "Thanks for getting in touch. How can I help?"

    try:
        reply = _ensure_safety_reply(reply, message)
    except Exception:
        pass
    try:
        reply = _ensure_price_answer(reply, message, pack or {})
    except Exception:
        pass
    try:
        reply = _ensure_redirect(reply, message)
    except Exception:
        pass

    try:
        if _has_booking_intent(message):
            ref = _make_lead_reference()
            if ref and "TPL-" not in (reply or ""):
                suffix = f" Your booking reference is {ref}."
                base = _truncate(reply, _MAX_SMS_CHARS - len(suffix))
                reply = (base + suffix).strip()
    except Exception:
        pass

    return _truncate(reply, _MAX_SMS_CHARS)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health")
async def health():
    """Liveness + consent-gate flag. Never 500."""
    try:
        return {"status": "ok", "consent_gate": True}
    except Exception:
        return {"status": "ok", "consent_gate": True}


@router.post("/inbound")
async def inbound(request: Request):
    """Twilio inbound SMS webhook (form fields From/Body). Never 500 —
    every failure path returns a (possibly empty) TwiML <Response/>."""
    try:
        try:
            form = await request.form()
        except Exception:
            form = {}
        try:
            raw_from = str(form.get("From") or "")
        except Exception:
            raw_from = ""
        try:
            body = str(form.get("Body") or "")
        except Exception:
            body = ""

        sender = _normalize_sender(raw_from)
        if not sender:
            return _twiml(None)

        # (2) STOP / opt-out.
        try:
            is_stop = _is_opt_out(body)
        except Exception:
            is_stop = False
        if is_stop:
            try:
                await _record_opt_out(sender, request)
            except Exception:
                pass
            try:
                await _log_sms(sender, f"IN: {body} | OUT: {_UNSUBSCRIBED_MESSAGE}"[:1600], "opt_out")
            except Exception:
                pass
            return _twiml(_UNSUBSCRIBED_MESSAGE)

        # (3) Consent gate (failures = allow).
        try:
            opted_out = await _sender_opted_out(sender)
        except Exception:
            opted_out = False
        if opted_out:
            return _twiml(_UNSUBSCRIBED_MESSAGE)

        # (4) Quiet hours: queue silently, reply nothing.
        try:
            quiet = _in_quiet_hours()
        except Exception:
            quiet = False
        if quiet:
            try:
                await _log_sms(sender, f"IN: {body}"[:1600], "queued")
            except Exception:
                pass
            return _twiml(None)

        # (5) Deterministic brain over the real-estate pack.
        try:
            pack = _get_pack()
        except Exception:
            pack = {}
        try:
            reply = _brain_answer(pack or {}, body)
        except Exception:
            reply = "Thanks for getting in touch. How can I help?"
        if not (reply or "").strip():
            reply = "Thanks for getting in touch. How can I help?"

        # (6) Log + reply (<=320 chars enforced inside _brain_answer).
        try:
            await _log_sms(sender, f"IN: {body} | OUT: {reply}"[:1600], "received")
        except Exception:
            pass
        return _twiml(reply)
    except Exception:
        try:
            return _twiml(None)
        except Exception:
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response/>',
                media_type="application/xml",
            )
