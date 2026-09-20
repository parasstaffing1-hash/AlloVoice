"""Closed-loop realtime-voice test (no mic/human).

Synth PCM -> WS PCM frames -> expect transcript/reply/audio.
Run ONLY against a MANUALLY started backend on :8000; never starts servers.
If connection refused -> prints SKIP. Per-stage PASS/FAIL otherwise.

Usage: python test_realtime_loop.py
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import wave

URL = "ws://127.0.0.1:8000/api/realtime-voice/ws/talk"
PHRASE = "hello, my boiler has no hot water"
FRAME = 3200  # bytes per WS binary frame (~100ms @16k mono int16)


def mp3_to_pcm16(mp3_bytes: bytes) -> bytes:
    """MP3 -> raw Int16LE mono 16kHz PCM via imageio-ffmpeg (cf speech.webm_to_wav)."""
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as fin:
        fin.write(mp3_bytes)
        in_path = fin.name
    out_fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(out_fd)
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", in_path, "-ac", "1", "-ar", "16000",
             "-f", "wav", out_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        with wave.open(out_path, "rb") as wf:
            assert wf.getnchannels() == 1 and wf.getframerate() == 16000, (
                f"unexpected wav {wf.getnchannels()}ch@{wf.getframerate()}")
            return wf.readframes(wf.getnframes())
    finally:
        for p in (in_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass


async def main() -> int:
    print(f"[1/5] TTS synth {PHRASE!r} ...")
    try:
        from app.services.speech import EdgeTTSVoice

        mp3, voice = await EdgeTTSVoice().speak(PHRASE)
        assert mp3, "empty mp3"
        print(f"  PASS tts ({len(mp3)} bytes, voice={voice})")
    except Exception as e:
        print(f"  FAIL tts: {e}")
        return 1

    print("[2/5] decode MP3 -> PCM16/16k ...")
    try:
        pcm = await asyncio.to_thread(mp3_to_pcm16, mp3)
        assert len(pcm) > 16000, f"pcm too short: {len(pcm)}"
        print(f"  PASS decode ({len(pcm)} bytes PCM)")
    except Exception as e:
        print(f"  FAIL decode: {e}")
        return 1

    # Append ~1.5s digital silence so Silero emits speech_end (700ms trailing).
    pcm = pcm + b"\x00" * (16000 * 2 * 3 // 2)

    print(f"[3/5] connect {URL} ...")
    try:
        import websockets

        ws = await websockets.connect(URL, max_size=8 * 1024 * 1024)
    except Exception as e:
        print(f"  SKIP: backend not running ({e}). Start it manually first.")
        return 2
    print("  PASS connect")

    got = {"transcript_final": "", "reply_text": "", "audio_start": False,
           "audio_bin": 0, "audio_end": False, "errors": []}
    try:
        print("[4/5] stream PCM frames ...")
        for i in range(0, len(pcm), FRAME):
            try:
                await ws.send(pcm[i:i + FRAME])
            except Exception as e:
                print(f"  FAIL send: {e}")
                break
            await asyncio.sleep(0.02)
        print(f"  PASS send ({len(pcm)} bytes in {len(pcm)//FRAME+1} frames)")

        print("[5/5] wait transcript_final / reply_text / audio ...")
        deadline = asyncio.get_event_loop().time() + 75.0
        async with asyncio.timeout(deadline - asyncio.get_event_loop().time()):
            while True:
                if (got["transcript_final"] and got["reply_text"]
                        and got["audio_start"] and got["audio_end"]
                        and got["audio_bin"] > 0):
                    break
                try:
                    msg = await asyncio.wait_for(
                        ws.recv(),
                        timeout=max(1.0, deadline - asyncio.get_event_loop().time()))
                except asyncio.TimeoutError:
                    break
                if isinstance(msg, (bytes, bytearray)):
                    got["audio_bin"] += len(msg)
                    continue
                try:
                    obj = json.loads(msg)
                except Exception:
                    continue
                t = obj.get("type")
                if t == "transcript_final" and obj.get("text"):
                    got["transcript_final"] = obj["text"]
                elif t == "reply_text" and obj.get("text"):
                    got["reply_text"] = obj["text"]
                elif t == "audio_start":
                    got["audio_start"] = True
                elif t == "audio_end":
                    got["audio_end"] = True
                elif t == "error":
                    got["errors"].append(str(obj.get("message", ""))[:120])
    finally:
        try:
            await ws.close()
        except Exception:
            pass

    ok = True
    for stage in ("transcript_final", "reply_text"):
        if got[stage]:
            print(f"  PASS {stage}: {got[stage][:120]!r}")
        else:
            print(f"  FAIL {stage}: (missing) errors={got['errors']}")
            ok = False
    if got["audio_start"] and got["audio_end"] and got["audio_bin"] > 0:
        print(f"  PASS audio (start+{got['audio_bin']}B bin+end)")
    else:
        print(f"  FAIL audio: start={got['audio_start']} bin={got['audio_bin']} "
              f"end={got['audio_end']} errors={got['errors']}")
        ok = False
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
