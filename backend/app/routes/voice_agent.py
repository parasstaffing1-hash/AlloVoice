"""Local voice-agent routes: STT (faster-whisper) + TTS (edge-tts) + central LLM.

Prefix: /api/voice-agent
"""

import asyncio
import base64
import binascii
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.models.models import User
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
    "You are the VoiceField support assistant, a UK trades SaaS helping "
    "customers with creating accounts, documents needed (ID, proof of address, "
    "Gas Safe certificates and EICR certificates for engineers, company details "
    "for quotes), bookings and plans. Use a professional British customer-support "
    "tone. Be concise and use plain English."
)


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
        return "Goodbye, and thanks for using VoiceField! Get in touch any time you need help."
    if any(w in t for w in ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"]):
        return (
            "Hello! I'm the VoiceField support assistant. I can help with creating "
            "your account, documents you'll need, bookings and plans. "
            "What would you like help with?"
        )
    if any(k in t for k in ["document", "documents", "id", "proof of address",
                            "gas safe", "eicr", "certificate", "cert"]):
        return (
            "For VoiceField you'll normally need: (1) photo ID such as a passport or "
            "driving licence, (2) proof of address such as a utility bill or bank "
            "statement, (3) engineer certificates where relevant — Gas Safe "
            "registration for gas work and EICR qualifications for electrical work, "
            "and (4) company details (name, address, VAT number if registered) for "
            "quotes and invoicing."
        )
    if any(k in t for k in ["create account", "creating account", "new account",
                            "sign up", "signup", "register", "account"]):
        return (
            "To create your VoiceField account: 1) Register with your name, email and "
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
            "VoiceField plans cover job management, dispatch, quotes and invoicing. "
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/transcribe")
async def transcribe(
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
        mp3_bytes, voice_used = await provider.speak(text)
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
            recent = history[-6:]
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
                    max_tokens=400,
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
