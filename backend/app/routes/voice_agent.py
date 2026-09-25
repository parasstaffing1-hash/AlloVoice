"""Local voice-agent routes: STT (faster-whisper) + TTS (edge-tts) + central LLM.

Prefix: /api/voice-agent
"""

import asyncio
import base64
import binascii
import re
import time
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.models import KnowledgeBaseArticle, User
from app.routes.auth import get_current_user
from app.services import llm as llm_service
from app.services.speech import (
    FALLBACK_VOICE,
    MAX_TTS_CHARS,
    PRIMARY_VOICE,
    EdgeTTSVoice,
    get_stt,
    get_tts,
    webm_to_wav,
)

router = APIRouter(prefix="/api/voice-agent", tags=["voice-agent"])

# session_id -> [{"role": ..., "content": ...}] (cap 20 entries)
_sessions: Dict[str, List[dict]] = {}

_VOICE_ALIASES = {
    "sonia": PRIMARY_VOICE,
    "ryan": FALLBACK_VOICE,
    PRIMARY_VOICE.lower(): PRIMARY_VOICE,
    FALLBACK_VOICE.lower(): FALLBACK_VOICE,
}

CHAT_SYSTEM_PROMPT = (
    "You are the Allo support assistant, a UK trades SaaS helping "
    "customers with creating accounts, documents needed (ID, proof of address, "
    "Gas Safe certificates and EICR certificates for engineers, company details "
    "for quotes), bookings and plans. Use a professional British customer-support "
    "tone. Be concise and use plain English. "
    "IMPORTANT: reply in at most 2 short sentences — this is read aloud."
)


def _spoken_excerpt(text: str, limit: int = 280) -> str:
    """First ~2 sentences for TTS so replies start playing fast."""
    import re
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    out = ""
    for p in parts[:3]:
        candidate = (out + " " + p).strip()
        if len(candidate) > limit and out:
            break
        out = candidate
    return out or (text or "")[:limit]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TranscribeRequest(BaseModel):
    audio_base64: str = ""


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1600)
    voice: Optional[str] = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Rule-based fallback (used when LLM is not configured or errors)
# ---------------------------------------------------------------------------


def rule_based_reply(message: str) -> str:
    t = (message or "").lower().strip()

    if any(w in t for w in ["thank"]):
        return (
            "You're welcome! If you need anything else with your account, "
            "documents, bookings or plans, just let me know."
        )
    if any(w in t for w in ["goodbye", "bye", "see you", "cheers"]):
        return "Goodbye, and thanks for using Allo! Get in touch any time you need help."
    # Word-boundary match: plain `in` checks misfire on "hi" inside
    # "which"/"this"/"high", shadowing the document/booking branches below.
    if re.search(
        r"\b(hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening)\b", t
    ):
        return (
            "Hello! I'm the Allo support assistant. I can help with creating "
            "your account, documents you'll need, bookings and plans. "
            "What would you like help with?"
        )
    if any(k in t for k in ["document", "documents", "id", "proof of address",
                            "gas safe", "eicr", "certificate", "cert"]):
        return (
            "For Allo you'll normally need: (1) photo ID such as a passport or "
            "driving licence, (2) proof of address such as a utility bill or bank "
            "statement, (3) engineer certificates where relevant — Gas Safe "
            "registration for gas work and EICR qualifications for electrical work, "
            "and (4) company details (name, address, VAT number if registered) for "
            "quotes and invoicing."
        )
    if any(k in t for k in ["create account", "creating account", "new account",
                            "sign up", "signup", "register", "account"]):
        return (
            "To create your Allo account: 1) Register with your name, email and "
            "password. 2) Verify your email. 3) Add your business details under "
            "Settings. 4) Invite engineers and upload any certificates. "
            "Would you like help with any of these steps?"
        )
    if any(k in t for k in ["book", "booking", "appointment", "schedule", "visit", "engineer"]):
        return (
            "To make a booking, go to Jobs and choose New Job, pick the customer, "
            "service and preferred time, then assign an engineer. You'll get a "
            "confirmation once it's scheduled. Want help with a specific booking?"
        )
    if any(k in t for k in ["plan", "plans", "pricing", "price", "subscription",
                            "cost", "membership"]):
        return (
            "Allo plans cover job management, dispatch, quotes and invoicing. "
            "Tell me about your team size and workload and I can point you to the "
            "most suitable plan — or I can help with billing questions."
        )
    return (
        "Thanks for getting in touch. I can help with creating your account, "
        "the documents you'll need, bookings and plans. Could you tell me a bit "
        "more about what you need?"
    )


def _get_history(session_id: str) -> List[dict]:
    history = _sessions.get(session_id)
    if history is None:
        history = []
        _sessions[session_id] = history
    return history


def _append_turn(session_id: str, role: str, content: str) -> None:
    history = _get_history(session_id)
    history.append({"role": role, "content": content})
    # Cap at last 20 entries.
    if len(history) > 20:
        del history[: len(history) - 20]


async def _kb_context(
    query: str,
    db,
    business_id=None,
    limit: int = 3,
) -> List[dict]:
    """RAG-lite keyword retrieval over published KB articles (demo-chat use).

    Splits the query into 3+ letter tokens, scores title hits ×3 plus
    content hits ×1, returns top `limit` hits as [{title, excerpt}].
    Never raises — returns [] on any failure (demo must never 500).
    """
    try:
        tokens = re.findall(r"[a-z]{3,}", (query or "").lower())
        if not tokens or db is None:
            return []
        stmt = select(KnowledgeBaseArticle).where(
            KnowledgeBaseArticle.is_published == True  # noqa: E712
        )
        if business_id is not None:
            stmt = stmt.where(KnowledgeBaseArticle.business_id == business_id)
        result = await db.execute(stmt)
        articles = result.scalars().all()
        if not articles:
            return []
        scored: List[tuple] = []
        for article in articles:
            title_lower = (article.title or "").lower()
            content_lower = (article.content or "").lower()
            score = 0
            for token in tokens:
                score += title_lower.count(token) * 3 + content_lower.count(token) * 1
            if score > 0:
                scored.append(
                    (
                        score,
                        {
                            "title": article.title,
                            "excerpt": (article.content or "")[:300],
                        },
                    )
                )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in scored[:limit]]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/transcribe")
@limiter.limit("10/minute")
async def transcribe(
    request: Request,
    data: TranscribeRequest,
    current_user: User = Depends(get_current_user),
):
    """Browser webm (base64) -> English transcript. Never 500 on model errors."""
    raw = (data.audio_base64 or "").strip()
    if not raw:
        return {"transcript": "", "note": "No audio provided"}
    try:
        try:
            webm_bytes = base64.b64decode(raw)
        except (binascii.Error, ValueError) as e:
            return {"transcript": "", "error": f"Invalid base64 audio: {e}"}
        if not webm_bytes:
            return {"transcript": "", "note": "No audio provided"}
        try:
            wav_bytes = await asyncio.to_thread(webm_to_wav, webm_bytes)
        except Exception as e:
            return {"transcript": "", "error": f"Audio conversion failed: {e}"}
        try:
            # Fast path: Groq-hosted Whisper first when GROQ_API_KEY is set;
            # fall back to the configured (default local faster-whisper) STT
            # on any failure. Response shape unchanged.
            try:
                from app.core.config import get_settings as _get_settings

                _groq_key = (_get_settings().GROQ_API_KEY or "").strip()
            except Exception:
                _groq_key = ""
            if _groq_key:
                try:
                    from app.services.speech import GroqWhisperSTT

                    transcript = await GroqWhisperSTT().transcribe(wav_bytes)
                except Exception:
                    transcript = await get_stt().transcribe(wav_bytes)
            else:
                transcript = await get_stt().transcribe(wav_bytes)
        except Exception as e:
            return {"transcript": "", "error": f"Transcription failed: {e}"}
        transcript = (transcript or "").strip()
        if not transcript:
            return {"transcript": "", "note": "No speech recognised"}
        return {"transcript": transcript, "language": "en-GB"}
    except Exception as e:  # absolute safety net — never 500
        return {"transcript": "", "error": str(e)}


@router.post("/speak")
async def speak(
    data: SpeakRequest,
    current_user: User = Depends(get_current_user),
):
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")
    if len(text) > MAX_TTS_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Text too long (max {MAX_TTS_CHARS} chars)",
        )

    requested = (data.voice or "").strip().lower()
    primary_voice: Optional[str] = None
    if requested:
        if requested not in _VOICE_ALIASES:
            raise HTTPException(
                status_code=400, detail="voice must be 'sonia' or 'ryan'"
            )
        primary_voice = _VOICE_ALIASES[requested]

    try:
        if primary_voice:
            provider = EdgeTTSVoice(primary=primary_voice)
        else:
            provider = get_tts()
        # Vocalize the excerpt only — full text already shown in chat.
        speak_text = _spoken_excerpt(text)
        cache_key, cached = _tts_cache_get(primary_voice or "default", speak_text)
        if cached is not None:
            mp3_bytes, voice_used = cached
        else:
            mp3_bytes, voice_used = await provider.speak(speak_text)
            if mp3_bytes:
                _tts_cache_put(cache_key, (mp3_bytes, voice_used))
    except NotImplementedError:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}")

    if not mp3_bytes:
        raise HTTPException(status_code=502, detail="TTS returned empty audio")
    return {
        "audio_base64": base64.b64encode(mp3_bytes).decode("ascii"),
        "voice_used": voice_used,
        "content_type": "audio/mpeg",
    }


@router.post("/chat")
async def chat(
    data: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    message = (data.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="No message provided")
    session_id = (data.session_id or "").strip() or uuid.uuid4().hex
    history = _get_history(session_id)

    reply: str = ""
    if llm_service.is_configured():
        try:
            recent = history[-2:]
            convo = "\n".join(
                f"{'Customer' if h['role'] == 'user' else 'Assistant'}: {h['content']}"
                for h in recent
            )
            prompt = (
                f"{convo}\nCustomer: {message}\nAssistant:"
                if convo
                else f"Customer: {message}\nAssistant:"
            )
            reply = (
                await llm_service.complete(
                    prompt,
                    system=CHAT_SYSTEM_PROMPT,
                    max_tokens=180,
                    temperature=0.3,
                )
            ).strip()
        except Exception:
            reply = ""
    if not reply:
        reply = rule_based_reply(message)

    _append_turn(session_id, "user", message)
    _append_turn(session_id, "assistant", reply)
    return {"reply": reply, "session_id": session_id}


@router.get("/voices")
async def voices():
    return {
        "primary": PRIMARY_VOICE,
        "fallback": FALLBACK_VOICE,
        "provider": "edge-tts",
    }


# ─── Public demo (no login) — strict per-IP rate limits ──────────
# Demo abuse costs real money (LLM) or compute (TTS), so these are
# throttled hard. Authenticated endpoints above are unaffected.

_DEMO_WINDOW_S = 60.0
_DEMO_MAX_CALLS = 10
_demo_hits: Dict[str, List[float]] = {}
_demo_sessions: Dict[str, List[dict]] = {}

# ─── TTS cache: repeat phrases play instantly ───────────────────
# Keyed by voice+text hash, LRU-capped. Demo greetings and common
# replies repeat constantly — no reason to re-synthesize them.
_TTS_CACHE: Dict[str, tuple] = {}
_TTS_CACHE_MAX = 100


def _tts_cache_get(voice: str, text: str):
    import hashlib
    key = hashlib.sha256(f"{voice}|{text}".encode("utf-8")).hexdigest()
    return key, _TTS_CACHE.get(key)


def _tts_cache_put(key: str, value: tuple) -> None:
    _TTS_CACHE[key] = value
    while len(_TTS_CACHE) > _TTS_CACHE_MAX:
        _TTS_CACHE.pop(next(iter(_TTS_CACHE)))


def _demo_allow(ip: str) -> bool:
    now = time.monotonic()
    hits = [t for t in _demo_hits.get(ip, []) if now - t < _DEMO_WINDOW_S]
    if len(hits) >= _DEMO_MAX_CALLS:
        return False
    hits.append(now)
    _demo_hits[ip] = hits
    return True


def _demo_ip(request: Request) -> str:
    try:
        return (request.client.host if request.client else "unknown") or "unknown"
    except Exception:
        return "unknown"


class DemoChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class DemoSpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=300)


@router.post("/demo-chat")
async def demo_chat(
    data: DemoChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public demo chat — 10 calls/min per IP, short replies."""
    if not _demo_allow(_demo_ip(request)):
        raise HTTPException(status_code=429, detail="Demo limit reached — try again in a minute")
    message = data.message.strip()
    ip = _demo_ip(request)
    history = _demo_sessions.get(ip, [])[-2:]
    # RAG-lite: never 500 — fall back to no context on any failure.
    try:
        kb_hits = await _kb_context(message, db, limit=3)
    except Exception:
        kb_hits = []
    # pgvector semantic retrieval (additive): RAG hits first, dedupe by title.
    try:
        from app.services import rag as _rag

        rag_hits = await _rag.retrieve(db, message, limit=3)
        if rag_hits:
            _seen = {h.get("title") for h in rag_hits}
            kb_hits = list(rag_hits) + [h for h in kb_hits if h.get("title") not in _seen]
            kb_hits = kb_hits[:3]
    except Exception:
        pass
    kb_block = ""
    if kb_hits:
        kb_lines = "\n".join(f"- {h['title']}: {h['excerpt']}" for h in kb_hits)
        kb_block = f"Relevant company knowledge:\n{kb_lines}\n"
    reply = ""
    if llm_service.is_configured():
        try:
            convo = "\n".join(
                f"{'Customer' if h['role'] == 'user' else 'Assistant'}: {h['content']}"
                for h in history
            )
            prompt = f"{convo}\n{kb_block}Customer: {message}\nAssistant:" if convo else f"{kb_block}Customer: {message}\nAssistant:"
            reply = (await llm_service.complete(
                prompt, system=CHAT_SYSTEM_PROMPT, max_tokens=150, temperature=0.3)).strip()
        except Exception:
            reply = ""
    if not reply:
        rule_reply = rule_based_reply(message)
        if kb_hits and rule_reply.startswith("Thanks for getting in touch."):
            top = kb_hits[0]
            rule_reply = (
                f"{top['title']}: {top['excerpt']} Want me to book you in?"
            )
        reply = rule_reply
    _demo_sessions[ip] = (history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply},
    ])[-20:]
    return {"reply": reply}


@router.post("/demo-speak")
async def demo_speak(data: DemoSpeakRequest, request: Request):
    """Public demo TTS — 10 calls/min per IP, 300 chars max."""
    if not _demo_allow(_demo_ip(request)):
        raise HTTPException(status_code=429, detail="Demo limit reached — try again in a minute")
    try:
        speak_text = _spoken_excerpt(data.text.strip())
        cache_key, cached = _tts_cache_get("default", speak_text)
        if cached is not None:
            mp3_bytes, voice_used = cached
        else:
            mp3_bytes, voice_used = await get_tts().speak(speak_text)
            if mp3_bytes:
                _tts_cache_put(cache_key, (mp3_bytes, voice_used))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}")
    if not mp3_bytes:
        raise HTTPException(status_code=502, detail="TTS returned empty audio")
    return {
        "audio_base64": base64.b64encode(mp3_bytes).decode("ascii"),
        "voice_used": voice_used,
        "content_type": "audio/mpeg",
    }
