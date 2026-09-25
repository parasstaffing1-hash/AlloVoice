"""Real-time voice WebSocket (Vapi-style turn-taking + barge-in, browser PCM).

No auth — demo-grade. TODO: add per-IP rate limit before exposing publicly.
Wire-up (main.py, do NOT edit here): app.include_router(realtime_voice.router).
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import get_settings
from app.services.realtime_voice import (
    CHAT_SYSTEM_PROMPT,
    VadTurnDetector,
    groq_chat,
    groq_transcribe,
    pcm16_to_wav,
)
from app.services.speech import EdgeTTSVoice

try:  # Hume-style emotion layer is additive; the route works without it.
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

router = APIRouter(prefix="/api/realtime-voice", tags=["realtime-voice"])

# 20s cap @16kHz mono int16: 16000 * 2 * 20.
_MAX_UTTERANCE_BYTES = 16000 * 2 * 20
_MP3_CHUNK = 32 * 1024
# Session histories keyed by connection id; each capped at 6 turns (12 msgs).
_HISTORIES: dict[int, list] = {}
_HISTORY_MAX_MSGS = 12
# Per-connection emotion timelines: [{turn, state, confidence}], capped at 20.
_EMOTIONS: dict[int, list] = {}
_EMOTION_MAX_TURNS = 20
# Global session cap: _HISTORIES/_EMOTIONS are per-conn capped, but the dicts
# themselves were unbounded — a flood of half-open sockets could grow them
# forever. Oldest entries beyond this are evicted on new connections.
_MAX_SESSIONS = 500


def _evict_sessions_if_needed(current_id: int) -> None:
    """Drop oldest sessions beyond _MAX_SESSIONS. Never raises."""
    try:
        while len(_HISTORIES) > _MAX_SESSIONS:
            oldest = next((k for k in _HISTORIES if k != current_id), None)
            if oldest is None:
                break
            _HISTORIES.pop(oldest, None)
            _EMOTIONS.pop(oldest, None)
        while len(_EMOTIONS) > _MAX_SESSIONS:
            oldest = next((k for k in _EMOTIONS if k != current_id), None)
            if oldest is None:
                break
            _EMOTIONS.pop(oldest, None)
            _HISTORIES.pop(oldest, None)
    except Exception:
        pass


def _emotion_timeline(conn_id: int) -> list:
    timeline = _EMOTIONS.get(conn_id)
    if timeline is None:
        timeline = []
        _EMOTIONS[conn_id] = timeline
    return timeline


def _emotion_append(conn_id: int, state: str, confidence: float) -> None:
    timeline = _emotion_timeline(conn_id)
    timeline.append(
        {"turn": len(timeline) + 1, "state": state, "confidence": confidence}
    )
    if len(timeline) > _EMOTION_MAX_TURNS:
        del timeline[: len(timeline) - _EMOTION_MAX_TURNS]


def _history_for(conn_id: int) -> list:
    hist = _HISTORIES.get(conn_id)
    if hist is None:
        hist = []
        _HISTORIES[conn_id] = hist
    return hist


def _history_append(conn_id: int, role: str, content: str) -> None:
    hist = _history_for(conn_id)
    hist.append({"role": role, "content": content})
    if len(hist) > _HISTORY_MAX_MSGS:
        del hist[: len(hist) - _HISTORY_MAX_MSGS]


# ─── Callable voice tools (Groq native tool use, OpenAI tools format) ───

VOICE_TOOLS: list = [
    {
        "type": "function",
        "function": {
            "name": "lookup_customer",
            "description": (
                "Look up a customer by phone number. Use when the caller "
                "asks about their account, bookings, or history."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Caller phone number in any format.",
                    }
                },
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_job",
            "description": (
                "Collect job booking details. Does NOT write a Job row "
                "(no business tenancy on the voice line) — returns a draft "
                "for the office to confirm."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_phone": {
                        "type": "string",
                        "description": "Caller phone number in any format.",
                    },
                    "customer_name": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "normal", "high", "urgent"],
                    },
                },
                "required": ["customer_phone", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_call",
            "description": (
                "Flag that the caller wants a human, a manager, or an "
                "office callback."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                },
                "required": ["reason"],
            },
        },
    },
]

_TOOL_ROUTER_SYSTEM = (
    "You are a voice-call router for a UK trades business. "
    "You have tools: lookup_customer, book_job, escalate_call. "
    "Call lookup_customer when the caller asks about their account, "
    "bookings, or history and a phone number is mentioned or implied. "
    "Call book_job when the caller wants to book, schedule, or request work. "
    "Call escalate_call when the caller asks for a human, a manager, or a "
    "callback, or sounds like they want to complain to someone senior. "
    "Otherwise make NO tool call. Keep arguments minimal and valid."
)

# Job open states for lookup_customer open_jobs_count.
_OPEN_JOB_STATUSES = (
    "quote_requested",
    "quote_sent",
    "quote_approved",
    "scheduled",
    "in_progress",
)


def _normalize_lookup_phone(raw: str) -> str:
    """Normalize a caller phone (UK-first, GB region fallback). Raises ValueError."""
    from app.services.phone import normalize_phone, normalize_uk_phone

    text = (raw or "").strip()
    if not text:
        raise ValueError("Invalid phone number")
    try:
        return normalize_uk_phone(text)
    except ValueError:
        return normalize_phone(text, "GB")


def _drain_complete_sentences(pending: str) -> tuple[list[str], str]:
    """Pop leading complete sentences (ending . ! ?) off `pending`.

    Returns (sentences, remainder). A sentence is emitted only if it
    contains an alphanumeric char and is >= 2 chars; stray punctuation
    is dropped. If no boundary appears, force-split past ~140 chars at
    the last space so slow/free-tier dribbles still produce audio.
    Never raises.
    """
    try:
        sentences: list[str] = []
        buf = pending or ""
        while True:
            pos = -1
            for i, ch in enumerate(buf):
                if ch in ".!?":
                    pos = i
                    break
            if pos < 0:
                if len(buf) >= 140:
                    cut = buf.rfind(" ", 0, 140)
                    cut = cut if cut > 40 else min(len(buf), 140)
                    candidate = buf[:cut].strip()
                    if any(c.isalnum() for c in candidate):
                        sentences.append(candidate)
                    buf = buf[cut:].lstrip()
                    continue
                break
            candidate = buf[: pos + 1].strip()
            rest = buf[pos + 1 :].lstrip()
            if not candidate:
                buf = rest
                continue
            has_word = any(c.isalnum() for c in candidate)
            if has_word and len(candidate) >= 2:
                sentences.append(candidate)
                buf = rest
            else:
                # Stray punctuation (e.g. "...") — drop and keep scanning.
                buf = rest
        return sentences, buf
    except Exception:
        return [], pending


async def _voice_tool_lookup_customer(args: dict) -> dict:
    """lookup_customer executor. Never raises — returns dict (error on failure)."""
    try:
        raw = ""
        try:
            raw = str((args or {}).get("phone")
                      or (args or {}).get("customer_phone") or "").strip()
        except Exception:
            raw = ""
        if not raw:
            return {"found": False, "open_jobs_count": 0,
                    "summary": "no phone provided",
                    "error": "missing phone"}
        try:
            normalized = _normalize_lookup_phone(raw)
        except Exception:
            return {"found": False, "open_jobs_count": 0,
                    "summary": f"invalid phone: {raw}"[:200],
                    "error": f"invalid phone: {raw}"[:200]}
        try:
            from sqlalchemy import select

            from app.core.database import AsyncSessionLocal
            from app.models.models import Business, Customer, Job
        except Exception as e:
            return {"found": False, "open_jobs_count": 0,
                    "summary": "customer lookup unavailable",
                    "error": str(e)[:200]}
        try:
            async with AsyncSessionLocal() as db:
                cust = None
                result = await db.execute(
                    select(Customer)
                    .where(Customer.phone == normalized)
                    .limit(1)
                )
                cust = result.scalars().first()
                if cust is None and raw.strip() != normalized:
                    r2 = await db.execute(
                        select(Customer)
                        .where(Customer.phone == raw.strip())
                        .limit(1)
                    )
                    cust = r2.scalars().first()
                if cust is None:
                    digits = "".join(c for c in normalized if c.isdigit())
                    tail = digits[-9:] if len(digits) >= 9 else digits
                    if tail:
                        r3 = await db.execute(
                            select(Customer)
                            .where(Customer.phone.ilike(f"%{tail}"))
                            .limit(1)
                        )
                        cust = r3.scalars().first()
                if cust is None:
                    return {"found": False, "open_jobs_count": 0,
                            "summary": f"No customer found for {normalized}"}
                biz_name = ""
                try:
                    if getattr(cust, "business_id", None) is not None:
                        rb = await db.execute(
                            select(Business).where(
                                Business.id == cust.business_id)
                        )
                        biz = rb.scalars().first()
                        biz_name = str(getattr(biz, "name", "") or "") if biz else ""
                except Exception:
                    biz_name = ""
                open_count = 0
                try:
                    rj = await db.execute(
                        select(Job).where(
                            Job.customer_id == cust.id,
                            Job.status.in_(_OPEN_JOB_STATUSES),  # type: ignore[attr-defined]
                        )
                    )
                    open_count = len(rj.scalars().all())
                except Exception:
                    # status enum comparison can fail on some drivers — fall
                    # back to counting non-closed by string value.
                    try:
                        rj = await db.execute(
                            select(Job).where(Job.customer_id == cust.id)
                        )
                        closed = {"completed", "cancelled", "paid", "invoiced"}
                        n = 0
                        for j in rj.scalars().all():
                            try:
                                st = str(getattr(getattr(j, "status", ""), "value", getattr(j, "status", "")) or "")
                            except Exception:
                                st = ""
                            if st not in closed:
                                n += 1
                        open_count = n
                    except Exception:
                        open_count = 0
                who = str(getattr(cust, "full_name", "") or "customer")
                where = f" ({biz_name})" if biz_name else ""
                return {"found": True,
                        "customer_id": str(getattr(cust, "id", "")),
                        "open_jobs_count": open_count,
                        "summary": f"{who}{where}, phone {getattr(cust, 'phone', normalized)}, {open_count} open jobs"}
        except Exception as e:
            return {"found": False, "open_jobs_count": 0,
                    "summary": "customer lookup failed",
                    "error": str(e)[:200]}
    except Exception as e:
        return {"found": False, "open_jobs_count": 0,
                "summary": "customer lookup failed",
                "error": str(e)[:200]}


async def _voice_tool_book_job(args: dict) -> dict:
    """book_job executor. Never writes (Job needs business_id+customer_id,
    both nullable=False) — returns {needs_business: True, draft}. Never raises."""
    try:
        a = args if isinstance(args, dict) else {}
        phone_raw = str(a.get("customer_phone") or "").strip()
        title = str(a.get("title") or "").strip()
        desc = str(a.get("description") or "").strip()
        cname = str(a.get("customer_name") or "").strip()
        priority = str(a.get("priority") or "normal").strip().lower() or "normal"
        if priority not in ("low", "normal", "high", "urgent"):
            priority = "normal"
        if not phone_raw:
            return {"needs_business": True, "error": "missing customer_phone",
                    "draft": {"title": title, "description": desc,
                              "priority": priority}}
        if not title:
            return {"needs_business": True, "error": "missing title",
                    "draft": {"customer_phone": phone_raw,
                              "description": desc, "priority": priority}}
        try:
            normalized = _normalize_lookup_phone(phone_raw)
        except Exception:
            return {"needs_business": True,
                    "error": f"invalid phone: {phone_raw}"[:200],
                    "draft": {"customer_phone": phone_raw, "title": title,
                              "description": desc, "priority": priority}}
        # Read-only enrichment: is this an existing customer?
        existing_id = ""
        existing_name = ""
        try:
            from sqlalchemy import select

            from app.core.database import AsyncSessionLocal
            from app.models.models import Customer

            async with AsyncSessionLocal() as db:
                digits = "".join(c for c in normalized if c.isdigit())
                tail = digits[-9:] if len(digits) >= 9 else digits
                cust = None
                r = await db.execute(
                    select(Customer).where(Customer.phone == normalized).limit(1)
                )
                cust = r.scalars().first()
                if cust is None and tail:
                    r2 = await db.execute(
                        select(Customer)
                        .where(Customer.phone.ilike(f"%{tail}")).limit(1)
                    )
                    cust = r2.scalars().first()
                if cust is not None:
                    existing_id = str(getattr(cust, "id", "") or "")
                    existing_name = str(getattr(cust, "full_name", "") or "")
        except Exception:
            pass
        draft = {
            "customer_phone": normalized,
            "customer_name": cname or existing_name,
            "title": title,
            "description": desc,
            "priority": priority,
            "customer_found": bool(existing_id),
            "existing_customer_id": existing_id,
        }
        return {"needs_business": True, "draft": draft,
                "message": ("Collected job details; no business context on "
                            "this voice line so the office should confirm "
                            "the business and create the job.")}
    except Exception as e:
        return {"needs_business": True, "error": str(e)[:200],
                "draft": dict(args) if isinstance(args, dict) else {}}


async def _voice_tool_escalate_call(args: dict) -> dict:
    """escalate_call executor. Never raises."""
    try:
        a = args if isinstance(args, dict) else {}
        reason = str(a.get("reason") or "").strip() or "caller requested escalation"
        return {"escalated": True, "reason": reason[:300]}
    except Exception as e:
        return {"escalated": False, "error": str(e)[:200]}


_TOOL_TRIGGERS = (
    "book", "appointment", "schedule", "price", "cost", "quote", "how much",
    "transfer", "human", "manager", "someone", "person", "agent",
    "call me", "ring me", "phone", "number", "mobile", "contact",
    "cancel", "reschedule", "emergency",
)


def _needs_tools(transcript: str) -> bool:
    """Heuristic gate: only spend an LLM tool-routing round-trip when the
    transcript looks like tool work (contact details, booking/pricing
    intent, escalation). Digit runs (>=6 digits) almost always mean a
    phone number for lookup/booking."""
    try:
        import re

        t = (transcript or "").lower()
        if not t:
            return False
        if re.search(r"\d[\d\s\-()]{5,}\d", t):
            return True
        return any(k in t for k in _TOOL_TRIGGERS)
    except Exception:
        return False


async def _voice_run_tool_pass(
    transcript: str, hist: list
) -> tuple[str | None, bool, str | None]:
    """Try one tool-routing pass. Returns (summary|None, escalated, reason).

    Never raises — any failure returns (None, False, None) so the caller
    falls back to the plain chat path.
    """
    try:
        from app.services.llm import complete_with_tools
    except Exception:
        return (None, False, None)
    try:
        import json as _json

        base: list = [{"role": "system", "content": _TOOL_ROUTER_SYSTEM}]
        for m in (hist or [])[-4:]:
            try:
                role = (m or {}).get("role")
                content = str((m or {}).get("content") or "").strip()
                if role in ("user", "assistant") and content:
                    base.append({"role": role, "content": content})
            except Exception:
                continue
        base.append({"role": "user", "content": transcript})
        messages = list(base)
        results_log: list[tuple[str, dict, dict]] = []
        escalated = False
        esc_reason: str | None = None
        for _round in range(2):
            try:
                data = await complete_with_tools(
                    messages, VOICE_TOOLS, max_tokens=300
                )
            except Exception:
                break
            try:
                msg = data["choices"][0]["message"] or {}
            except Exception:
                break
            calls = msg.get("tool_calls") or []
            if not calls:
                break
            try:
                messages.append({"role": "assistant",
                                 "content": msg.get("content") or "",
                                 "tool_calls": calls})
            except Exception:
                messages.append({"role": "assistant", "content": ""})
            for tc in calls:
                try:
                    fn = ((tc or {}).get("function") or {}).get("name") or ""
                    fname = str(fn).strip()
                    raw_args = ((tc or {}).get("function") or {}).get("arguments") or "{}"
                    try:
                        targs = _json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                    except Exception:
                        targs = {}
                    if not isinstance(targs, dict):
                        targs = {}
                except Exception:
                    fname = ""
                    targs = {}
                if fname == "lookup_customer":
                    res = await _voice_tool_lookup_customer(targs)
                elif fname == "book_job":
                    res = await _voice_tool_book_job(targs)
                elif fname == "escalate_call":
                    res = await _voice_tool_escalate_call(targs)
                    try:
                        if isinstance(res, dict) and res.get("escalated"):
                            escalated = True
                            esc_reason = str(res.get("reason") or "") or "caller requested escalation"
                    except Exception:
                        pass
                else:
                    res = {"error": f"unknown tool {fname}"[:200]}
                results_log.append((fname or "unknown", targs, res if isinstance(res, dict) else {"result": str(res)[:500]}))
                try:
                    tid = (tc or {}).get("id") or "call_0"
                    messages.append({"role": "tool", "tool_call_id": tid,
                                     "content": _json.dumps(results_log[-1][2])[:2000]})
                except Exception:
                    pass
        if not results_log:
            if escalated:
                return (None, True, esc_reason)
            return (None, False, None)
        lines = []
        for n, a, r in results_log:
            try:
                lines.append(f"- {n}({_json.dumps(a)[:300]}) => {_json.dumps(r)[:800]}")
            except Exception:
                lines.append(f"- {n} => {str(r)[:800]}")
        summary = "Tool results:\n" + "\n".join(lines)
        return (summary, escalated, esc_reason)
    except Exception:
        return (None, False, None)




@router.websocket("/ws/talk")
async def ws_talk(websocket: WebSocket):
    await websocket.accept()
    conn_id = id(websocket)
    _HISTORIES.pop(conn_id, None)
    _EMOTIONS.pop(conn_id, None)
    _evict_sessions_if_needed(conn_id)
    detector = VadTurnDetector()  # lazy singleton model, per-conn iterator state
    utterance = bytearray()
    speaking = False
    current_task: asyncio.Task | None = None
    send_lock = asyncio.Lock()

    async def send_json(obj: dict) -> None:
        async with send_lock:
            await websocket.send_json(obj)

    async def abort_speaking(reason: str = "interrupted") -> None:
        nonlocal speaking, current_task
        # Detach first, then await the cancelled task: this guarantees the
        # old reply pipeline is fully dead before "interrupted" is sent, so
        # a new utterance can't start a second overlapping TTS stream.
        task = current_task
        current_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if speaking:
            speaking = False
            try:
                await send_json({"type": reason})
            except Exception:
                pass

    async def process_utterance(pcm: bytes) -> None:
        """Transcribe -> chat -> TTS stream. Errors -> {"type":"error"}; no drop."""
        nonlocal speaking
        try:
            settings = get_settings()
            key = (settings.GROQ_API_KEY or "").strip()
            if not key:
                await send_json(
                    {"type": "error", "message": "voice brain not configured"}
                )
                return
            if not pcm:
                return
            # Emotion (additive): prosody straight from the utterance PCM.
            # Never fatal — failures leave _prosody None -> neutral later.
            _prosody: dict | None = None
            if _EMOTION_AVAILABLE:
                try:
                    _prosody = analyze_prosody(bytes(pcm))
                except Exception:
                    _prosody = None
            try:
                wav = pcm16_to_wav(pcm)
            except Exception as e:
                await send_json({"type": "error", "message": f"audio prep: {e}"})
                return
            try:
                text = await groq_transcribe(wav, key)
            except Exception as e:
                await send_json({"type": "error", "message": f"stt: {e}"[:200]})
                return
            text = (text or "").strip()
            if not text:
                await send_json({"type": "error", "message": "empty transcript"})
                return
            # Emotion state fuses prosody with the transcript; neutral on failure.
            emotion_state = "neutral"
            emotion_conf = 0.5
            if _EMOTION_AVAILABLE:
                try:
                    _pros = (
                        _prosody
                        if isinstance(_prosody, dict)
                        else analyze_prosody(bytes(pcm))
                    )
                    _cls = classify_state(_pros or {}, text)
                    emotion_state = str((_cls or {}).get("state") or "neutral")
                    emotion_conf = float((_cls or {}).get("confidence", 0.5))
                    if emotion_state not in EMPATHY_POLICY:
                        emotion_state = "neutral"
                except Exception:
                    emotion_state = "neutral"
                    emotion_conf = 0.5
            try:
                _emotion_append(conn_id, emotion_state, emotion_conf)
            except Exception:
                pass
            await send_json(
                {"type": "transcript_final", "text": text, "emotion": emotion_state}
            )
            try:
                await send_json(
                    {
                        "type": "emotion",
                        "state": emotion_state,
                        "confidence": emotion_conf,
                    }
                )
            except Exception:
                pass
            # Empathy policy steers tone (LLM addon) and voice (TTS rate/pitch).
            empathy_addon = ""
            tts_rate, tts_pitch = "+0%", "+0Hz"
            empathy_applied = False
            if _EMOTION_AVAILABLE:
                try:
                    _pol = (EMPATHY_POLICY or {}).get(emotion_state) or {}
                    if str(_pol.get("prompt_addon") or "").strip():
                        empathy_addon = str(_pol["prompt_addon"]).strip()
                        empathy_applied = True
                    tts_rate = str(_pol.get("tts_rate") or "+0%")
                    tts_pitch = str(_pol.get("tts_pitch") or "+0Hz")
                except Exception:
                    empathy_addon = ""
                    tts_rate, tts_pitch = "+0%", "+0Hz"
                    empathy_applied = False
            hist = _history_for(conn_id)
            # Callable tools pass FIRST (short router; last 4 turns + transcript).
            # Silent fallback to plain chat when the LLM tools call is unavailable.
            # GATED: the tool pass costs a full extra LLM round-trip, so only
            # run it when the transcript smells like tool work (contact details,
            # booking/pricing intent, escalation). Normal chat skips straight
            # to streaming reply.
            tool_summary: str | None = None
            tool_escalated = False
            tool_esc_reason: str | None = None
            if _needs_tools(text):
                try:
                    tool_summary, tool_escalated, tool_esc_reason = (
                        await _voice_run_tool_pass(text, hist)
                    )
                except Exception:
                    tool_summary, tool_escalated, tool_esc_reason = None, False, None
            messages = [*hist, {"role": "user", "content": text}]
            if empathy_addon or tool_summary:
                # groq_chat() prepends its own system prompt and forwards any
                # extra system-role entries, so addons ride along untouched.
                messages = [*hist]
                if empathy_addon:
                    messages.append({"role": "system", "content": empathy_addon})
                if tool_summary:
                    messages.append({"role": "system", "content": tool_summary})
                messages.append({"role": "user", "content": text})
            # Streaming replies (perceived latency): stream tokens, split on
            # sentence boundaries (. ! ?) and synthesize each sentence at once
            # via the existing EdgeTTSVoice path. Compat: reply_text carries the
            # FULL text once complete; audio_start precedes the first chunk and
            # audio_end follows the last. New: reply_delta per token batch and
            # sentence_start per sentence. Any stream failure before audio falls
            # back to the non-stream path below; mid-way failures finalize the
            # partial so the caller is never left hanging. Barge-in works
            # between sentences via task cancellation at the awaits.
            _stream_system = " ".join(
                p.strip()
                for p in [CHAT_SYSTEM_PROMPT, empathy_addon or "",
                          str(tool_summary or "")]
                if p and p.strip()
            )
            _prompt_lines: list[str] = []
            for _m in hist:
                try:
                    _r = (_m or {}).get("role")
                    _c = str((_m or {}).get("content") or "").strip()
                    if _r in ("user", "assistant") and _c:
                        _prompt_lines.append(
                            f"{'Caller' if _r == 'user' else 'Assistant'}: {_c}"
                        )
                except Exception:
                    continue
            _prompt_lines.append(f"Caller: {text}")
            _stream_prompt = "\n".join(_prompt_lines)
            try:
                from app.services.llm import complete_stream as _complete_stream

                _full = ""
                _pending = ""
                _sent_idx = 0
                _audio_started = False
                _voice_first: str | None = None
                _stream_provider = EdgeTTSVoice()

                async def _speak_sentence(_sentence: str) -> None:
                    nonlocal _audio_started, _voice_first, speaking, _sent_idx
                    try:
                        await send_json({"type": "sentence_start",
                                         "index": _sent_idx})
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        pass
                    try:
                        _mp3, _v = await _stream_provider.speak(
                            _sentence, rate=tts_rate, pitch=tts_pitch
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as _e:
                        try:
                            await send_json({"type": "error",
                                             "message": f"tts: {_e}"[:200]})
                        except Exception:
                            pass
                        _sent_idx += 1
                        return
                    if not _mp3:
                        _sent_idx += 1
                        return
                    if _voice_first is None:
                        _voice_first = _v
                    if not _audio_started:
                        _audio_started = True
                        speaking = True
                        try:
                            await send_json({"type": "audio_start", "voice": _v})
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            pass
                    try:
                        for _i in range(0, len(_mp3), _MP3_CHUNK):
                            async with send_lock:
                                await websocket.send_bytes(
                                    _mp3[_i : _i + _MP3_CHUNK]
                                )
                    except asyncio.CancelledError:
                        raise
                    except Exception as _e:
                        try:
                            await send_json({"type": "error",
                                             "message": f"stream: {_e}"[:200]})
                        except Exception:
                            pass
                        raise
                    _sent_idx += 1

                try:
                    async for _delta in _complete_stream(
                        _stream_prompt, system=_stream_system,
                        max_tokens=180, temperature=0.3,
                    ):
                        if _delta:
                            _full += _delta
                            _pending += _delta
                            try:
                                await send_json({"type": "reply_delta",
                                                 "text": _delta})
                            except asyncio.CancelledError:
                                raise
                            except Exception:
                                pass
                            _ready, _pending = _drain_complete_sentences(_pending)
                            for _s in _ready:
                                await _speak_sentence(_s)
                except asyncio.CancelledError:
                    raise
                except Exception as _se:
                    if not _audio_started and not _full.strip():
                        raise
                    if _full.strip():
                        try:
                            _tail0 = (_pending or "").strip()
                            if _tail0:
                                await _speak_sentence(_tail0)
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            pass
                        _partial = _full.strip()
                        _history_append(conn_id, "user", text)
                        _history_append(conn_id, "assistant", _partial)
                        _reply_obj_p: dict = {
                            "type": "reply_text",
                            "text": _partial,
                            "emotion": emotion_state,
                            "empathy_applied": empathy_applied,
                        }
                        if tool_escalated:
                            _reply_obj_p["escalation_suggested"] = True
                            _reply_obj_p["reason"] = (
                                tool_esc_reason or "office follow-up requested"
                            )
                        elif _EMOTION_AVAILABLE:
                            try:
                                _adapted_p = adapt(_emotion_timeline(conn_id))
                                if (isinstance(_adapted_p, dict)
                                        and _adapted_p.get("escalate")):
                                    _reply_obj_p["escalation_suggested"] = True
                                    _reply_obj_p["reason"] = str(
                                        _adapted_p.get("reason")
                                        or "repeated frustrated/upset turns"
                                    )
                            except Exception:
                                pass
                        try:
                            await send_json(_reply_obj_p)
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            pass
                        if _audio_started:
                            try:
                                await send_json({"type": "audio_end"})
                            except Exception:
                                pass
                        speaking = False
                        try:
                            await send_json({"type": "state", "state": "idle"})
                        except Exception:
                            pass
                        return
                    raise
                _full = (_full or "").strip()
                if not _full:
                    raise RuntimeError("empty stream reply")
                _tail_ready, _pending = _drain_complete_sentences(_pending)
                for _s in _tail_ready:
                    await _speak_sentence(_s)
                _tail = (_pending or "").strip()
                if _tail:
                    await _speak_sentence(_tail)
                if not _audio_started:
                    raise RuntimeError("tts empty audio")
                _history_append(conn_id, "user", text)
                _history_append(conn_id, "assistant", _full)
                _reply_obj_s: dict = {
                    "type": "reply_text",
                    "text": _full,
                    "emotion": emotion_state,
                    "empathy_applied": empathy_applied,
                }
                if tool_escalated:
                    _reply_obj_s["escalation_suggested"] = True
                    _reply_obj_s["reason"] = (
                        tool_esc_reason or "office follow-up requested"
                    )
                elif _EMOTION_AVAILABLE:
                    try:
                        _adapted_s = adapt(_emotion_timeline(conn_id))
                        if (isinstance(_adapted_s, dict)
                                and _adapted_s.get("escalate")):
                            _reply_obj_s["escalation_suggested"] = True
                            _reply_obj_s["reason"] = str(
                                _adapted_s.get("reason")
                                or "repeated frustrated/upset turns"
                            )
                    except Exception:
                        pass
                await send_json(_reply_obj_s)
                try:
                    await send_json({"type": "audio_end"})
                except asyncio.CancelledError:
                    raise
                except Exception as _e:
                    await send_json({"type": "error",
                                     "message": f"stream: {_e}"[:200]})
                speaking = False
                try:
                    await send_json({"type": "state", "state": "idle"})
                except Exception:
                    pass
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # fall through to the non-stream path below
            try:
                reply = await groq_chat(messages, key)
            except Exception as e:
                await send_json({"type": "error", "message": f"chat: {e}"[:200]})
                return
            reply = (reply or "").strip()
            if not reply:
                await send_json({"type": "error", "message": "empty reply"})
                return
            _history_append(conn_id, "user", text)
            _history_append(conn_id, "assistant", reply)
            reply_obj: dict = {
                "type": "reply_text",
                "text": reply,
                "emotion": emotion_state,
                "empathy_applied": empathy_applied,
            }
            if tool_escalated:
                reply_obj["escalation_suggested"] = True
                reply_obj["reason"] = (
                    tool_esc_reason or "office follow-up requested"
                )
            elif _EMOTION_AVAILABLE:
                try:
                    _adapted = adapt(_emotion_timeline(conn_id))
                    if isinstance(_adapted, dict) and _adapted.get("escalate"):
                        # Suggest only — the Retell module owns any transfer.
                        reply_obj["escalation_suggested"] = True
                        reply_obj["reason"] = str(
                            _adapted.get("reason")
                            or "repeated frustrated/upset turns"
                        )
                except Exception:
                    pass
            await send_json(reply_obj)
            # TTS via existing EdgeTTS provider.
            try:
                provider = EdgeTTSVoice()
                mp3, voice_used = await provider.speak(
                    reply, rate=tts_rate, pitch=tts_pitch
                )
            except Exception as e:
                await send_json({"type": "error", "message": f"tts: {e}"[:200]})
                return
            if not mp3:
                await send_json({"type": "error", "message": "tts empty audio"})
                return
            speaking = True
            try:
                await send_json({"type": "audio_start", "voice": voice_used})
                for i in range(0, len(mp3), _MP3_CHUNK):
                    async with send_lock:
                        await websocket.send_bytes(mp3[i : i + _MP3_CHUNK])
                await send_json({"type": "audio_end"})
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await send_json({"type": "error", "message": f"stream: {e}"[:200]})
            finally:
                speaking = False
            try:
                await send_json({"type": "state", "state": "idle"})
            except Exception:
                pass
        except asyncio.CancelledError:
            speaking = False
            raise
        except Exception as e:  # absolute net — never drop socket on error
            speaking = False
            try:
                await send_json({"type": "error", "message": str(e)[:200]})
            except Exception:
                pass

    try:
        while True:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                break
            except Exception:
                break  # transport error — close loop, not a crash
            # Binary PCM frame.
            if message.get("bytes") is not None:
                chunk: bytes = message["bytes"] or b""
                if not chunk:
                    continue
                # Cap utterance at 20s; force endpoint when exceeded.
                room = _MAX_UTTERANCE_BYTES - len(utterance)
                if room <= 0:
                    forced = bytes(utterance)
                    utterance.clear()
                    detector.reset()
                    if forced and (
                        current_task is None or current_task.done()
                    ):
                        current_task = asyncio.create_task(
                            process_utterance(forced)
                        )
                    continue
                utterance.extend(chunk[:room])
                try:
                    event = detector.feed(chunk)
                except Exception:
                    event = None
                if event == "speech_start":
                    await abort_speaking("interrupted")
                    try:
                        await send_json({"type": "state", "state": "listening"})
                    except Exception:
                        pass
                elif event == "speech_end":
                    pcm = bytes(utterance)
                    utterance.clear()
                    detector.reset()
                    if pcm and (
                        current_task is None or current_task.done()
                    ):
                        current_task = asyncio.create_task(
                            process_utterance(pcm)
                        )
                elif len(utterance) >= _MAX_UTTERANCE_BYTES:
                    # 20s cap reached without VAD end — force endpoint.
                    pcm = bytes(utterance)
                    utterance.clear()
                    detector.reset()
                    if pcm and (
                        current_task is None or current_task.done()
                    ):
                        current_task = asyncio.create_task(
                            process_utterance(pcm)
                        )
                continue
            # Text control frame.
            text = message.get("text")
            if text is None:
                continue
            try:
                data = json.loads(text)
            except Exception:
                continue
            mtype = (data.get("type") or "").strip().lower()
            if mtype == "ping":
                try:
                    await send_json({"type": "pong"})
                except Exception:
                    pass
            elif mtype in ("barge-in", "barge_in", "bargein", "interrupt"):
                await abort_speaking("interrupted")
                try:
                    await send_json({"type": "state", "state": "listening"})
                except Exception:
                    pass
                utterance.clear()
                try:
                    detector.reset()
                except Exception:
                    pass
            # Unknown text types are ignored (keep socket open).
    finally:
        try:
            # Cancel AND await: avoids "task destroyed but pending" warnings
            # and unretrieved-exception noise on dropped calls.
            task = current_task
            current_task = None
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        except Exception:
            pass
        _HISTORIES.pop(conn_id, None)
        _EMOTIONS.pop(conn_id, None)
        try:
            await websocket.close()
        except Exception:
            pass
