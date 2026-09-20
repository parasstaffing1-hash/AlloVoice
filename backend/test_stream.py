"""Prove streaming deltas + sentence audio arrive before full reply."""
import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import wave

sys.path.insert(0, ".")
from test_realtime_loop import mp3_to_pcm16, FRAME, URL

PHRASE = "hello, my boiler has no hot water"


async def main() -> int:
    from app.services.speech import EdgeTTSVoice
    mp3, _ = await EdgeTTSVoice().speak(PHRASE)
    pcm = await asyncio.to_thread(mp3_to_pcm16, mp3)
    pcm = pcm + b"\x00" * (16000 * 2 * 3 // 2)

    import websockets
    ws = await websockets.connect(URL, max_size=8 * 1024 * 1024)
    try:
        for i in range(0, len(pcm), FRAME):
            await ws.send(pcm[i:i + FRAME])
            await asyncio.sleep(0.02)
        t0 = time.time()
        deltas, sentences, first_delta_at, reply_at = 0, 0, None, None
        seen = {}
        audio_started = False
        deadline = time.time() + 180.0
        while time.time() < deadline:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
            except asyncio.TimeoutError:
                break
            if isinstance(msg, (bytes, bytearray)):
                continue
            try:
                obj = json.loads(msg)
            except Exception:
                continue
            t = obj.get("type")
            seen[t] = seen.get(t, 0) + 1
            if t == "reply_delta" and obj.get("text"):
                deltas += 1
                if first_delta_at is None:
                    first_delta_at = time.time() - t0
            elif t == "sentence_start":
                sentences += 1
            elif t == "reply_text" and obj.get("text"):
                reply_at = time.time() - t0
                break
            elif t == "error":
                print("SERVER ERROR:", str(obj.get("message"))[:200])
        print("events seen:", seen)
        print(f"deltas: {deltas} | sentences: {sentences} | "
              f"first_delta: {first_delta_at and round(first_delta_at,1)}s | "
              f"full_reply: {reply_at and round(reply_at,1)}s")
        ok = deltas > 0 and sentences > 0 and reply_at is not None
        print("STREAM RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        try:
            await ws.close()
        except Exception:
            pass


sys.exit(asyncio.run(main()))
