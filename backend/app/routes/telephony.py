"""Twilio Programmable Voice (Media Streams) into the realtime pipeline.

Wiring (main.py is frozen for this task — add these two lines yourself):
    from app.routes import telephony
    app.include_router(telephony.router)

Webhook URLs to paste into the Twilio console (Phone Number -> Voice
Configuration -> "A call comes in" -> Webhook, HTTP POST):
    Voice webhook:  https://<public-host>/api/telephony/voice
Media Streams connect-back (derived automatically from TWILIO_MEDIA_WS_URL):
    Media WS:       wss://<public-host>/api/telephony/media
Outbound announcement callbacks are built automatically per call:
    https://<public-host>/api/telephony/outbound-twiml?message=...
(Full-agent outbound calls should point at /voice instead so the caller
gets the live agent rather than a one-shot <Say>.)

Tunnel requirement: Twilio cannot reach localhost. Expose this backend via
a public tunnel (ngrok/cloudflared) or a VPS with public HTTPS/WSS, then
set TWILIO_MEDIA_WS_URL to the public *wss* base URL, e.g.
TWILIO_MEDIA_WS_URL=wss://abc123.ngrok.io

Raw REST + hand-built TwiML only — no twilio SDK. Only httpx + numpy
(+ stdlib) are used here. Every audio helper is pure and never raises.
Every WebSocket stage is try/except-guarded so one bad frame or failed
STT/LLM/TTS call can never crash the socket.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import quote
from xml.sax.saxutils import escape as _xml_escape

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel

from app.core.config import get_settings
from app.models.models import User
from app.routes.auth import get_current_user
from app.services.realtime_voice import (
    VadTurnDetector,
    groq_chat,
    groq_transcribe,
    pcm16_to_wav,
)

try:  # Emotion layer is additive; telephony works without it.
    from app.services.emotion import (
        EMPATHY_POLICY,
        adapt,
        analyze_prosody,
        classify_state,
    )
    _EMOTION_AVAILABLE = True
except Exception:
    EMPATHY_POLICY = {}
    _EMOTION_AVAILABLE = False

    def analyze_prosody(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError("emotion module unavailable")

    def classify_state(*args, **kwargs):  # type: ignore[no-redef]
        raise RuntimeError("emotion module unavailable")

    def adapt(*args, **kwargs):  # type: ignore[no-redef]
        return {"mood": None, "escalate": False, "reason": None}


router = APIRouter(prefix="/api/telephony", tags=["telephony"])

# Live phone sessions keyed by Twilio streamSid (decoupled from calls.py —
# own minimal shape, no imports from the calls router).
TWILIO_CALLS: dict[str, dict] = {}
# Finished records keyed by our call_id (populated on stop/disconnect).
TWILIO_CALL_RECORDS: dict[str, dict] = {}

_MULAW_BIAS = 0x84
_MULAW_CLIP = 32635
# Outbound audio chunking: 320 bytes of 8kHz mu-law per `media` message.
_MULAW_CHUNK = 320
# 20s cap @16kHz mono int16, mirroring realtime_voice.
_MAX_UTTERANCE_BYTES = 16000 * 2 * 20
_HISTORY_MAX_MSGS = 12
_EMOTION_MAX_TURNS = 20


# ─── Audio glue (numpy only, pure functions, never raise) ────────────────────

def mulaw_to_pcm16(mulaw: bytes) -> bytes:
    """G.711 mu-law bytes -> Int16LE PCM bytes. Empty bytes on bad input."""
    try:
        import numpy as np

        if not mulaw:
            return b""
        u = np.frombuffer(bytes(mulaw), dtype=np.uint8).astype(np.int32)
        u = (~u) & 0xFF
        sign = u & 0x80
        exponent = (u >> 4) & 0x07
        mantissa = u & 0x0F
        magnitude = (((mantissa << 3) + _MULAW_BIAS) << exponent) - _MULAW_BIAS
        out = np.where(sign != 0, -magnitude, magnitude)
        return np.clip(out, -32768, 32767).astype(np.int16).tobytes()
    except Exception:
        return b""


def pcm16_to_mulaw(pcm: bytes) -> bytes:
    """Int16LE PCM bytes -> G.711 mu-law bytes. Empty bytes on bad input."""
    try:
        import numpy as np

        if not pcm or len(pcm) < 2:
            return b""
        raw = bytes(pcm)
        if len(raw) % 2:
            raw = raw[:-1]
        if not raw:
            return b""
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.int32)
        if samples.size == 0:
            return b""
        negative = samples < 0
        biased = np.minimum(np.where(negative, -samples, samples),
                            _MULAW_CLIP) + _MULAW_BIAS
        # Segment number: floor(log2(biased)) - 7 in [0, 7]. The epsilon
        # guards exact powers of two against float rounding below the step.
        exponent = np.clip(
            np.floor(np.log2(biased.astype(np.float64)) + 1e-6).astype(np.int32) - 7,
            0, 7,
        )
        mantissa = (biased >> (exponent + 3)) & 0x0F
        code = np.where(negative, 0x80, 0) | (exponent << 4) | mantissa
        return ((~code) & 0xFF).astype(np.uint8).tobytes()
    except Exception:
        return b""


def resample_8k_to_16k(pcm: bytes) -> bytes:
    """Int16LE mono 8kHz -> 16kHz via linear interp. Empty on bad input."""
    try:
        import numpy as np

        if not pcm or len(pcm) < 2:
            return b""
        raw = bytes(pcm)
        if len(raw) % 2:
            raw = raw[:-1]
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if x.size == 0:
            return b""
        old_idx = np.arange(x.size, dtype=np.float64)
        new_idx = np.arange(x.size * 2, dtype=np.float64) * 0.5
        y = np.interp(new_idx, old_idx, x)
        return np.clip(y, -32768, 32767).astype(np.int16).tobytes()
    except Exception:
        return b""


def resample_16k_to_8k(pcm: bytes) -> bytes:
    """Int16LE mono 16kHz -> 8kHz via linear interp. Empty on bad input."""
    try:
        import numpy as np

        if not pcm or len(pcm) < 2:
            return b""
        raw = bytes(pcm)
        if len(raw) % 2:
            raw = raw[:-1]
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if x.size == 0:
            return b""
        new_idx = np.arange(x.size // 2, dtype=np.float64) * 2.0
        if new_idx.size == 0:
            return b""
        old_idx = np.arange(x.size, dtype=np.float64)
        y = np.interp(new_idx, old_idx, x)
        return np.clip(y, -32768, 32767).astype(np.int16).tobytes()
    except Exception:
        return b""


def _mp3_to_pcm16_16k(mp3: bytes) -> bytes:
    """Best-effort MP3 -> Int16LE mono 16kHz PCM (bundled ffmpeg). Never raises."""
    try:
        if not mp3:
            return b""
        import os
        import subprocess
        import tempfile

        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as fin:
            fin.write(bytes(mp3))
            in_path = fin.name
        out_fd, out_path = tempfile.mkstemp(suffix=".raw")
        os.close(out_fd)
        try:
            subprocess.run(
                [ffmpeg, "-y", "-v", "error", "-i", in_path,
                 "-ac", "1", "-ar", "16000", "-f", "s16le", out_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            with open(out_path, "rb") as fh:
                return fh.read()
        finally:
            for p in (in_path, out_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass
    except Exception:
        return b""


# ─── Settings / URL helpers (mirror sms.py creds pattern) ────────────────────

def _twilio_creds() -> tuple[str, str]:
    s = get_settings()
    return ((s.TWILIO_ACCOUNT_SID or "").strip(),
            (s.TWILIO_AUTH_TOKEN or "").strip())


def _twilio_from_number() -> str:
    # Voice calls need a real Twilio number — never the SMS sender-ID fallback.
    return (get_settings().TWILIO_PHONE_NUMBER or "").strip()


def _public_base() -> str:
    """Public base without scheme conversion.

    Order: explicit TWILIO_MEDIA_WS_URL (tunnel/VPS) wins, then the
    backend's own PUBLIC_API_URL. NOTE: APP_URL is the FRONTEND and must
    never be used here — Twilio webhooks + media streams hit the backend.
    """
    s = get_settings()
    media = (getattr(s, "TWILIO_MEDIA_WS_URL", "") or "").strip().rstrip("/")
    if media:
        return media
    return ((getattr(s, "PUBLIC_API_URL", "") or "").strip().rstrip("/")
            or "http://localhost:8000")


def _media_ws_url() -> str:
    base = _public_base()
    if base.startswith("https://"):
        base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://"):]
    return base + "/api/telephony/media"


def _http_base() -> str:
    base = _public_base()
    if base.startswith("wss://"):
        base = "https://" + base[len("wss://"):]
    elif base.startswith("ws://"):
        base = "http://" + base[len("ws://"):]
    return base


def _valid_twilio_signature(url: str, params: dict,
                            signature: str, auth_token: str) -> bool:
    """Twilio signing: HMAC-SHA1(auth_token, url + sorted k+v), base64."""
    try:
        if not url or not auth_token or not signature:
            return False
        data = url + "".join(
            str(k) + str(params[k]) for k in sorted(params.keys()))
        digest = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"),
                          hashlib.sha1).digest()
        expected = base64.b64encode(digest).decode("ascii")
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


def _twiml(content: str, status_code: int = 200) -> Response:
    return Response(content=content, media_type="application/xml",
                    status_code=status_code)


def _xml_attr(value: str) -> str:
    try:
        return _xml_escape(value or "", {'"': "&quot;"})
    except Exception:
        return ""


# ─── POST /voice: Twilio inbound webhook (NO auth — signature instead) ───────

@router.post("/voice")
async def voice_webhook(request: Request):
    """Inbound-call webhook. Returns <Connect><Stream> to /media on success."""
    try:
        form = await request.form()
        params = {str(k): str(v) for k, v in form.items()}
    except Exception:
        params = {}
    from_number = (params.get("From") or "").strip()
    call_sid = (params.get("CallSid") or "").strip()

    sid, token = _twilio_creds()
    if not sid or not token:
        return _twiml(
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say>Sorry, this number is not configured "
            "for voice calls yet. Goodbye.</Say></Response>"
        )
    signature = request.headers.get("X-Twilio-Signature", "") or ""
    if not _valid_twilio_signature(str(request.url), params, signature, token):
        return _twiml(
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Reject/></Response>",
            status_code=403,
        )
    ws_url = _media_ws_url()
    return _twiml(
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Connect><Stream url=\"" + _xml_attr(ws_url) + "\">"
        "<Parameter name=\"callSid\" value=\"" + _xml_attr(call_sid) + "\"/>"
        "<Parameter name=\"from\" value=\"" + _xml_attr(from_number) + "\"/>"
        "</Stream></Connect></Response>"
    )


# ─── GET /outbound-twiml: one-shot announcement (NO auth — Twilio calls it) ──

@router.get("/outbound-twiml")
async def outbound_twiml(message: str = "Hello from VoiceField."):
    """Simple <Say> announcement for POST /call callbacks.

    Full-agent outbound (live conversation) should point the Twilio call's
    Url at POST /voice instead so the caller gets the realtime agent.
    """
    try:
        text = (message or "").strip() or "Hello from VoiceField."
    except Exception:
        text = "Hello from VoiceField."
    return _twiml(
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Say>" + _xml_attr(text)[:1600] + "</Say></Response>"
    )


# ─── WS /media: Twilio Media Streams socket (NO auth — headerless) ───────────

def _heuristic_summary(history: list) -> str:
    try:
        caller = [m for m in (history or [])
                  if isinstance(m, dict) and m.get("role") == "user"
                  and str(m.get("content") or "").strip()]
        n_agent = sum(1 for m in (history or [])
                      if isinstance(m, dict) and m.get("role") == "assistant")
        if caller:
            first = str(caller[0].get("content") or "")[:160]
            out = (f"Phone call had {len(history or [])} messages "
                   f"({len(caller)} caller / {n_agent} agent). "
                   f"Caller opened with: \"{first}\".")
            if len(caller) > 1:
                last = str(caller[-1].get("content") or "")[:160]
                out += f" Call closed with: \"{last}\"."
            return out
        return (f"Phone call had {len(history or [])} messages with no caller "
                "speech captured. Review transcript for detail.")
    except Exception:
        return "Phone call ended. Review transcript for detail."


async def _finalize_twilio_call(stream_key: str) -> None:
    """Pop the live session, attach analysis, archive. Never raises."""
    try:
        rec = TWILIO_CALLS.pop(stream_key, None)
        if not isinstance(rec, dict):
            return
        history = rec.get("history") or []
        emotions = rec.get("emotions") or []
        summary = _heuristic_summary(history)
        model = "heuristic"
        try:
            from app.services.llm import complete as _llm_complete
            from app.services.llm import is_configured as _llm_configured

            if _llm_configured() and history:
                transcript = "\n".join(
                    f"{(m or {}).get('role', 'user')}: "
                    f"{str((m or {}).get('content', ''))[:500]}"
                    for m in history
                )[:6000]
                summary = (await _llm_complete(
                    "Summarise this phone call in 2-3 sentences.\nTranscript:\n"
                    + transcript,
                    system="You are a call-centre QA analyst.",
                    max_tokens=300, temperature=0.2,
                )).strip()[:1000] or summary
                model = "llm"
        except Exception:
            pass
        call_id = str(rec.get("call_id") or stream_key)
        TWILIO_CALL_RECORDS[call_id] = {
            "call_id": call_id,
            "stream_sid": rec.get("stream_sid"),
            "call_sid": rec.get("call_sid"),
            "from": rec.get("from"),
            "started_at": rec.get("started_at"),
            "ended_at": datetime.utcnow().isoformat(),
            "status": "ended",
            "turns": history,
            "emotions": emotions,
            "analysis": {"summary": summary, "model": model},
        }
    except Exception:
        try:
            TWILIO_CALLS.pop(stream_key, None)
        except Exception:
            pass


@router.websocket("/media")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    detector = VadTurnDetector()  # lazy model; RMS fallback until ready
    utterance = bytearray()
    speaking = False
    current_task: asyncio.Task | None = None
    send_lock = asyncio.Lock()

    stream_sid: str | None = None
    call_sid = ""
    from_number = ""
    call_id = ""
    history: list = []
    emotions: list = []

    def _stream_key() -> str:
        return stream_sid or call_sid or call_id

    async def send_json(obj: dict) -> None:
        async with send_lock:
            await websocket.send_json(obj)

    async def process_turn(pcm: bytes) -> None:
        """16kHz caller utterance -> STT -> emotion -> LLM -> TTS -> phone."""
        nonlocal speaking
        try:
            key = (get_settings().GROQ_API_KEY or "").strip()
            if not key or not pcm:
                return
            _prosody: dict | None = None
            if _EMOTION_AVAILABLE:
                try:
                    _prosody = analyze_prosody(bytes(pcm))
                except Exception:
                    _prosody = None
            try:
                wav = pcm16_to_wav(bytes(pcm), 16000)
            except Exception:
                return
            try:
                text = await groq_transcribe(wav, key)
            except Exception:
                return
            text = (text or "").strip()
            if not text:
                return
            emotion_state = "neutral"
            emotion_conf = 0.5
            if _EMOTION_AVAILABLE:
                try:
                    _pros = (_prosody if isinstance(_prosody, dict)
                             else analyze_prosody(bytes(pcm)))
                    _cls = classify_state(_pros or {}, text)
                    emotion_state = str((_cls or {}).get("state") or "neutral")
                    emotion_conf = float((_cls or {}).get("confidence", 0.5))
                    if emotion_state not in EMPATHY_POLICY:
                        emotion_state = "neutral"
                except Exception:
                    emotion_state, emotion_conf = "neutral", 0.5
            try:
                emotions.append({"turn": len(emotions) + 1,
                                 "state": emotion_state,
                                 "confidence": emotion_conf})
                if len(emotions) > _EMOTION_MAX_TURNS:
                    del emotions[: len(emotions) - _EMOTION_MAX_TURNS]
            except Exception:
                pass
            empathy_addon = ""
            tts_rate, tts_pitch = "+0%", "+0Hz"
            if _EMOTION_AVAILABLE:
                try:
                    _pol = (EMPATHY_POLICY or {}).get(emotion_state) or {}
                    empathy_addon = str(_pol.get("prompt_addon") or "").strip()
                    tts_rate = str(_pol.get("tts_rate") or "+0%")
                    tts_pitch = str(_pol.get("tts_pitch") or "+0Hz")
                except Exception:
                    empathy_addon = ""
            messages = list(history)
            if empathy_addon:
                messages.append({"role": "system", "content": empathy_addon})
            messages.append({"role": "user", "content": text})
            reply = ""
            try:
                reply = (await groq_chat(messages, key) or "").strip()
            except Exception:
                reply = ""
            if not reply:
                try:
                    from app.services.llm import complete as _llm_complete

                    reply = (await _llm_complete(
                        f"Caller: {text}",
                        system=("You are the VoiceField support assistant. "
                                "Be concise: at most 2 short sentences."),
                        max_tokens=150, temperature=0.3,
                    ) or "").strip()
                except Exception:
                    reply = ""
            if not reply:
                return
            try:
                history.append({"role": "user", "content": text})
                history.append({"role": "assistant", "content": reply})
                if len(history) > _HISTORY_MAX_MSGS:
                    del history[: len(history) - _HISTORY_MAX_MSGS]
                try:
                    if stream_sid:
                        TWILIO_CALLS[stream_sid]["history"] = list(history)
                        TWILIO_CALLS[stream_sid]["emotions"] = list(emotions)
                except Exception:
                    pass
            except Exception:
                pass
            try:
                from app.services.speech import EdgeTTSVoice

                mp3, _voice = await EdgeTTSVoice().speak(
                    reply, rate=tts_rate, pitch=tts_pitch)
            except Exception:
                return
            pcm16 = _mp3_to_pcm16_16k(mp3)
            if not pcm16:
                return
            mulaw = pcm16_to_mulaw(resample_16k_to_8k(pcm16))
            if not mulaw:
                return
            speaking = True
            try:
                for i in range(0, len(mulaw), _MULAW_CHUNK):
                    chunk = mulaw[i: i + _MULAW_CHUNK]
                    await send_json({
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload":
                                  base64.b64encode(chunk).decode("ascii")},
                    })
            finally:
                speaking = False
        except asyncio.CancelledError:
            speaking = False
            raise
        except Exception:
            speaking = False

    try:
        while True:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                break
            except Exception:
                break  # transport error — close loop, not a crash
            text = message.get("text")
            if text is None:
                continue  # Twilio sends text frames only; ignore the rest
            try:
                event = json.loads(text)
            except Exception:
                continue
            try:
                etype = str((event or {}).get("event") or "").strip().lower()
            except Exception:
                continue
            if etype == "connected":
                continue  # protocol handshake — nothing to do
            elif etype == "start":
                try:
                    start = (event.get("start") or {}) if isinstance(event, dict) else {}
                    acct = str(start.get("accountSid") or "").strip()
                    sid, _tok = _twilio_creds()
                    if sid and acct and acct != sid:
                        try:
                            await websocket.close()
                        except Exception:
                            pass
                        break
                    stream_sid = (event.get("streamSid")
                                  or start.get("streamSid") or "")
                    stream_sid = str(stream_sid or "").strip()
                    call_sid = str(start.get("callSid") or "").strip()
                    params = start.get("customParameters") or {}
                    if not isinstance(params, dict):
                        params = {}
                    from_number = str(params.get("from")
                                      or start.get("from") or "").strip()
                    call_id = str(uuid.uuid4())
                    history = []
                    emotions = []
                    detector.reset()
                    utterance.clear()
                    if stream_sid:
                        TWILIO_CALLS[stream_sid] = {
                            "call_id": call_id,
                            "stream_sid": stream_sid,
                            "call_sid": call_sid,
                            "from": from_number,
                            "started_at": datetime.utcnow().isoformat(),
                            "status": "live",
                            "history": history,
                            "emotions": emotions,
                        }
                except Exception:
                    continue
            elif etype == "media":
                try:
                    media = (event.get("media") or {}) if isinstance(event, dict) else {}
                    payload = media.get("payload") or ""
                    try:
                        raw = base64.b64decode(str(payload)) if payload else b""
                    except Exception:
                        raw = b""
                    pcm8 = mulaw_to_pcm16(raw)
                    pcm16 = resample_8k_to_16k(pcm8) if pcm8 else b""
                    if not pcm16:
                        continue
                    room = _MAX_UTTERANCE_BYTES - len(utterance)
                    if room <= 0:
                        forced = bytes(utterance)
                        utterance.clear()
                        detector.reset()
                        if forced and (current_task is None
                                       or current_task.done()):
                            current_task = asyncio.create_task(
                                process_turn(forced))
                        continue
                    utterance.extend(pcm16[:room] if room < len(pcm16) else pcm16)
                    try:
                        turn_event = detector.feed(pcm16)
                    except Exception:
                        turn_event = None
                    if turn_event == "speech_start" and (
                            speaking or (current_task is not None
                                         and not current_task.done())):
                        # Barge-in: stop phone audio, drop the reply task.
                        speaking = False
                        if current_task is not None and not current_task.done():
                            try:
                                current_task.cancel()
                            except Exception:
                                pass
                            current_task = None
                        try:
                            await send_json({"event": "clear",
                                             "streamSid": stream_sid})
                        except Exception:
                            pass
                    elif turn_event == "speech_end":
                        pcm_done = bytes(utterance)
                        utterance.clear()
                        detector.reset()
                        if pcm_done and (current_task is None
                                         or current_task.done()):
                            current_task = asyncio.create_task(
                                process_turn(pcm_done))
                except Exception:
                    continue
            elif etype == "stop":
                break
            # Unknown events (e.g. "mark", "dtmf") are ignored.
    finally:
        try:
            if current_task is not None and not current_task.done():
                current_task.cancel()
        except Exception:
            pass
        try:
            key = _stream_key()
            if key:
                await _finalize_twilio_call(key)
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass


# ─── Auth-required management endpoints ───────────────────────────────────────

class OutboundCallBody(BaseModel):
    to_phone: str
    message: Optional[str] = None


class HangupBody(BaseModel):
    stream_sid: Optional[str] = None
    call_sid: Optional[str] = None


@router.post("/call")
async def start_outbound_call(body: OutboundCallBody,
                              current_user: User = Depends(get_current_user)):
    """Place an outbound call via Twilio REST.

    The call's Url points at /outbound-twiml for a one-shot announcement.
    For a full live-agent outbound call, create the call with Url pointing
    at /api/telephony/voice instead.
    """
    try:
        from app.services.phone import normalize_uk_phone

        to_e164 = normalize_uk_phone((body.to_phone or "").strip())
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid UK phone number")
    sid, token = _twilio_creds()
    if not sid or not token:
        raise HTTPException(status_code=503,
                            detail="Twilio not configured (TWILIO_* missing)")
    from_number = _twilio_from_number()
    if not from_number:
        raise HTTPException(status_code=400,
                            detail="no Twilio number — buy one")
    try:
        message = (body.message or "").strip() or "Hello from VoiceField."
    except Exception:
        message = "Hello from VoiceField."
    callback_url = (_http_base() + "/api/telephony/outbound-twiml?message="
                    + quote(message[:1600], safe=""))
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
                auth=(sid, token),
                data={"To": to_e164, "From": from_number, "Url": callback_url},
            )
            resp.raise_for_status()
            data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502,
                            detail=f"Twilio call failed: {e}"[:300])
    try:
        return {"call_sid": data.get("sid"), "status": data.get("status")}
    except Exception:
        raise HTTPException(status_code=502, detail="Twilio bad response")


@router.get("/status")
async def telephony_status(current_user: User = Depends(get_current_user)):
    sid, token = _twilio_creds()
    try:
        number = (get_settings().TWILIO_PHONE_NUMBER or "").strip() or None
    except Exception:
        number = None
    try:
        media_ws_url = _media_ws_url()
    except Exception:
        media_ws_url = ""
    try:
        active = len(TWILIO_CALLS)
    except Exception:
        active = 0
    return {
        "twilio_configured": bool(sid and token),
        "phone_number": number,
        "media_ws_url": media_ws_url,
        "active_calls": active,
        "note": ("Twilio cannot reach localhost — expose /api/telephony/voice "
                 "and /api/telephony/media via a public tunnel (ngrok/ "
                 "cloudflared) or VPS and set TWILIO_MEDIA_WS_URL to the "
                 "public wss base URL."),
    }


@router.post("/hangup")
async def hangup_call(body: HangupBody,
                      current_user: User = Depends(get_current_user)):
    """Best-effort hangup (Twilio call -> completed). Always 200."""
    hung_up = False
    target = ""
    try:
        target = ((body.call_sid or "").strip())
        if not target and (body.stream_sid or "").strip():
            try:
                rec = TWILIO_CALLS.get((body.stream_sid or "").strip())
                if isinstance(rec, dict):
                    target = str(rec.get("call_sid") or "").strip()
            except Exception:
                target = ""
        if target:
            sid, token = _twilio_creds()
            if sid and token:
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.post(
                            f"https://api.twilio.com/2010-04-01/Accounts/{sid}"
                            f"/Calls/{target}.json",
                            auth=(sid, token),
                            data={"Status": "completed"},
                        )
                        hung_up = 200 <= resp.status_code < 300
                except Exception:
                    hung_up = False
    except Exception:
        hung_up = False
    return {"ok": True, "hung_up": hung_up, "call_sid": target or None}
