import base64
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.rate_limit import limiter
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import User
from app.schemas import VoiceQuoteRequest, VoiceQuoteResponse
from app.routes.auth import get_current_user
from app.services import llm

router = APIRouter(prefix="/api/voice", tags=["voice"])
settings = get_settings()

# Verified live against Sarvam API (Sep 2026):
# - English language code is en-IN (en-GB rejected)
# - TTS model bulbul:v3 (v2 deprecated), speaker priya
# - TTS response carries audio in `audios[]` (not `audio_base64`)
_SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
_SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
_SARVAM_LANG = "en-IN"
_SARVAM_TTS_MODEL = "bulbul:v3"
_SARVAM_TTS_SPEAKER = "priya"
_SARVAM_STT_MODEL = "saarika:v2.5"


def _sarvam_key() -> str:
    return (settings.SARVAM_API_KEY or "").strip()


async def sarvam_tts(text: str) -> str | None:
    """Text → base64 audio via Sarvam Bulbul. None on any failure/no key."""
    if not _sarvam_key() or not (text or "").strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                _SARVAM_TTS_URL,
                headers={"api-subscription-key": _sarvam_key()},
                json={
                    "inputs": [(text or "").strip()[:2000]],
                    "target_language_code": _SARVAM_LANG,
                    "speaker": _SARVAM_TTS_SPEAKER,
                    "model": _SARVAM_TTS_MODEL,
                },
            )
            if response.status_code == 200:
                body = response.json()
                audios = body.get("audios") or []
                if audios and audios[0]:
                    return audios[0]
    except Exception:
        pass
    return None


async def sarvam_stt(audio_base64: str) -> str:
    """Base64 audio → transcript via Sarvam Saarika (multipart upload)."""
    if not _sarvam_key() or not audio_base64:
        return ""
    try:
        raw = base64.b64decode(audio_base64)
    except Exception:
        return ""
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                _SARVAM_STT_URL,
                headers={"api-subscription-key": _sarvam_key()},
                files={"file": ("audio", raw, "audio/wav")},
                data={"model": _SARVAM_STT_MODEL, "language_code": _SARVAM_LANG},
            )
            if response.status_code == 200:
                body = response.json()
                if isinstance(body.get("transcript"), str):
                    return body["transcript"]
                data = body.get("data") or {}
                if isinstance(data.get("transcript"), str):
                    return data["transcript"]
    except Exception:
        pass
    return ""


async def transcribe_audio(audio_base64: str) -> str:
    return await sarvam_stt(audio_base64)


async def generate_quote_from_text(transcript: str) -> dict:
    # ─── Central LLM (DeepSeek) first — reasoning belongs there ───
    if llm.is_configured():
        try:
            raw = await llm.complete_json(
                f"Parse this customer service request into a quote. Request: {transcript}\n"
                'Return ONLY valid JSON: {"title": str, '
                '"items": [{"description": str, "quantity": number, "unit_price": number (GBP)}], '
                '"estimated_hours": number, "notes": str}. Use UK English.',
                system="You are an expert UK field service quote generator. "
                       "Return ONLY valid JSON, no markdown. Prices in GBP.",
                max_tokens=800,
                temperature=0.3,
            )
            items = []
            for i in raw.get("items", []) or []:
                if not isinstance(i, dict):
                    continue
                try:
                    items.append({
                        "description": str(i.get("description", "Service")),
                        "quantity": float(i.get("quantity", 1) or 1),
                        "unit_price": float(i.get("unit_price", 0) or 0),
                    })
                except (TypeError, ValueError):
                    continue
            return {
                "title": str(raw.get("title", "Service Request") or "Service Request"),
                "items": items or [{"description": "Service call", "quantity": 1, "unit_price": 0}],
                "estimated_hours": float(raw.get("estimated_hours", 1) or 1),
                "notes": str(raw.get("notes", "") or ""),
            }
        except Exception:
            pass
    return {
        "title": "Service Request",
        "items": [{"description": "Service call", "quantity": 1, "unit_price": 0}],
        "estimated_hours": 1,
        "notes": "Please provide details for accurate pricing"
    }


async def generate_voice_response(quote_data: dict) -> str:
    title = quote_data.get("title", "Service")
    items = quote_data.get("items", []) or []
    total = sum(float(i.get("quantity", 0) or 0) * float(i.get("unit_price", 0) or 0) for i in items if isinstance(i, dict))
    items_text = ", ".join(str(i.get("description", "")) for i in items if isinstance(i, dict))

    text = f"Here's your quote for {title}. The estimated cost is £{total:.0f}. This includes: {items_text}. Would you like to proceed?"

    audio = await sarvam_tts(text)
    return audio or text


@router.post("/transcribe", response_model=VoiceQuoteResponse)
@limiter.limit("10/minute")
async def transcribe_and_quote(
    request: Request,
    data: VoiceQuoteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    transcript = data.transcript

    if data.audio_base64 and not transcript:
        transcript = await transcribe_audio(data.audio_base64)

    if not transcript:
        raise HTTPException(status_code=400, detail="No audio or transcript provided")

    quote_data = await generate_quote_from_text(transcript)
    voice_response = await generate_voice_response(quote_data)

    return VoiceQuoteResponse(
        transcript=transcript,
        quote_data=quote_data,
        voice_response=voice_response
    )


@router.post("/text-to-speech")
async def text_to_speech(text: str):
    audio = await sarvam_tts(text)
    if audio:
        return {"audio_base64": audio}
    return {"audio_base64": None, "fallback": True}


@router.post("/speech-to-text")
@limiter.limit("10/minute")
async def speech_to_text(request: Request, audio_base64: str):
    transcript = await sarvam_stt(audio_base64)
    return {"transcript": transcript}
