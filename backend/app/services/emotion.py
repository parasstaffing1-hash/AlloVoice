"""Hume-style emotion detection + empathetic adaptation (local, numpy-only).

No downloads, no torch, no extra pip packages — numpy + stdlib only.
Every public function is total (never raises); unexpected input degrades
to neutral defaults so the realtime voice hot path stays alive.

Pipeline
--------
1. ``analyze_prosody`` — acoustic features from raw Int16LE mono PCM.
2. ``classify_state`` — fuse prosody with an optional keyword sentiment
   scan into one of 7 caller states.
3. ``EMPATHY_POLICY`` — per-state LLM tone steering + edge-tts rate/pitch.
4. ``adapt`` — session-level mood + escalation flag over a turn timeline.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Framing / normalisation constants (documented thresholds)
# ---------------------------------------------------------------------------

_FRAME_SEC = 0.02            # 20 ms analysis frames
_VOICED_RMS_THRESHOLD = 0.02  # frame RMS above this counts as voiced speech
_LOUD_RMS_REF = 0.30        # RMS of loud speech; mean energy is scaled by this
_ZCR_REF = 0.30             # zero-crossing rate of very tense/noisy speech
_CV_REF = 1.5               # coeff. of variation ref for energy-burstiness

_STATES = ("calm", "neutral", "rushed", "frustrated", "upset", "warm", "worried")

# Keyword sentiment markers (case-insensitive substring match).
FRUSTRATION_MARKERS = ("damn", "ridiculous", "waiting ages", "useless")
URGENCY_MARKERS = ("emergency", "asap", "flooding", "no heating")
WARMTH_MARKERS = ("thanks", "great", "lovely")
WORRY_MARKERS = ("worried", "expensive", "how much")

# Escalation states: 2+ of these in the last 3 turns suggests a human handoff.
_ESCALATION_STATES = ("frustrated", "upset")

_NEUTRAL_PROSODY = {
    "arousal": 0.4,
    "tension": 0.3,
    "mean_energy": 0.0,
    "max_energy": 0.0,
    "energy_variance": 0.0,
    "zcr": 0.0,
    "tempo": 0.0,
    "pause_ratio": 0.5,
}


def _clamp01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0


def analyze_prosody(pcm16_bytes: bytes, sample_rate: int = 16000) -> dict:
    """Acoustic prosody from raw Int16LE mono PCM. Never raises.

    Features (20 ms non-overlapping frames):
      - mean/max frame RMS energy + energy variance (burstiness)
      - zero-crossing rate (mean over voiced frames; harshness proxy)
      - speech tempo = voiced frames per second of audio
      - pause ratio = share of frames below the voiced RMS threshold

    Mapping (all refs are module constants above):
      - arousal = 0.5 * min(1, mean_rms/0.30) + 0.3 * voiced_ratio
                + 0.2 * min(1, zcr/0.30)
      - tension = 0.45 * min(1, cv/1.5) + 0.35 * min(1, mean_rms/0.30)
                + 0.2 * min(1, zcr/0.30),  where cv = std(rms)/mean(rms)

    Silence/empty input -> arousal 0.0, tension 0.0. Garbage input that
    breaks decoding -> neutral defaults (arousal 0.4, tension 0.3).
    """
    try:
        import numpy as np

        if not pcm16_bytes or len(pcm16_bytes) < 2:
            return {
                "arousal": 0.0, "tension": 0.0, "mean_energy": 0.0,
                "max_energy": 0.0, "energy_variance": 0.0, "zcr": 0.0,
                "tempo": 0.0, "pause_ratio": 1.0,
            }
        sr = int(sample_rate) or 16000
        if sr <= 0:
            sr = 16000
        samples = (
            np.frombuffer(bytes(pcm16_bytes), dtype=np.int16)
            .astype(np.float32) / 32768.0
        )
        if samples.size == 0:
            return {
                "arousal": 0.0, "tension": 0.0, "mean_energy": 0.0,
                "max_energy": 0.0, "energy_variance": 0.0, "zcr": 0.0,
                "tempo": 0.0, "pause_ratio": 1.0,
            }
        try:
            samples = samples - float(np.mean(samples))  # drop DC bias
        except Exception:
            pass
        frame_len = max(1, int(sr * _FRAME_SEC))
        n_frames = int(samples.size // frame_len)
        if n_frames == 0:  # sub-frame utterance: analyse as one frame
            frames = samples.reshape(1, -1)
        else:
            frames = samples[: n_frames * frame_len].reshape(n_frames, frame_len)
        rms = np.sqrt(np.mean(frames * frames, axis=1))
        with np.errstate(invalid="ignore"):
            prod = frames[:, :-1] * frames[:, 1:]
            zcr = np.mean(prod < 0.0, axis=1)
        voiced = rms > _VOICED_RMS_THRESHOLD
        voiced_ratio = float(np.mean(voiced)) if voiced.size else 0.0
        pause_ratio = 1.0 - voiced_ratio
        mean_e = float(np.mean(rms))
        max_e = float(np.max(rms))
        var_e = float(np.var(rms))
        std_e = float(np.std(rms))
        if np.any(voiced):
            zcr_mean = float(np.mean(zcr[voiced]))
        else:
            zcr_mean = 0.0
        duration_sec = float(samples.size) / float(sr)
        tempo = float(np.sum(voiced)) / duration_sec if duration_sec > 0 else 0.0

        energy_norm = min(1.0, mean_e / _LOUD_RMS_REF)
        zcr_norm = min(1.0, zcr_mean / _ZCR_REF)
        cv = std_e / (mean_e + 1e-6)
        cv_norm = min(1.0, cv / _CV_REF)
        arousal = 0.5 * energy_norm + 0.3 * voiced_ratio + 0.2 * zcr_norm
        tension = 0.45 * cv_norm + 0.35 * energy_norm + 0.2 * zcr_norm
        return {
            "arousal": round(_clamp01(arousal), 4),
            "tension": round(_clamp01(tension), 4),
            "mean_energy": round(float(mean_e), 4),
            "max_energy": round(float(max_e), 4),
            "energy_variance": round(float(var_e), 6),
            "zcr": round(float(zcr_mean), 4),
            "tempo": round(float(tempo), 2),
            "pause_ratio": round(_clamp01(pause_ratio), 4),
        }
    except Exception:
        return dict(_NEUTRAL_PROSODY)


def _keyword_hits(text_lower: str, markers: tuple) -> list:
    return [m for m in markers if m in text_lower]


def classify_state(prosody: dict, text: str | None) -> dict:
    """Fuse prosody with keyword sentiment into one caller state. Never raises.

    Keyword priority (first match wins — deterministic):
      1. frustration markers -> ``frustrated`` (base confidence 0.85)
      2. urgency markers     -> ``rushed``     (base 0.80)
      3. warmth markers      -> ``warm``       (base 0.85)
      4. worry markers       -> ``worried``    (base 0.80)
    Keyword confidence gains +0.05 per extra marker and +0.05 when the
    matching prosody dimension agrees (tension>=0.5 for frustration,
    arousal>=0.6 for urgency), capped at 0.95.

    Prosody-only fallback (no keyword hit):
      - arousal >= 0.65 and tension >= 0.55      -> ``frustrated`` (0.65)
      - tension >= 0.65 (and not the above)     -> ``upset``      (0.60)
      - arousal >= 0.60 and pause_ratio <= 0.40 -> ``rushed``     (0.60)
      - arousal <= 0.35 and tension <= 0.35     -> ``calm``       (0.60)
      - otherwise                               -> ``neutral``    (0.50)

    Returns ``{state, confidence, signals}`` where signals lists the
    matched keywords and the prosody values that drove the decision.
    """
    try:
        prosody = prosody if isinstance(prosody, dict) else {}
        try:
            arousal = float(prosody.get("arousal", 0.4))
        except Exception:
            arousal = 0.4
        try:
            tension = float(prosody.get("tension", 0.3))
        except Exception:
            tension = 0.3
        try:
            pause_ratio = float(prosody.get("pause_ratio", 0.5))
        except Exception:
            pause_ratio = 0.5
        text_lower = (text or "").lower() if isinstance(text, str) else ""

        signals = [
            f"prosody:arousal={arousal:.2f}",
            f"prosody:tension={tension:.2f}",
            f"prosody:pause_ratio={pause_ratio:.2f}",
        ]

        frust = _keyword_hits(text_lower, FRUSTRATION_MARKERS)
        urg = _keyword_hits(text_lower, URGENCY_MARKERS)
        warm = _keyword_hits(text_lower, WARMTH_MARKERS)
        wor = _keyword_hits(text_lower, WORRY_MARKERS)

        if frust:
            conf = 0.85 + 0.05 * (len(frust) - 1) + (0.05 if tension >= 0.5 else 0.0)
            signals += [f"keyword:frustration:{m}" for m in frust]
            return {"state": "frustrated", "confidence": round(min(0.95, conf), 2),
                    "signals": signals}
        if urg:
            conf = 0.80 + 0.05 * (len(urg) - 1) + (0.05 if arousal >= 0.6 else 0.0)
            signals += [f"keyword:urgency:{m}" for m in urg]
            return {"state": "rushed", "confidence": round(min(0.95, conf), 2),
                    "signals": signals}
        if warm:
            conf = 0.85 + 0.05 * (len(warm) - 1)
            signals += [f"keyword:warmth:{m}" for m in warm]
            return {"state": "warm", "confidence": round(min(0.95, conf), 2),
                    "signals": signals}
        if wor:
            conf = 0.80 + 0.05 * (len(wor) - 1)
            signals += [f"keyword:worry:{m}" for m in wor]
            return {"state": "worried", "confidence": round(min(0.95, conf), 2),
                    "signals": signals}

        if arousal >= 0.65 and tension >= 0.55:
            signals.append("rule:hot-and-tense->frustrated")
            return {"state": "frustrated", "confidence": 0.65, "signals": signals}
        if tension >= 0.65:
            signals.append("rule:tense-but-not-hot->upset")
            return {"state": "upset", "confidence": 0.60, "signals": signals}
        if arousal >= 0.60 and pause_ratio <= 0.40:
            signals.append("rule:loud-and-dense->rushed")
            return {"state": "rushed", "confidence": 0.60, "signals": signals}
        if arousal <= 0.35 and tension <= 0.35:
            signals.append("rule:quiet-and-steady->calm")
            return {"state": "calm", "confidence": 0.60, "signals": signals}
        signals.append("rule:fallback->neutral")
        return {"state": "neutral", "confidence": 0.50, "signals": signals}
    except Exception:
        return {"state": "neutral", "confidence": 0.5, "signals": ["error:fallback"]}


# ---------------------------------------------------------------------------
# Empathy policy: per-state LLM steering + edge-tts voice tuning.
# rate/pitch use edge-tts SSML-style strings: rate "[+-]N%", pitch "[+-]NHz".
# ---------------------------------------------------------------------------

EMPATHY_POLICY: dict = {
    "calm": {
        "prompt_addon": (
            "The caller sounds calm. Keep your steady, unhurried tone "
            "and confirm each step clearly."
        ),
        "tts_rate": "+0%",
        "tts_pitch": "+0Hz",
        "style_note": "Steady and clear; no extra softening needed.",
    },
    "neutral": {
        "prompt_addon": (
            "The caller sounds neutral. Stay professional and concise, "
            "and answer the question directly."
        ),
        "tts_rate": "+0%",
        "tts_pitch": "+0Hz",
        "style_note": "Professional baseline; direct answer first.",
    },
    "rushed": {
        "prompt_addon": (
            "The caller sounds rushed. Be concise: give the key point first "
            "in one short sentence and skip background detail."
        ),
        "tts_rate": "+5%",
        "tts_pitch": "+0Hz",
        "style_note": "Concise and front-loaded; no small talk.",
    },
    "frustrated": {
        "prompt_addon": (
            "The caller sounds frustrated. Start with a brief apology, "
            "acknowledge the specific issue, then give one clear fix."
        ),
        "tts_rate": "-10%",
        "tts_pitch": "-2Hz",
        "style_note": "Apology-first, slower and lower; never defensive.",
    },
    "upset": {
        "prompt_addon": (
            "The caller sounds upset. Be gentle and patient: acknowledge how "
            "they feel, speak slowly, and offer one clear next step."
        ),
        "tts_rate": "-5%",
        "tts_pitch": "-2Hz",
        "style_note": "Gentle and patient; one clear next step only.",
    },
    "warm": {
        "prompt_addon": (
            "The caller sounds warm and friendly. Match their warmth with a "
            "friendly tone while staying concise."
        ),
        "tts_rate": "+0%",
        "tts_pitch": "+2Hz",
        "style_note": "Friendly mirroring; stay concise.",
    },
    "worried": {
        "prompt_addon": (
            "The caller sounds worried. Reassure them first, state any costs "
            "or timeframes upfront, and give one clear next step."
        ),
        "tts_rate": "-5%",
        "tts_pitch": "+0Hz",
        "style_note": "Reassuring; costs and timing upfront.",
    },
}


def adapt(session_states: list) -> dict:
    """Session-level mood + escalation flag. Never raises.

    Accepts a timeline of ``{state, confidence, ...}`` dicts (as stored per
    connection, capped at 20) or plain state strings; unknown states are
    ignored. ``mood`` is the dominant (most frequent) state, ties broken by
    recency. ``escalate`` is True when 2+ of the last 3 turns are
    ``frustrated``/``upset`` — the caller (reply event) should then suggest
    a human handoff; this function never triggers a transfer itself.
    """
    try:
        states: list = []
        for item in session_states or []:
            if isinstance(item, dict):
                s = item.get("state")
            else:
                s = item
            s = str(s or "").strip().lower()
            if s in _STATES:
                states.append(s)
        if not states:
            return {"mood": None, "escalate": False, "reason": None,
                    "turns": 0, "counts": {}}
        counts: dict = {}
        for s in states:
            counts[s] = counts.get(s, 0) + 1
        top = max(counts.values())
        mood = None
        for s in reversed(states):  # most recent wins ties
            if counts[s] == top:
                mood = s
                break
        last3 = states[-3:]
        neg = sum(1 for s in last3 if s in _ESCALATION_STATES)
        escalate = neg >= 2
        reason = (
            f"{neg} of last {len(last3)} turns were "
            f"frustrated/upset — human handoff suggested"
            if escalate else None
        )
        return {"mood": mood, "escalate": escalate, "reason": reason,
                "turns": len(states), "counts": counts}
    except Exception:
        return {"mood": None, "escalate": False, "reason": None,
                "turns": 0, "counts": {}}
