"""Portfolio template engine (Allo voice/chat demo).

Prefix: /api/agents

All endpoints are PUBLIC (no auth) — demo-grade like the voice_agent
demo endpoints. Per-IP rate limit (20/min) mirrors voice_agent.py's
_demo_allow pattern with a simple module-level dict.

FOLLOW-UP (not implemented to keep this shippable): merge DB overrides
from agent_templates / custom_agents tables on top of the JSON packs in
templates/voice/*.json. For now reads are packs-only.
"""

import base64
import json
import random
import re
import string
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services import llm as llm_service
from app.services.speech import (
    FALLBACK_VOICE,
    MAX_TTS_CHARS,
    PRIMARY_VOICE,
    EdgeTTSVoice,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])

# ---------------------------------------------------------------------------
# Pack loading (import-time + per-request fallback)
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = _BACKEND_DIR / "templates" / "voice"

PACKS: Dict[str, dict] = {}


def _load_packs() -> Dict[str, dict]:
    """Read templates/voice/*.json into {id: pack}. Never raises."""
    packs: Dict[str, dict] = {}
    try:
        if not TEMPLATES_DIR.is_dir():
            return packs
        for path in sorted(TEMPLATES_DIR.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    pack = json.load(fh)
                pid = (pack.get("id") or "").strip()
                if pid and isinstance(pack, dict):
                    packs[pid] = pack
            except Exception:
                continue
    except Exception:
        return packs
    return packs


# Import-time load; per-request fallback re-reads in _get_pack().
PACKS = _load_packs()


def _get_pack(template_id: str) -> Optional[dict]:
    """Return pack or None. Re-reads from disk once if cache misses."""
    tid = (template_id or "").strip()
    if not tid:
        return None
    pack = PACKS.get(tid)
    if pack is not None:
        return pack
    # Fallback: re-read per request (covers packs added after import).
    try:
        fresh = _load_packs()
        if fresh:
            PACKS.update(fresh)
        return PACKS.get(tid)
    except Exception:
        return PACKS.get(tid)


# ---------------------------------------------------------------------------
# Per-IP rate limit — 20/min (mirrors voice_agent.py _demo_allow)
# ---------------------------------------------------------------------------

_RL_WINDOW_S = 60.0
_RL_MAX_CALLS = 20
_rl_hits: Dict[str, List[float]] = {}


def _rl_ip(request: Request) -> str:
    try:
        return (request.client.host if request.client else "unknown") or "unknown"
    except Exception:
        return "unknown"


def _rl_allow(ip: str) -> bool:
    now = time.monotonic()
    hits = [t for t in _rl_hits.get(ip, []) if now - t < _RL_WINDOW_S]
    if len(hits) >= _RL_MAX_CALLS:
        return False
    hits.append(now)
    _rl_hits[ip] = hits
    return True


def _check_rate_limit(request: Request) -> None:
    if not _rl_allow(_rl_ip(request)):
        raise HTTPException(
            status_code=429,
            detail="Rate limit reached — try again in a minute",
        )


# ---------------------------------------------------------------------------
# Chat sessions: session_id -> [{"role": ..., "content": ...}] (cap 20)
# ---------------------------------------------------------------------------

_sessions: Dict[str, List[dict]] = {}


def _get_history(session_id: str) -> List[dict]:
    history = _sessions.get(session_id)
    if history is None:
        history = []
        _sessions[session_id] = history
    return history


def _append_turn(session_id: str, role: str, content: str) -> None:
    history = _get_history(session_id)
    history.append({"role": role, "content": content})
    if len(history) > 20:
        del history[: len(history) - 20]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    template_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = None


class SpeakRequest(BaseModel):
    template_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=1600)


# ---------------------------------------------------------------------------
# Helpers: booking intent, fallback, prompt building
# ---------------------------------------------------------------------------

_BOOK_WORDS_STRONG = ("book", "booking", "appointment", "schedule")
_BOOK_WORDS_SOFT = (
    "visit", "call out", "callout", "engineer", "come round", "come out",
)

_POSTCODE_RE = re.compile(
    r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE
)
_PHONE_RE = re.compile(r"(\+44[\d\s-]{9,}|07[\d\s-]{9,}|020[\d\s-]{7,})")


def _has_booking_intent(message: str) -> bool:
    """Lead-worthy booking intent. Explicit booking verbs (book/appointment/
    schedule) always count; softer trade words (visit/callout/engineer) only
    count with a postcode or phone number; postcode+phone together also count
    (contact details with no verb yet). Price-only questions stay info-stage."""
    t = (message or "").lower()
    try:
        has_postcode = bool(_POSTCODE_RE.search(message or ""))
        has_phone = bool(_PHONE_RE.search(message or ""))
    except Exception:
        has_postcode = has_phone = False
    if any(w in t for w in _BOOK_WORDS_STRONG):
        return True
    if has_postcode and has_phone:
        return True
    if has_postcode or has_phone:
        return any(w in t for w in _BOOK_WORDS_SOFT)
    return False


def _make_lead_reference() -> str:
    rand6 = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"TPL-{rand6}"


def _faq_fallback(pack: dict, message: str) -> str:
    """Keyword fallback: best FAQ answer, else services/prices, else greeting."""
    t = (message or "").lower().strip()
    try:
        faqs = pack.get("faqs") or []
        tokens = re.findall(r"[a-z]{3,}", t)
        best = None
        best_score = 0
        for faq in faqs:
            if not isinstance(faq, dict):
                continue
            hay = f"{faq.get('q', '')} {faq.get('a', '')}".lower()
            score = sum(hay.count(tok) for tok in tokens)
            if score > best_score:
                best_score = score
                best = faq
        if best is not None and best_score > 0:
            return (best.get("a") or "").strip()

        services = pack.get("services") or []
        if any(w in t for w in ("price", "pricing", "cost", "charge", "quote", "how much")):
            lines = []
            for s in services:
                if not isinstance(s, dict):
                    continue
                price = s.get("price_from_gbp")
                price_txt = f"£{price}" if isinstance(price, (int, float)) else "POA"
                lines.append(f"{s.get('name', 'Service')} from {price_txt}")
            if lines:
                return (
                    "Our guide prices: " + "; ".join(lines) + ". "
                    "Want me to book you in? Just share your name, phone and postcode."
                )

        if any(w in t for w in ("hello", "hi", "hey", "good morning",
                                "good afternoon", "good evening")):
            greeting = (pack.get("greeting") or "").strip()
            if greeting:
                return greeting

        if _has_booking_intent(message):
            return (
                "Happy to book that in. Please share your name, phone number, "
                "postcode and a brief description of the problem, and we will "
                "confirm your slot."
            )
    except Exception:
        pass
    return (
        "Thanks for getting in touch. "
        "To book, just share your name, phone number, postcode and "
        "a brief description of the problem."
    )


def _build_prompt(pack: dict, message: str, history: List[dict]) -> str:
    try:
        faqs = pack.get("faqs") or []
        faq_lines = "\n".join(
            f"- Q: {f.get('q', '')}\n  A: {f.get('a', '')}"
            for f in faqs if isinstance(f, dict)
        )
        services = pack.get("services") or []
        svc_lines = "\n".join(
            f"- {s.get('name', '')}: from £{s.get('price_from_gbp')}"
            if isinstance(s.get("price_from_gbp"), (int, float))
            else f"- {s.get('name', '')}: POA"
            for s in services if isinstance(s, dict)
        )
        recent = (history or [])[-4:]
        convo = "\n".join(
            f"{'Customer' if h.get('role') == 'user' else 'Assistant'}: {h.get('content', '')}"
            for h in recent
            if isinstance(h, dict)
        )
        block = (
            f"FAQs:\n{faq_lines}\n"
            f"Services:\n{svc_lines}\n"
            f"Booking fields needed: name, phone, postcode, problem.\n"
        )
        if convo:
            return f"{block}\n{convo}\nCustomer: {message}\nAssistant:"
        return f"{block}\nCustomer: {message}\nAssistant:"
    except Exception:
        return f"Customer: {message}\nAssistant:"


def _quick_replies(pack: dict) -> List[str]:
    """Max 3 short follow-ups for the demo UI."""
    return ["Book a visit", "Get a price", "Emergency help"]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/chat")
async def chat(data: ChatRequest, request: Request):
    """Template chat — LLM first, rule-based fallback. Never 500."""
    try:
        _check_rate_limit(request)
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        pack = _get_pack(data.template_id)
        if pack is None:
            raise HTTPException(status_code=404, detail="Unknown template_id")
        message = (data.message or "").strip()
        if not message:
            raise HTTPException(status_code=400, detail="No message provided")
        session_id = ((data.session_id or "").strip() or uuid.uuid4().hex)
        history = list(_get_history(session_id))

        system = (pack.get("system_prompt") or "").strip()
        prompt = _build_prompt(pack, message, history)

        reply = ""
        try:
            if llm_service.is_configured():
                reply = (await llm_service.complete(
                    prompt,
                    system=system or None,
                    max_tokens=220,
                    temperature=0.3,
                ) or "").strip()
        except Exception:
            reply = ""
        if not reply:
            try:
                reply = _faq_fallback(pack, message)
            except Exception:
                reply = "Thanks for getting in touch. How can I help?"

        booking = _has_booking_intent(message)
        lead_reference = _make_lead_reference() if booking else None
        stage = "booking" if booking else "info"
        if lead_reference and "TPL-" not in reply:
            # Voice callers can't see JSON — speak the reference aloud.
            reply = f"{reply.rstrip()} Your booking reference is {lead_reference}."

        try:
            _append_turn(session_id, "user", message)
            _append_turn(session_id, "assistant", reply)
        except Exception:
            pass

        return {
            "reply": reply,
            "quick_replies": _quick_replies(pack)[:3],
            "stage": stage,
            "lead_reference": lead_reference,
            "template_id": (data.template_id or "").strip(),
        }
    except HTTPException:
        raise
    except Exception as e:
        # Absolute safety net — never 500 on demo endpoints.
        try:
            tid = (data.template_id or "").strip()
        except Exception:
            tid = ""
        return {
            "reply": "Sorry, something went wrong — please share your name, phone and postcode and we will call you back.",
            "quick_replies": ["Book a visit", "Get a price"],
            "stage": "info",
            "lead_reference": None,
            "template_id": tid,
        }


@router.post("/speak")
async def speak(data: SpeakRequest, request: Request):
    """Template TTS via EdgeTTS. Never 500 (TTS failures → 502)."""
    try:
        _check_rate_limit(request)
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        pack = _get_pack(data.template_id)
        if pack is None:
            raise HTTPException(status_code=404, detail="Unknown template_id")
        text = (data.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="No text provided")
        if len(text) > MAX_TTS_CHARS:
            raise HTTPException(
                status_code=400,
                detail=f"Text too long (max {MAX_TTS_CHARS} chars)",
            )
        voice_alias = (pack.get("voice") or "sonia").strip().lower()
        primary = PRIMARY_VOICE if voice_alias == "sonia" else FALLBACK_VOICE
        try:
            provider = EdgeTTSVoice(primary=primary)
            mp3_bytes, voice_used = await provider.speak(text)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"TTS failed: {e}")
        if not mp3_bytes:
            raise HTTPException(status_code=502, detail="TTS returned empty audio")
        return {
            "audio_base64": base64.b64encode(mp3_bytes).decode("ascii"),
            "voice_used": voice_used,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}")


@router.get("/templates")
async def list_templates():
    """Summaries of all packs. Never 500."""
    try:
        packs = PACKS or _load_packs()
        items = []
        for pid in sorted(packs.keys()):
            pack = packs.get(pid) or {}
            try:
                items.append({
                    "id": pid,
                    "kind": pack.get("kind", "voice"),
                    "industry": pack.get("industry", ""),
                    "locale": pack.get("locale", "en-GB"),
                    "name": pack.get("name", ""),
                    "greeting": pack.get("greeting", ""),
                    "voice": pack.get("voice", "sonia"),
                    "brand_color": pack.get("brand_color", ""),
                })
            except Exception:
                continue
        return {"templates": items}
    except Exception:
        return {"templates": []}


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """Full pack JSON + id. Unknown id → 404. Never 500."""
    try:
        pack = _get_pack(template_id)
        if pack is None:
            raise HTTPException(status_code=404, detail="Unknown template_id")
        try:
            out = dict(pack)
        except Exception:
            raise HTTPException(status_code=404, detail="Unknown template_id")
        out["id"] = (template_id or "").strip()
        return out
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Unknown template_id")
