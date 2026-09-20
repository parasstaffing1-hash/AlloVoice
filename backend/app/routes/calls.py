"""Retell-style call sessions + post-call analysis + transfer.

Module-dict storage (move to DB tables in production — see NOTE below).
All datetimes are ISO-8601 strings. LLM failures never 500: every
analysis path falls back to a local heuristic.

NOTE (wiring): app/main.py is frozen for this task, so this router is
not auto-registered. To enable, add `calls` to the routes import in
app/main.py and call `app.include_router(calls.router)`.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.models.models import User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/calls", tags=["calls"])

# ─── In-memory storage (production → DB tables) ───────────────────────────────
CALLS: dict[str, dict] = {}
ESCALATIONS: dict[str, dict] = {}

# Emotion service may not exist yet (built by a parallel task) — defensive.
try:  # pragma: no cover - optional dependency
    from app.services import emotion as _emotion_svc  # type: ignore
except Exception:
    _emotion_svc = None  # type: ignore


# ─── Request bodies ───────────────────────────────────────────────────────────
class StartCallBody(BaseModel):
    customer_id: Optional[str] = None
    job_id: Optional[str] = None
    direction: Literal["inbound", "outbound"] = "inbound"
    channel: Literal["realtime", "phone", "demo"] = "demo"


class TurnBody(BaseModel):
    speaker: Literal["caller", "agent"]
    text: str
    emotion: Optional[str] = None
    audio_seconds: Optional[float] = None


class TransferBody(BaseModel):
    reason: str
    oncall_phone: Optional[str] = None


class EndCallBody(BaseModel):
    outcome: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _new_call(data: StartCallBody) -> dict:
    now = _now_iso()
    return {
        "id": str(uuid.uuid4()),
        "customer_id": data.customer_id,
        "job_id": data.job_id,
        "direction": data.direction,
        "channel": data.channel,
        "status": "live",
        "started_at": now,
        "ended_at": None,
        "outcome": None,
        "transferred_at": None,
        "turns": [],
        "emotions": [],
        "analysis": None,
        "escalations": [],
    }


def _get_call_or_404(call_id: str) -> dict:
    call = CALLS.get(call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


def _detect_emotion(text: str) -> Optional[str]:
    """Best-effort emotion detection via the (optional) emotion service."""
    if _emotion_svc is None:
        return None
    try:
        # Parallel-task emotion service exposes
        # classify_state(prosody, text) -> {state, confidence, signals}.
        fn = getattr(_emotion_svc, "classify_state", None)
        if callable(fn):
            try:
                res = fn({}, text)
            except Exception:
                res = None
            if isinstance(res, dict):
                state = res.get("state")
                if isinstance(state, str) and state.strip():
                    return state.strip().lower()
        for fname in ("detect", "detect_emotion", "analyze", "classify",
                      "predict", "score"):
            fn = getattr(_emotion_svc, fname, None)
            if not callable(fn):
                continue
            try:
                res = fn(text)
                if inspect.isawaitable(res):  # pragma: no cover
                    continue  # sync context here; skip async APIs
            except Exception:
                continue
            if isinstance(res, str) and res.strip():
                return res.strip().lower()
            if isinstance(res, dict):
                for key in ("emotion", "label", "dominant",
                            "dominant_emotion", "state"):
                    val = res.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip().lower()
    except Exception:
        return None
    return None


# ─── Heuristic post-call analysis (fallback when LLM unavailable) ─────────────
_POS_WORDS = frozenset(
    "great good excellent happy pleased thanks thank lovely perfect wonderful "
    "amazing brilliant fantastic glad satisfied helpful resolved fixed sorted".split()
)
_NEG_WORDS = frozenset(
    "bad terrible awful angry furious upset annoyed frustrated disappointed "
    "complaint broken fault wrong late never poor useless worst hate refund "
    "cancel cancelled problem issue disgusting shocking".split()
)
_FOLLOWUP_CUES = (
    "call back", "callback", "follow up", "follow-up", "complaint",
    "broken", "not working", "refund", "cancel", "manager", "supervisor",
)


def _score_text(text: str) -> float:
    words = [w.strip(".,!?;:\"'()").lower() for w in (text or "").split()]
    pos = sum(1 for w in words if w in _POS_WORDS)
    neg = sum(1 for w in words if w in _NEG_WORDS)
    return max(-1.0, min(1.0, (pos - neg) * 0.5))


def _heuristic_analysis(call: dict, outcome: Optional[str] = None) -> dict:
    turns = call.get("turns", []) or []
    caller_turns = [t for t in turns if t.get("speaker") == "caller"]
    agent_turns = [t for t in turns if t.get("speaker") == "agent"]

    trend = [_score_text(t.get("text", "")) for t in turns]
    avg = (sum(trend) / len(trend)) if trend else 0.0
    sentiment = "positive" if avg > 0.15 else ("negative" if avg < -0.15 else "neutral")

    if caller_turns:
        first_q = (caller_turns[0].get("text", "") or "")[:160]
        last_q = (caller_turns[-1].get("text", "") or "")[:160]
        summary = (
            f"Call had {len(turns)} turns "
            f"({len(caller_turns)} caller / {len(agent_turns)} agent). "
            f"Caller opened with: \"{first_q}\"."
        )
        if len(caller_turns) > 1:
            summary += f" Call closed with: \"{last_q}\"."
    else:
        summary = (
            f"Call had {len(turns)} turns with no caller speech captured. "
            "Review transcript for detail."
        )

    caller_chars = sum(len(t.get("text", "") or "") for t in caller_turns)
    total_chars = sum(len(t.get("text", "") or "") for t in turns)
    talk_ratio = round(caller_chars / total_chars * 100, 1) if total_chars else 0.0

    key_quotes = [(t.get("text", "") or "")[:160] for t in caller_turns[:2]
                  if (t.get("text", "") or "").strip()]

    full_text = " ".join(t.get("text", "") or "" for t in turns).lower()
    follow_up = (
        sentiment == "negative"
        or any(cue in full_text for cue in _FOLLOWUP_CUES)
    )

    actions = ["Review transcript"]
    if follow_up:
        actions.append("Follow up with caller")

    return {
        "summary": summary,
        "sentiment": sentiment,
        "sentiment_trend": trend,
        "action_items": actions,
        "talk_ratio_caller_pct": talk_ratio,
        "key_quotes": key_quotes,
        "follow_up_suggested": follow_up,
        "outcome": outcome,
        "model": "heuristic",
    }


async def _llm_analysis(call: dict, outcome: Optional[str] = None) -> Optional[dict]:
    """Try LLM analysis; return None on any failure (caller falls back)."""
    try:
        from app.services.llm import complete_json, is_configured
    except Exception:
        return None
    try:
        if not is_configured():
            return None
    except Exception:
        return None

    turns = call.get("turns", []) or []
    if not turns:
        return None
    transcript = "\n".join(
        f"{t.get('speaker', 'caller')}: {(t.get('text', '') or '')[:500]}"
        for t in turns
    )[:6000]
    prompt = (
        "Analyse this customer call transcript and reply with JSON only, "
        "using exactly these keys: summary (2-3 sentences), "
        "sentiment (one of positive|neutral|negative), "
        "sentiment_trend (one float per turn in order, each -1..1), "
        "action_items (list of strings), "
        "talk_ratio_caller_pct (0-100 number), "
        "key_quotes (max 2 short verbatim caller quotes), "
        "follow_up_suggested (boolean).\n"
        f"Outcome: {outcome or 'unknown'}\nTranscript:\n{transcript}"
    )
    system = "You are a call-centre QA analyst. Reply with JSON only."
    try:
        data = await complete_json(prompt, system=system,
                                   max_tokens=800, temperature=0.2)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    heuristic = _heuristic_analysis(call, outcome)
    try:
        sentiment = str(data.get("sentiment", "")).lower().strip()
        if sentiment not in ("positive", "neutral", "negative"):
            sentiment = heuristic["sentiment"]
        raw_trend = data.get("sentiment_trend")
        if isinstance(raw_trend, list):
            trend = []
            for v in raw_trend:
                try:
                    trend.append(max(-1.0, min(1.0, float(v))))
                except (TypeError, ValueError):
                    continue
        else:
            trend = heuristic["sentiment_trend"]
        actions = [str(a)[:200] for a in data.get("action_items", [])
                   if isinstance(a, str) and a.strip()]
        if not actions:
            actions = heuristic["action_items"]
        try:
            talk_ratio = float(data.get("talk_ratio_caller_pct",
                                        heuristic["talk_ratio_caller_pct"]))
            talk_ratio = max(0.0, min(100.0, talk_ratio))
        except (TypeError, ValueError):
            talk_ratio = heuristic["talk_ratio_caller_pct"]
        quotes = [str(q)[:200] for q in data.get("key_quotes", [])
                  if isinstance(q, str) and q.strip()][:2]
        return {
            "summary": str(data.get("summary") or heuristic["summary"])[:1000],
            "sentiment": sentiment,
            "sentiment_trend": trend,
            "action_items": actions,
            "talk_ratio_caller_pct": round(talk_ratio, 1),
            "key_quotes": quotes,
            "follow_up_suggested": bool(data.get("follow_up_suggested", False)),
            "outcome": outcome,
            "model": "llm",
        }
    except Exception:
        return None


async def _send_escalation_sms(to_phone: str, message: str) -> bool:
    """Best-effort Twilio text. Never raises — returns True if accepted."""
    try:
        from app.core.config import get_settings

        s = get_settings()
        sid = ((getattr(s, "TWILIO_ACCOUNT_SID", "") or "").strip())
        token = ((getattr(s, "TWILIO_AUTH_TOKEN", "") or "").strip())
        if not sid or not token:
            return False
        sender = ((getattr(s, "TWILIO_PHONE_NUMBER", "") or "").strip()
                  or (getattr(s, "TWILIO_SENDER_ID", "") or "VoiceField").strip())
        try:
            from app.services.phone import normalize_uk_phone

            to_e164 = normalize_uk_phone(to_phone)
        except Exception:
            to_e164 = (to_phone or "").strip()
        if not to_e164:
            return False
        import httpx

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                auth=(sid, token),
                data={"To": to_e164, "From": sender, "Body": message[:1600]},
            )
            return 200 <= resp.status_code < 300
    except Exception:
        return False


# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.post("/start")
async def start_call(
    data: StartCallBody,
    current_user: User = Depends(get_current_user),
):
    call = _new_call(data)
    CALLS[call["id"]] = call
    return call


@router.post("/{call_id}/turn")
async def add_turn(
    call_id: str,
    data: TurnBody,
    current_user: User = Depends(get_current_user),
):
    call = _get_call_or_404(call_id)
    if call.get("status") != "live":
        raise HTTPException(status_code=400, detail="Call is not live")
    if not (data.text or "").strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    idx = len(call["turns"])
    ts = _now_iso()
    emotion_val = (data.emotion or "").strip().lower() or None
    if emotion_val is None:
        try:
            emotion_val = _detect_emotion(data.text)
        except Exception:
            emotion_val = None
    turn = {
        "index": idx,
        "speaker": data.speaker,
        "text": data.text,
        "emotion": emotion_val,
        "audio_seconds": data.audio_seconds,
        "at": ts,
    }
    call["turns"].append(turn)
    if emotion_val:
        call["emotions"].append(
            {"turn_index": idx, "emotion": emotion_val, "at": ts}
        )
    return {"ok": True, "turn_index": idx}


@router.post("/{call_id}/transfer")
async def transfer_call(
    call_id: str,
    data: TransferBody,
    current_user: User = Depends(get_current_user),
):
    call = _get_call_or_404(call_id)
    if call.get("status") == "ended":
        raise HTTPException(status_code=400, detail="Call already ended")
    if not (data.reason or "").strip():
        raise HTTPException(status_code=422, detail="reason must not be empty")
    now = _now_iso()
    escalation = {
        "id": str(uuid.uuid4()),
        "call_id": call_id,
        "reason": data.reason,
        "at": now,
    }
    ESCALATIONS[escalation["id"]] = escalation
    call["escalations"].append(escalation)
    call["status"] = "transferred"
    call["transferred_at"] = now

    sms_sent = False
    if (data.oncall_phone or "").strip():
        try:
            sms_sent = await _send_escalation_sms(
                data.oncall_phone.strip(),
                f"VoiceField escalation: {data.reason} (call {call_id})",
            )
        except Exception:
            sms_sent = False
    escalation["sms_sent"] = sms_sent
    return {"escalation_id": escalation["id"], "status": "transferred",
            "sms_sent": sms_sent}


@router.post("/{call_id}/end")
async def end_call(
    call_id: str,
    data: EndCallBody,
    current_user: User = Depends(get_current_user),
):
    call = _get_call_or_404(call_id)
    outcome = (data.outcome or "").strip() or None
    try:
        analysis = await _llm_analysis(call, outcome)
    except Exception:
        analysis = None
    if analysis is None:
        try:
            analysis = _heuristic_analysis(call, outcome)
        except Exception:
            analysis = {
                "summary": "Call ended. Review transcript for detail.",
                "sentiment": "neutral",
                "sentiment_trend": [],
                "action_items": ["Review transcript"],
                "talk_ratio_caller_pct": 0.0,
                "key_quotes": [],
                "follow_up_suggested": False,
                "outcome": outcome,
                "model": "heuristic",
            }
    call["analysis"] = analysis
    call["status"] = "ended"
    call["ended_at"] = _now_iso()
    call["outcome"] = outcome
    return call


@router.get("/")
async def list_calls(
    current_user: User = Depends(get_current_user),
):
    ordered = sorted(CALLS.values(),
                     key=lambda c: c.get("started_at", ""), reverse=True)
    return [
        {
            "id": c["id"],
            "started_at": c.get("started_at"),
            "ended_at": c.get("ended_at"),
            "status": c.get("status"),
            "turns_count": len(c.get("turns", []) or []),
            "sentiment": (c.get("analysis") or {}).get("sentiment"),
            "customer_id": c.get("customer_id"),
            "job_id": c.get("job_id"),
        }
        for c in ordered
    ]


@router.get("/{call_id}")
async def get_call(
    call_id: str,
    current_user: User = Depends(get_current_user),
):
    call = _get_call_or_404(call_id)
    return {**call, "emotion_timeline": call.get("emotions", [])}
