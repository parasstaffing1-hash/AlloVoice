"""Real-time voice helpers: Silero VAD turn detection + Groq STT/LLM.

Transport here is browser WebSocket PCM (Int16LE mono 16kHz); no telephony.
"""

from __future__ import annotations

import io
import wave

import httpx

# Silero VAD turn-taking: 512-sample (32ms @16kHz) windows, 700ms end silence.
_WINDOW_SAMPLES = 512
_WINDOW_BYTES = _WINDOW_SAMPLES * 2  # int16 mono
_END_SILENCE_MS = 700
_FALLBACK_RMS_THRESHOLD = 800.0  # int16 RMS; speech is typically >>1000
_FALLBACK_SILENCE_WINDOWS = max(1, _END_SILENCE_MS // 32)

_GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

CHAT_SYSTEM_PROMPT = (
    "You are the Allo support assistant for UK trades engineers. "
    "Be concise: reply in at most 2 short sentences, plain British English."
)

# Lazy singleton Silero model — loaded once, shared by all detectors.
# NOTE: first load (torch init + weights) can take minutes and MUST NOT
# block the event loop, or the single worker stalls all requests.
# _get_model() kicks a daemon warm-up thread and returns None until ready;
# detectors use the RMS fallback meanwhile and pick up Silero on next init.
_MODEL = None
_MODEL_FAILED = False
_MODEL_WARMING = False
_MODEL_LOCK = None


def _get_lock():
    global _MODEL_LOCK
    if _MODEL_LOCK is None:
        import threading

        _MODEL_LOCK = threading.Lock()
    return _MODEL_LOCK


def _warm_model_bg() -> None:
    global _MODEL, _MODEL_FAILED, _MODEL_WARMING
    try:
        from silero_vad import load_silero_vad

        model = load_silero_vad()
        try:
            model.eval()
        except Exception:
            pass
        with _get_lock():
            _MODEL = model
    except Exception:
        with _get_lock():
            _MODEL_FAILED = True
    finally:
        with _get_lock():
            _MODEL_WARMING = False


def _get_model():
    """Load Silero VAD once; return None on failure (caller uses RMS fallback)."""
    global _MODEL_FAILED, _MODEL_WARMING
    with _get_lock():
        if _MODEL is not None:
            return _MODEL
        if _MODEL_FAILED or _MODEL_WARMING:
            return None
        _MODEL_WARMING = True
    import threading

    threading.Thread(target=_warm_model_bg, daemon=True).start()
    return None


# Kick off background warm-up at import so the model is (hopefully) ready
# before the first call. Instant — never blocks startup.
try:
    _get_model()
except Exception:
    pass


def _rms_int16(window: bytes) -> float:
    """RMS of a 512-sample int16 window. Never raises (returns 0.0)."""
    try:
        import numpy as np

        arr = np.frombuffer(window, dtype=np.int16).astype(np.float32)
        if arr.size == 0:
            return 0.0
        return float((arr * arr).mean() ** 0.5)
    except Exception:
        try:
            import struct

            n = len(window) // 2
            if n == 0:
                return 0.0
            vals = struct.unpack("<" + "h" * n, window[: n * 2])
            return float((sum(v * v for v in vals) / n) ** 0.5)
        except Exception:
            return 0.0


class VadTurnDetector:
    """Streaming turn detector over Int16LE mono PCM (any chunk size).

    feed() buffers leftovers internally and steps 512-sample windows through
    Silero VADIterator (resets per utterance via reset()). Returns
    "speech_start" once per utterance, "speech_end" after 700ms trailing
    silence, else None. Never raises — model errors degrade to RMS fallback.
    """

    def __init__(
        self,
        threshold: float = 0.5,
        sample_rate: int = 16000,
        silence_ms: int = _END_SILENCE_MS,
    ) -> None:
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.silence_ms = silence_ms
        self._buf = bytearray()
        self._iterator = None
        self._use_fallback = False
        # Fallback state machine (also mirrors model state loosely).
        self._fb_in_speech = False
        self._fb_silence_windows = 0
        try:
            model = _get_model()
            if model is None:
                self._use_fallback = True
            else:
                from silero_vad import VADIterator

                self._iterator = VADIterator(
                    model,
                    threshold=threshold,
                    sampling_rate=16000,
                    min_silence_duration_ms=silence_ms,
                    speech_pad_ms=30,
                )
        except Exception:
            self._iterator = None
            self._use_fallback = True

    def reset(self) -> None:
        """Clear buffers + VAD state for the next utterance. Never raises."""
        try:
            self._buf.clear()
        except Exception:
            self._buf = bytearray()
        self._fb_in_speech = False
        self._fb_silence_windows = 0
        try:
            if self._iterator is not None:
                self._iterator.reset_states()
        except Exception:
            pass

    def _fallback_window(self, window: bytes) -> str | None:
        rms = _rms_int16(window)
        if not self._fb_in_speech:
            if rms >= _FALLBACK_RMS_THRESHOLD:
                self._fb_in_speech = True
                self._fb_silence_windows = 0
                return "speech_start"
            return None
        # In speech: count trailing silence windows (~32ms each).
        if rms >= _FALLBACK_RMS_THRESHOLD:
            self._fb_silence_windows = 0
            return None
        self._fb_silence_windows += 1
        if self._fb_silence_windows * 32 >= self.silence_ms:
            self._fb_in_speech = False
            self._fb_silence_windows = 0
            return "speech_end"
        return None

    def feed(self, pcm16_bytes: bytes, sample_rate: int = 16000) -> str | None:
        """Feed arbitrary-size PCM16 chunk; return turn event or None.

        Contract: caller MUST supply 16kHz Int16LE mono (the talk-page
        AudioWorklet resamples any native rate to 16k before sending).
        `sample_rate` is accepted for forward-compat but intentionally
        ignored: no resampling here (would need numpy/scipy — absent
        per requirements.txt). Non-16k input only skews window timing
        (~32ms windows stretch/shrink), never crashes.
        """
        try:
            if not pcm16_bytes:
                return None
            # NOTE: non-16k input is treated as 16k windows (no resampling).
            self._buf.extend(pcm16_bytes)
            saw_start = False
            saw_end = False
            while len(self._buf) >= _WINDOW_BYTES:
                window = bytes(self._buf[:_WINDOW_BYTES])
                del self._buf[:_WINDOW_BYTES]
                event: str | None = None
                if not self._use_fallback and self._iterator is not None:
                    try:
                        import torch

                        import numpy as np

                        arr = (
                            np.frombuffer(window, dtype=np.int16)
                            .astype(np.float32)
                            / 32768.0
                        )
                        tensor = torch.from_numpy(arr)
                        out = self._iterator(tensor)
                        if isinstance(out, dict):
                            if "start" in out:
                                event = "speech_start"
                            elif "end" in out:
                                event = "speech_end"
                    except Exception:
                        # Degrade mid-stream: flip to RMS fallback permanently.
                        self._use_fallback = True
                        event = self._fallback_window(window)
                else:
                    try:
                        event = self._fallback_window(window)
                    except Exception:
                        event = None
                if event == "speech_start":
                    saw_start = True
                elif event == "speech_end":
                    saw_end = True
            # Start takes priority if both fired inside one chunk.
            if saw_start:
                return "speech_start"
            if saw_end:
                return "speech_end"
            return None
        except Exception:
            return None  # never raise from the audio hot path


def pcm16_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    """Wrap raw Int16LE mono PCM in a WAV container (stdlib wave)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm or b"")
    return buf.getvalue()


async def groq_transcribe(wav_bytes: bytes, api_key: str) -> str:
    """Transcribe WAV via Groq Whisper. Returns stripped text; raises on failure."""
    key = (api_key or "").strip()
    if not key:
        raise RuntimeError("missing Groq API key")
    if not wav_bytes:
        raise RuntimeError("empty audio")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _GROQ_TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {key}"},
                files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                data={"model": "whisper-large-v3-turbo", "language": "en"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"transcribe failed: HTTP {e.response.status_code}") from e
    except Exception as e:
        raise RuntimeError(f"transcribe failed: {e}") from e
    text = (data.get("text") or "").strip() if isinstance(data, dict) else ""
    if not text:
        raise RuntimeError("transcribe returned empty text")
    return text


async def groq_chat(
    messages: list, api_key: str, model: str = "qwen/qwen3.8-27b"
) -> str:
    """Chat via Groq OpenAI-compatible endpoint. Returns stripped reply; raises."""
    key = (api_key or "").strip()
    if not key:
        raise RuntimeError("missing Groq API key")
    chat_messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    for m in messages or []:
        try:
            role = m.get("role", "user")
            content = (m.get("content") or "").strip()
            if content and role in ("user", "assistant", "system"):
                chat_messages.append({"role": role, "content": content})
        except Exception:
            continue
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                _GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": chat_messages,
                    "max_tokens": 150,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"] or ""
        text = text.strip()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"chat failed: HTTP {e.response.status_code}") from e
    except Exception as e:
        raise RuntimeError(f"chat failed: {e}") from e
    if not text:
        raise RuntimeError("chat returned empty text")
    return text
