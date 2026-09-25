"""Local voice providers for VoiceField (no external STT/TTS keys needed).

Modular provider design: an alternative provider can be swapped in later by adding new
STTProvider/TTSProvider subclasses and extending get_stt()/get_tts() —
no route changes required.
"""

import asyncio
import os
import subprocess
import tempfile

PRIMARY_VOICE = "en-GB-SoniaNeural"
FALLBACK_VOICE = "en-GB-RyanNeural"
MAX_TTS_CHARS = 1500


# ---------------------------------------------------------------------------
# Base interfaces
# ---------------------------------------------------------------------------


class STTProvider:
    async def transcribe(self, wav_bytes: bytes) -> str:
        raise NotImplementedError


class TTSProvider:
    async def speak(self, text: str) -> tuple[bytes, str]:
        """Return (mp3_bytes, voice_used)."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# faster-whisper STT
# ---------------------------------------------------------------------------

_MODEL = None


def _get_model():
    """Lazy singleton WhisperModel. Downloads on first use (~500MB)."""
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel

        _MODEL = WhisperModel("small.en", device="cpu", compute_type="int8")
    return _MODEL


def is_model_cached() -> bool:
    return _MODEL is not None


class FasterWhisperSTT(STTProvider):
    async def transcribe(self, wav_bytes: bytes) -> str:
        if not wav_bytes:
            return ""

        def _run() -> str:
            try:
                model = _get_model()
            except ImportError as e:
                raise RuntimeError(
                    "faster-whisper not installed (local STT unavailable)"
                ) from e
            except Exception as e:
                raise RuntimeError(f"local STT model load failed: {e}") from e
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                path = f.name
                f.write(wav_bytes)
            try:
                segments, _info = model.transcribe(
                    path, language="en", beam_size=1, vad_filter=True
                )
                return " ".join(
                    (s.text or "").strip() for s in segments if (s.text or "").strip()
                ).strip()
            except Exception as e:
                raise RuntimeError(f"local STT transcription failed: {e}") from e
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass

        return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# Groq-hosted Whisper STT (fast alternative to local faster-whisper)
# ---------------------------------------------------------------------------


# Module-level shared client: reuse TCP/TLS connections across STT calls
# instead of paying a fresh handshake per transcription. Process-lifetime;
# httpx.AsyncClient is safe to share across awaits on one event loop.
_GROQ_CLIENT = None


def _get_groq_client():
    """Lazy singleton httpx.AsyncClient for Groq STT. May raise ImportError."""
    global _GROQ_CLIENT
    if _GROQ_CLIENT is None:
        import httpx

        _GROQ_CLIENT = httpx.AsyncClient(timeout=60.0)
    return _GROQ_CLIENT


class GroqWhisperSTT(STTProvider):
    """Groq-hosted Whisper (OpenAI-compatible audio API).

    No local model downloads — POSTs WAV bytes to Groq and returns the
    transcript string. Requires GROQ_API_KEY in settings/env.
    Raises on missing key, transport failure, or empty transcript.
    """

    _URL = "https://api.groq.com/openai/v1/audio/transcriptions"
    _MODEL = "whisper-large-v3-turbo"

    def _api_key(self) -> str:
        try:
            from app.core.config import get_settings

            key = (get_settings().GROQ_API_KEY or "").strip()
            if key:
                return key
        except Exception:
            pass
        return os.getenv("GROQ_API_KEY", "").strip()

    async def transcribe(self, wav_bytes: bytes) -> str:
        if not wav_bytes:
            return ""
        api_key = self._api_key()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not configured")
        try:
            client = _get_groq_client()
        except ImportError as e:
            raise RuntimeError(
                "httpx not installed (required for Groq STT)"
            ) from e
        try:
            resp = await client.post(
                self._URL,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                data={"model": self._MODEL, "language": "en"},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Groq STT failed: {e}") from e
        text = (data.get("text") or "").strip() if isinstance(data, dict) else ""
        if not text:
            raise RuntimeError("Groq STT returned empty transcript")
        return text


# ---------------------------------------------------------------------------
# edge-tts TTS
# ---------------------------------------------------------------------------


class EdgeTTSVoice(TTSProvider):
    def __init__(self, primary: str | None = None):
        primary = (primary or PRIMARY_VOICE).strip() or PRIMARY_VOICE
        self.primary = primary
        # If caller requested the fallback as primary, flip fallback to Sonia.
        self.fallback = (
            PRIMARY_VOICE if primary == FALLBACK_VOICE else FALLBACK_VOICE
        )

    @staticmethod
    def _cache_dir() -> str:
        """Disk cache for repeat phrases (greetings, prices, closers).
        VOICE_TTS_CACHE_DIR overrides; default is the OS temp dir.
        No new infra — plain files, capped at 500 newest."""
        d = (os.getenv("VOICE_TTS_CACHE_DIR") or "").strip() or os.path.join(
            tempfile.gettempdir(), "allovoice_tts")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            return ""
        return d

    @staticmethod
    def _cache_key(text: str, voice: str, rate: str, pitch: str) -> str:
        import hashlib

        raw = f"{voice}|{rate}|{pitch}|{text}".encode("utf-8", "ignore")
        return hashlib.sha1(raw).hexdigest() + ".mp3"

    def _cache_get(self, key: str) -> bytes:
        d = self._cache_dir()
        if not d:
            return b""
        try:
            p = os.path.join(d, key)
            if os.path.isfile(p):
                with open(p, "rb") as fh:
                    return fh.read()
        except OSError:
            pass
        return b""

    def _cache_put(self, key: str, data: bytes) -> None:
        d = self._cache_dir()
        if not d or not data:
            return
        try:
            with open(os.path.join(d, key), "wb") as fh:
                fh.write(data)
            files = sorted(
                (os.path.join(d, f) for f in os.listdir(d)
                 if f.endswith(".mp3")),
                key=lambda p: os.path.getmtime(p),
            )
            for old in files[:-500]:
                try:
                    os.unlink(old)
                except OSError:
                    pass
        except OSError:
            pass

    async def _speak_with_voice(self, text: str, voice: str,
                                rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
        import edge_tts

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
        try:
            await edge_tts.Communicate(text, voice=voice,
                                       rate=rate, pitch=pitch).save(path)
            with open(path, "rb") as fh:
                return fh.read()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    async def speak(self, text: str, rate: str = "+0%",
                    pitch: str = "+0Hz") -> tuple[bytes, str]:
        text = (text or "").strip()[:MAX_TTS_CHARS]
        if not text:
            return b"", self.primary
        key = self._cache_key(text, self.primary, rate, pitch)
        hit = self._cache_get(key)
        if hit:
            return hit, self.primary
        try:
            data = await self._speak_with_voice(text, self.primary, rate, pitch)
            if data:
                self._cache_put(key, data)
                return data, self.primary
            raise RuntimeError("primary TTS returned empty audio")
        except Exception:
            pass
        # Fallback voice: consult its own cache slot first, then synthesize.
        # Never raises — a total TTS outage degrades to b"" and callers
        # translate that to HTTP 502 (same as before, minus the traceback).
        try:
            fb_key = self._cache_key(text, self.fallback, rate, pitch)
            fb_hit = self._cache_get(fb_key)
            if fb_hit:
                return fb_hit, self.fallback
            data = await self._speak_with_voice(text, self.fallback, rate, pitch)
            if data:
                self._cache_put(fb_key, data)
                return data, self.fallback
            return b"", self.fallback
        except Exception:
            return b"", self.fallback


# ---------------------------------------------------------------------------
# Factories (provider swap-in point)
# ---------------------------------------------------------------------------


def get_stt(name: str | None = None) -> STTProvider:
    # VOICE_STT_PROVIDER: faster-whisper (default, local) | groq (hosted) | sarvam (swap-in point)
    provider = (name or os.getenv("VOICE_STT_PROVIDER", "faster-whisper")).strip().lower()
    if provider == "groq":
        return GroqWhisperSTT()
    if provider == "sarvam":
        raise NotImplementedError("Sarvam swap-in point")
    if provider in ("faster-whisper", "faster_whisper", "whisper", "local"):
        return FasterWhisperSTT()
    raise ValueError(f"Unknown STT provider: {provider}")


def get_tts(name: str | None = None, primary: str | None = None) -> TTSProvider:
    provider = (name or os.getenv("VOICE_TTS_PROVIDER", "edge-tts")).strip().lower()
    if provider == "sarvam":
        raise NotImplementedError("Sarvam swap-in point")
    if provider in ("edge-tts", "edge_tts", "edge", "local"):
        return EdgeTTSVoice(primary=primary)
    raise ValueError(f"Unknown TTS provider: {provider}")


# ---------------------------------------------------------------------------
# Audio conversion (browser webm/opus -> 16kHz mono WAV)
# ---------------------------------------------------------------------------


def webm_to_wav(webm_bytes: bytes) -> bytes:
    """Convert browser MediaRecorder webm/opus bytes to 16kHz mono WAV.

    Uses imageio-ffmpeg's bundled ffmpeg binary — no system ffmpeg needed.
    """
    if not webm_bytes:
        raise ValueError("empty audio input")
    try:
        import imageio_ffmpeg
    except ImportError as e:
        raise RuntimeError(
            "imageio-ffmpeg not installed (audio conversion unavailable)"
        ) from e
    try:
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise RuntimeError(f"ffmpeg binary unavailable: {e}") from e
    in_path = ""
    out_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as fin:
            in_path = fin.name
            fin.write(webm_bytes)
        out_fd, out_path = tempfile.mkstemp(suffix=".wav")
        os.close(out_fd)
        try:
            subprocess.run(
                [ffmpeg, "-y", "-i", in_path, "-ac", "1", "-ar", "16000", "-f", "wav", out_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=30,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("audio conversion timed out") from e
        except subprocess.CalledProcessError as e:
            tail = ((e.stderr or b"")[-500:]).decode("utf-8", "ignore").strip()
            detail = f": {tail}" if tail else ""
            raise RuntimeError(
                f"audio conversion failed (invalid/corrupt audio){detail}"
            ) from e
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        for p in (in_path, out_path):
            if not p:
                continue
            try:
                os.unlink(p)
            except OSError:
                pass
