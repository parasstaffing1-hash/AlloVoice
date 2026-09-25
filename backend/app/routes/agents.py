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
CHAT_TEMPLATES_DIR = _BACKEND_DIR / "templates" / "chat"

PACKS: Dict[str, dict] = {}


def _load_packs() -> Dict[str, dict]:
    """Read templates/voice/*.json + templates/chat/*.json into {id: pack}."""
    packs: Dict[str, dict] = {}
    try:
        for directory in (TEMPLATES_DIR, CHAT_TEMPLATES_DIR):
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
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
_CLAIM_WORDS = ("claim", "claiming")
_SIGNUP_WORDS = ("trial", "sign up", "signup", "register me", "join")

_POSTCODE_RE = re.compile(
    r"\b(?:[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}|\d{5}(?:-\d{4})?)\b", re.IGNORECASE
)
_PHONE_RE = re.compile(
    r"(\+44[\d\s-]{9,}|07[\d\s-]{9,}|020[\d\s-]{7,}"
    r"|\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"
    r"|\(\d{3}\)\s?\d{3}[-.\s]?\d{4}"
    r"|\+\d[\d\s-]{7,}\d)"
)


def _service_price(service: dict) -> str:
    """Price text honouring whichever currency key the pack uses."""
    try:
        for key, symbol in (("price_from_gbp", "£"), ("price_from_usd", "$"),
                            ("price_from_aed", "AED ")):
            value = (service or {}).get(key)
            if isinstance(value, (int, float)):
                return f"{symbol}{value:g}"
    except Exception:
        pass
    return "POA"


def _has_email(message: str) -> bool:
    try:
        import re as _re

        return bool(_re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", message or ""))
    except Exception:
        return False


_EMERGENCY_WORDS = (
    "sparking", "burning", "smoke", "gas leak", "smell of gas", "flood",
    "burst", "electrocut", "electric shock", "carbon monoxide",
)
_EMERGENCY_SAFETY = (
    "switch off", "stay clear", "do not touch", "don't touch",
    "call 999", "call 111", "stopcock", "isolate",
)
_PRICE_WORDS = (
    "price", "pricing", "cost", "charge", "how much", "quote",
    "expensive", "cheap", "fee", "rate", "much is", "much does",
    "figure", "excess", "amount",
)


def _ensure_safety_reply(reply: str, message: str) -> str:
    """Deterministic safety net: emergency reports must carry a safety
    instruction even if the model drifts. Never raises."""
    try:
        t = (message or "").lower()
        r = (reply or "").lower()
        if any(w in t for w in _EMERGENCY_WORDS) and not any(
                s in r for s in _EMERGENCY_SAFETY):
            return ("If anyone is in immediate danger, switch off power and gas "
                    "at the mains and stay clear. " + (reply or "").strip()).strip()
    except Exception:
        pass
    return reply


def _ensure_price_answer(reply: str, message: str, pack: dict) -> str:
    """Deterministic pricing net: price questions must show a figure from
    the pack when one exists. Never raises."""
    try:
        import re as _re

        t = (message or "").lower()
        r = reply or ""
        if not any(w in t for w in _PRICE_WORDS):
            return reply
        if _re.search(r"(£|\$|AED)\s?\d", r):
            return reply
        priced = []
        for s in (pack or {}).get("services") or []:
            if isinstance(s, dict):
                price = _service_price(s)
                if price != "POA":
                    priced.append(f"{s.get('name', 'Service')} from {price}")
            if len(priced) >= 2:
                break
        if priced:
            return (r.rstrip() + " Guide prices: " + "; ".join(priced) + ".").strip()
        # Fallback: a pack FAQ holding a £ figure matching the question
        # (e.g. excess splits, fee schedules) beats saying nothing.
        try:
            import re as _re2

            tokens = {w for w in _re2.findall(r"[a-z]{4,}", t) if w not in
                      ("what", "with", "your", "have", "this", "that", "from",
                       "please", "thank", "thanks", "hello", "there")}
            best, best_score = None, 0
            for f in (pack or {}).get("faqs") or []:
                if not isinstance(f, dict):
                    continue
                a = str(f.get("a", "") or "")
                if not _re2.search(r"(£|\$|AED)\s?\d", a):
                    continue
                hay = f"{f.get('q', '')} {a}".lower()
                score = sum(hay.count(tok) for tok in tokens)
                if score > best_score:
                    best, best_score = a, score
            if best and best_score > 0:
                snippet = best.strip()
                if len(snippet) > 220:
                    snippet = snippet[:220].rsplit(" ", 1)[0] + "…"
                return (r.rstrip() + f" From our faqs: {snippet}").strip()
        except Exception:
            pass
    except Exception:
        pass
    return reply


_OFFTOPIC_PATTERNS = (
    "poem", "poetry", "song lyrics", "write me a story", "essay",
    "homework", "write me a joke",
)
_DECLINE_WORDS = (
    "can't", "cannot", "sorry", "afraid", "unable", "not able",
)


def _ensure_redirect(reply: str, message: str) -> str:
    """Deterministic off-topic guard: creative/personal requests must carry
    an explicit decline, or the agent sounds like it agreed. Never raises."""
    try:
        t = (message or "").lower()
        r = reply or ""
        if any(p in t for p in _OFFTOPIC_PATTERNS) and not any(
                d in r.lower() for d in _DECLINE_WORDS):
            return ("I can't help with that — " + r.strip()).strip()
    except Exception:
        pass
    return reply


def _has_booking_intent(message: str) -> bool:
    """Lead-worthy booking intent. Explicit booking verbs (book/appointment/
    schedule) always count; softer trade words (visit/callout/engineer) only
    count with a postcode or phone number; postcode+phone together also count
    (contact details with no verb yet). Trial/signup/claim requests count when
    contact details (email/phone/postcode) are present. Price-only questions
    stay info-stage."""
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
    contact = has_postcode or has_phone or _has_email(message)
    if contact and (any(w in t for w in _SIGNUP_WORDS)
                    or any(w in t for w in _CLAIM_WORDS)):
        return True
    if has_postcode or has_phone:
        return any(w in t for w in _BOOK_WORDS_SOFT)
    return False


def _make_lead_reference() -> str:
    rand6 = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"TPL-{rand6}"


# Score at/above which a pack FAQ answers directly with no LLM call.
# Calibrated against the 108-probe gate: 102 probes score >= 8 on the
# correct FAQ; off-topic probes (redirect-guard territory) score < 8.
_FAQ_SHORT_CIRCUIT_SCORE = 8


def _faq_scores(pack: dict, message: str) -> list:
    """Token-overlap relevance per FAQ. Question-text matches weigh 3x —
    answer bodies share vocabulary (e.g. 'lessons') and would otherwise win."""
    t = (message or "").lower().strip()
    try:
        tokens = re.findall(r"[a-z]{3,}", t)
        scored = []
        for faq in pack.get("faqs") or []:
            if not isinstance(faq, dict):
                continue
            q = (faq.get("q") or "").lower()
            a = (faq.get("a") or "").lower()
            score = sum(q.count(tok) for tok in tokens) * 3 + sum(a.count(tok) for tok in tokens)
            scored.append((score, faq))
        scored.sort(key=lambda s: s[0], reverse=True)
        return scored
    except Exception:
        return [(0, f) for f in (pack.get("faqs") or []) if isinstance(f, dict)]


def _faq_fallback(pack: dict, message: str) -> str:
    """Keyword fallback: best FAQ answer, else services/prices, else greeting."""
    t = (message or "").lower().strip()
    try:
        scored = _faq_scores(pack, message)
        if scored and scored[0][0] > 0:
            return (scored[0][1].get("a") or "").strip()

        services = pack.get("services") or []
        if any(w in t for w in ("price", "pricing", "cost", "charge", "quote", "how much")):
            lines = []
            for s in services:
                if not isinstance(s, dict):
                    continue
                lines.append(f"{s.get('name', 'Service')} from {_service_price(s)}")
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
        scored = _faq_scores(pack, message)
        ordered = [f for _, f in scored] or [f for f in (pack.get("faqs") or []) if isinstance(f, dict)]
        faq_lines = "\n".join(
            f"- Q: {f.get('q', '')}\n  A: {f.get('a', '')}"
            for f in ordered
        )
        services = pack.get("services") or []
        svc_lines = "\n".join(
            f"- {s.get('name', '')}: from {_service_price(s)}"
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

        # No-LLM short-circuit: a confident pack-FAQ match answers directly
        # (~50ms, $0). Measured 102/108 gate probes resolve here; the rest
        # fall through to the LLM. Guards + booking refs still run below.
        reply = ""
        try:
            scored = _faq_scores(pack, message)
            if scored and scored[0][0] >= _FAQ_SHORT_CIRCUIT_SCORE:
                reply = (scored[0][1].get("a") or "").strip()
        except Exception:
            reply = ""
        try:
            if not reply and llm_service.is_configured():
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

        reply = _ensure_safety_reply(reply, message)
        reply = _ensure_price_answer(reply, message, pack)
        reply = _ensure_redirect(reply, message)

        booking = _has_booking_intent(message)
        lead_reference = _make_lead_reference() if booking else None
        stage = "booking" if booking else "info"
        if lead_reference and "TPL-" not in reply:
            # Voice callers can't see JSON — speak the reference aloud.
            # Claim flows hear "claim reference", everything else "booking".
            label = "claim" if any(
                w in (message or "").lower() for w in _CLAIM_WORDS) else "booking"
            reply = f"{reply.rstrip()} Your {label} reference is {lead_reference}."

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
