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
            model = _get_model()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                path = f.name
            try:
                segments, _info = model.transcribe(
                    path, language="en", beam_size=1, vad_filter=True
                )
                return " ".join(
                    (s.text or "").strip() for s in segments if (s.text or "").strip()
                ).strip()
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass

        return await asyncio.to_thread(_run)


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
        try:
            data = await self._speak_with_voice(text, self.primary, rate, pitch)
            if data:
                return data, self.primary
            raise RuntimeError("primary TTS returned empty audio")
        except Exception:
            data = await self._speak_with_voice(text, self.fallback, rate, pitch)
            return data, self.fallback


# ---------------------------------------------------------------------------
# Factories (provider swap-in point)
# ---------------------------------------------------------------------------


def get_stt(name: str | None = None) -> STTProvider:
    provider = (name or os.getenv("VOICE_STT_PROVIDER", "faster-whisper")).strip().lower()
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
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as fin:
        fin.write(webm_bytes)
        in_path = fin.name
    out_fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(out_fd)
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", in_path, "-ac", "1", "-ar", "16000", "-f", "wav", out_path],
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
