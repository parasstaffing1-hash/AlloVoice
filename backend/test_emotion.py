"""Emotion-module checks: no mic/server needed (synthetic PCM via numpy).

Covers: prosody ordering (rushed.arousal > calm.arousal, silent tension ~0),
keyword fusion (-> frustrated / warm), EMPATHY_POLICY coverage + rate/pitch
format, adapt() escalation on repeated frustration. Prints PASS/FAIL lines;
exits non-zero on any failure.
"""

import re
import sys

import numpy as np

from app.services.emotion import (
    EMPATHY_POLICY,
    adapt,
    analyze_prosody,
    classify_state,
)

SR = 16000
FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"PASS: {name}" + (f" ({detail})" if detail else ""))
    else:
        print(f"FAIL: {name}" + (f" ({detail})" if detail else ""))
        FAILURES.append(name)


def _to_pcm16(x: np.ndarray) -> bytes:
    x = np.clip(x, -1.0, 1.0)
    return (x * 32767).astype(np.int16).tobytes()


def make_calm(sr: int = SR) -> bytes:
    """Low-variance sine-ish voiced segments with real pauses."""
    rng = np.random.default_rng(7)
    t = np.arange(int(2.0 * sr)) / sr
    audio = np.zeros_like(t)
    for start in (0.10, 0.80, 1.45):
        i0, i1 = int(start * sr), int((start + 0.40) * sr)
        tt = t[i0:i1] - t[i0]
        audio[i0:i1] = 0.25 * np.sin(2 * np.pi * 180 * tt)
    audio = audio + 0.005 * rng.standard_normal(audio.shape)
    return _to_pcm16(audio)


def make_rushed(sr: int = SR) -> bytes:
    """Dense high-energy bursts with few pauses + harsh edges."""
    rng = np.random.default_rng(7)
    t = np.arange(int(2.0 * sr)) / sr
    audio = np.zeros_like(t)
    start = 0.0
    on = True
    while start < 2.0:
        dur = 0.35 if on else 0.05
        i0, i1 = int(start * sr), int(min(2.0, start + dur) * sr)
        if on:
            tt = t[i0:i1] - (t[i0] if i1 > i0 else 0.0)
            audio[i0:i1] = (0.55 * np.sign(np.sin(2 * np.pi * 300 * tt))
                            + 0.15 * rng.standard_normal(i1 - i0))
        start += dur
        on = not on
    return _to_pcm16(audio)


def make_silent(sr: int = SR) -> bytes:
    return _to_pcm16(np.zeros(int(2.0 * sr)))


def main() -> int:
    calm_pcm = make_calm()
    rushed_pcm = make_rushed()
    silent_pcm = make_silent()

    calm = analyze_prosody(calm_pcm, SR)
    rushed = analyze_prosody(rushed_pcm, SR)
    silent = analyze_prosody(silent_pcm, SR)
    print(f"calm:   arousal={calm['arousal']} tension={calm['tension']} "
          f"pause={calm['pause_ratio']} tempo={calm['tempo']}")
    print(f"rushed: arousal={rushed['arousal']} tension={rushed['tension']} "
          f"pause={rushed['pause_ratio']} tempo={rushed['tempo']}")
    print(f"silent: arousal={silent['arousal']} tension={silent['tension']} "
          f"pause={silent['pause_ratio']}")

    for key in ("arousal", "tension", "mean_energy", "max_energy",
                "energy_variance", "zcr", "tempo", "pause_ratio"):
        check(f"prosody keys include {key}", key in calm and key in rushed)

    check("rushed.arousal > calm.arousal",
          rushed["arousal"] > calm["arousal"],
          f"rushed={rushed['arousal']} calm={calm['arousal']}")
    check("silent tension ~0", silent["tension"] <= 0.1,
          f"tension={silent['tension']}")
    check("silent arousal ~0", silent["arousal"] <= 0.1,
          f"arousal={silent['arousal']}")
    check("arousal/tension bounded 0..1",
          all(0.0 <= v <= 1.0 for v in (
              calm["arousal"], calm["tension"],
              rushed["arousal"], rushed["tension"],
              silent["arousal"], silent["tension"])))

    # Garbage / empty input never raises and stays bounded.
    for bad in (b"", b"\x00", bytes(10)):
        try:
            got = analyze_prosody(bad, SR)
            ok = isinstance(got, dict) and 0.0 <= got["arousal"] <= 1.0
        except Exception:
            ok = False
        check(f"analyze_prosody never raises on {len(bad)}-byte input", ok)

    f = classify_state({"arousal": 0.4, "tension": 0.4, "pause_ratio": 0.5},
                       "this is ridiculous, waiting ages")
    check("keyword frustration -> frustrated",
          f["state"] == "frustrated", f"{f['state']} {f['confidence']}")
    w = classify_state({"arousal": 0.4, "tension": 0.3, "pause_ratio": 0.5},
                       "thanks, that's lovely")
    check("keyword warmth -> warm", w["state"] == "warm",
          f"{w['state']} {w['confidence']}")
    u = classify_state({"arousal": 0.4, "tension": 0.4, "pause_ratio": 0.5},
                       "it's an emergency, flooding asap")
    check("keyword urgency -> rushed", u["state"] == "rushed",
          f"{u['state']} {u['confidence']}")
    wor = classify_state({"arousal": 0.4, "tension": 0.4, "pause_ratio": 0.5},
                         "I'm worried, how much will it cost, it's expensive")
    check("keyword worry -> worried", wor["state"] == "worried",
          f"{wor['state']} {wor['confidence']}")
    hot = classify_state({"arousal": 0.9, "tension": 0.9, "pause_ratio": 0.1},
                         "the boiler stopped again")
    check("hot+tense prosody -> frustrated", hot["state"] == "frustrated",
          f"{hot['state']}")
    none_state = classify_state(None, None)
    check("classify_state never raises on None/None",
          none_state["state"] == "neutral", f"{none_state['state']}")

    # End-to-end on the synthetic fixtures: rushed PCM classifies hot.
    hot_real = classify_state(rushed, "the boiler stopped again")
    check("rushed PCM prosody not calm/neutral",
          hot_real["state"] in ("rushed", "frustrated", "upset"),
          f"{hot_real['state']}")

    expected = {"calm", "neutral", "rushed", "frustrated",
                "upset", "warm", "worried"}
    check("EMPATHY_POLICY covers all 7 states",
          set(EMPATHY_POLICY.keys()) == expected,
          sorted(EMPATHY_POLICY.keys()))
    rate_re = re.compile(r"^[+-]\d+%$")
    pitch_re = re.compile(r"^[+-]\d+Hz$")
    for state in sorted(expected):
        pol = EMPATHY_POLICY.get(state) or {}
        check(f"policy[{state}] prompt_addon non-empty",
              bool(str(pol.get("prompt_addon") or "").strip()))
        check(f"policy[{state}] tts_rate valid",
              bool(rate_re.match(str(pol.get("tts_rate") or ""))),
              str(pol.get("tts_rate")))
        check(f"policy[{state}] tts_pitch valid",
              bool(pitch_re.match(str(pol.get("tts_pitch") or ""))),
              str(pol.get("tts_pitch")))
        check(f"policy[{state}] style_note non-empty",
              bool(str(pol.get("style_note") or "").strip()))
    check("frustrated policy slows voice",
          EMPATHY_POLICY["frustrated"]["tts_rate"].startswith("-"),
          EMPATHY_POLICY["frustrated"]["tts_rate"])

    esc = adapt([
        {"turn": 1, "state": "frustrated", "confidence": 0.9},
        {"turn": 2, "state": "frustrated", "confidence": 0.85},
        {"turn": 3, "state": "neutral", "confidence": 0.5},
    ])
    check("adapt escalates on repeated frustration",
          esc.get("escalate") is True, str(esc))
    calm_sess = adapt(["calm", "calm", "warm"])
    check("adapt no escalation when calm",
          calm_sess.get("escalate") is False
          and calm_sess.get("mood") == "calm", str(calm_sess))
    mixed = adapt([
        {"state": "upset"}, {"state": "neutral"}, {"state": "upset"},
    ])
    check("adapt escalates on repeated upset",
          mixed.get("escalate") is True, str(mixed))
    empty = adapt([])
    check("adapt handles empty timeline",
          empty.get("escalate") is False, str(empty))

    print(f"\n{len(FAILURES)} failure(s). "
          + ("ALL CHECKS PASSED" if not FAILURES else f"FAILED: {FAILURES}"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
