"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, MicOff, Zap, PhoneOff, RefreshCw, Loader2, Volume2 } from "lucide-react";

type TalkStatus = "Idle" | "Listening" | "Thinking" | "Speaking" | "Interrupted";
type Msg = { role: "user" | "agent"; text: string };

type ServerMsg =
| { type: "transcript_final"; text: string }
| { type: "reply_text"; text: string }
| { type: "reply_delta"; text: string }
| { type: "sentence_start"; index: number }
  | { type: "audio_start"; voice?: string }
  | { type: "audio_end" }
  | { type: "state"; state: string }
  | { type: "error"; message: string }
  | { type: "interrupted" };

// Inline AudioWorklet processor: float32 in -> resample to 16k -> int16,
// posted in ~100ms chunks (1600 samples @ 16kHz).
// NOTE: plain string concat — no backticks/${} inside so it can live in a TS template literal.
const WORKLET_CODE = `
class TalkPCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._targetRate = 16000;
    this._ratio = sampleRate / this._targetRate;
    this._outLen = 1600;
    this._needIn = Math.max(1, Math.round(this._ratio * this._outLen));
    this._buf = new Float32Array(0);
  }
  _convert(block, count) {
    var out = new Int16Array(count);
    var scale = block.length / count;
    for (var i = 0; i < count; i++) {
      var pos = i * scale;
      var i0 = Math.floor(pos);
      var i1 = Math.min(i0 + 1, block.length - 1);
      var frac = pos - i0;
      var s = block[i0] * (1 - frac) + block[i1] * frac;
      if (s > 1) s = 1;
      else if (s < -1) s = -1;
      out[i] = s < 0 ? Math.round(s * 32768) : Math.round(s * 32767);
    }
    return out;
  }
  process(inputs) {
    try {
      var ch = inputs && inputs[0] && inputs[0][0];
      if (ch && ch.length) {
        var copy = new Float32Array(ch.length);
        copy.set(ch);
        var next = new Float32Array(this._buf.length + copy.length);
        next.set(this._buf, 0);
        next.set(copy, this._buf.length);
        this._buf = next;
        while (this._buf.length >= this._needIn) {
          var block = this._buf.slice(0, this._needIn);
          this._buf = this._buf.slice(this._needIn);
          var pcm = this._convert(block, this._outLen);
          this.port.postMessage(pcm.buffer, [pcm.buffer]);
        }
      }
    } catch (e) {}
    return true;
  }
}
registerProcessor('talk-pcm', TalkPCMProcessor);
`;

function buildWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.hostname}:8000/api/realtime-voice/ws/talk`;
}

function mapServerState(raw: string): TalkStatus | null {
  const s = (raw || "").trim().toLowerCase();
  if (s === "idle") return "Idle";
  if (s === "listening") return "Listening";
  if (s === "thinking") return "Thinking";
  if (s === "speaking") return "Speaking";
  if (s === "interrupted") return "Interrupted";
  return null;
}

function micErrorMessage(e: unknown): string {
  const err = e as DOMException | Error | undefined;
  const name = (err as DOMException)?.name || "";
  if (name === "NotAllowedError" || name === "SecurityError")
    return "Microphone access denied — click the mic/lock icon in the address bar, allow the microphone, then try again.";
  if (name === "NotFoundError" || name === "OverconstrainedError")
    return "No microphone found — plug in a mic (or enable one in system settings) and try again.";
  if (name === "NotReadableError")
    return "Microphone is busy — close other apps/tabs using the mic and try again.";
  const msg = (err as Error)?.message || "";
  return `Could not start the microphone${msg ? `: ${msg}` : ". Check permissions and try again."}`;
}

export default function TalkPage() {
  const [status, setStatus] = useState<TalkStatus>("Idle");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [voice, setVoice] = useState<string>("");
  const [sessionActive, setSessionActive] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [wsClosed, setWsClosed] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const gainRef = useRef<GainNode | null>(null);
  const playSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const mp3ChunksRef = useRef<Uint8Array[]>([]);
  const mp3BytesRef = useRef(0);
  const speakingRef = useRef(false);
  const sessionActiveRef = useRef(false);
  const statusRef = useRef<TalkStatus>("Idle");
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const levelRafRef = useRef<number | null>(null);
  const workletUrlRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const levelBarRef = useRef<HTMLDivElement | null>(null);
  const lastBargeRef = useRef(0);
  const silentFramesRef = useRef(0);
  const noSignalNotifiedRef = useRef(false);
  const flashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const deltaActiveRef = useRef(false);
  const mountedRef = useRef(true);
  const levelBufRef = useRef<Uint8Array | null>(null);

  const setBothStatus = useCallback((s: TalkStatus) => {
    statusRef.current = s;
    if (mountedRef.current) setStatus(s);
  }, []);

  const showError = useCallback((msg: string) => {
    if (mountedRef.current) setError(msg);
  }, []);

  // ---- playback ----
  const stopPlayback = useCallback(() => {
    speakingRef.current = false;
    const src = playSourceRef.current;
    playSourceRef.current = null;
    if (src) {
      try {
        src.onended = null;
        src.stop();
      } catch {
        /* already stopped */
      }
      try {
        src.disconnect();
      } catch {
        /* noop */
      }
    }
  }, []);

  const getPlaybackCtx = useCallback((): AudioContext => {
    let ctx = playbackCtxRef.current;
    if (!ctx || ctx.state === "closed") {
      const AC: typeof AudioContext | undefined =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AC) throw new Error("Audio playback is not supported in this browser.");
      ctx = new AC();
      const gain = ctx.createGain();
      gain.gain.value = 1.0;
      gain.connect(ctx.destination);
      gainRef.current = gain;
      playbackCtxRef.current = ctx;
    }
    if (ctx.state === "suspended") void ctx.resume().catch(() => {});
    return ctx;
  }, []);

  const playCollectedMp3 = useCallback(async () => {
    const chunks = mp3ChunksRef.current;
    const total = mp3BytesRef.current;
    mp3ChunksRef.current = [];
    mp3BytesRef.current = 0;
    if (!chunks.length || total === 0) {
      if (sessionActiveRef.current) setBothStatus("Listening");
      else setBothStatus("Idle");
      return;
    }
    try {
      const ctx = getPlaybackCtx();
      const flat = new Uint8Array(total);
      let off = 0;
      for (const c of chunks) {
        flat.set(c, off);
        off += c.length;
      }
      // decodeAudioData detaches the buffer — copy first.
      const copy = flat.slice().buffer;
      const audioBuf = await ctx.decodeAudioData(copy);
      if (!mountedRef.current || !sessionActiveRef.current) return;
      stopPlayback();
      const src = ctx.createBufferSource();
      src.buffer = audioBuf;
      src.connect(gainRef.current ?? ctx.destination);
      playSourceRef.current = src;
      speakingRef.current = true;
      setBothStatus("Speaking");
      src.onended = () => {
        if (playSourceRef.current === src) playSourceRef.current = null;
        speakingRef.current = false;
        if (!mountedRef.current) return;
        if (sessionActiveRef.current) setBothStatus("Listening");
        else setBothStatus("Idle");
      };
      src.start();
    } catch {
      speakingRef.current = false;
      showError("Reply audio could not be decoded — showing text only.");
      if (sessionActiveRef.current) setBothStatus("Listening");
      else setBothStatus("Idle");
    }
  }, [getPlaybackCtx, setBothStatus, showError, stopPlayback]);

  // ---- barge-in ----
  const sendBargeIn = useCallback(() => {
    const now = Date.now();
    if (now - lastBargeRef.current < 500) return; // throttle
    lastBargeRef.current = now;
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: "barge-in" }));
      } catch {
        /* socket going away — ignore */
      }
    }
  }, []);

  const handleInterrupt = useCallback(() => {
    sendBargeIn();
    stopPlayback();
    mp3ChunksRef.current = [];
    mp3BytesRef.current = 0;
    // Strip any half-streamed agent text? Keep history; just flash state.
    setBothStatus("Interrupted");
    if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
    flashTimerRef.current = setTimeout(() => {
      if (!mountedRef.current) return;
      setBothStatus(sessionActiveRef.current ? "Listening" : "Idle");
    }, 1200);
  }, [sendBargeIn, setBothStatus, stopPlayback]);

  // ---- teardown pieces ----
  const stopLevelLoop = useCallback(() => {
    if (levelRafRef.current !== null) {
      cancelAnimationFrame(levelRafRef.current);
      levelRafRef.current = null;
    }
    if (levelBarRef.current) levelBarRef.current.style.width = "0%";
  }, []);

  const stopPing = useCallback(() => {
    if (pingTimerRef.current !== null) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
  }, []);

  const teardownAudio = useCallback(() => {
    stopLevelLoop();
    const node = workletNodeRef.current;
    workletNodeRef.current = null;
    if (node) {
      try {
        node.port.onmessage = null;
        node.disconnect();
      } catch {
        /* noop */
      }
    }
    const src = sourceRef.current;
    sourceRef.current = null;
    if (src) {
      try {
        src.disconnect();
      } catch {
        /* noop */
      }
    }
    analyserRef.current = null;
    const cap = captureCtxRef.current;
    captureCtxRef.current = null;
    if (cap) {
      void cap.close().catch(() => {});
    }
    const st = streamRef.current;
    streamRef.current = null;
    if (st) {
      st.getTracks().forEach((t) => {
        try {
          t.stop();
        } catch {
          /* noop */
        }
      });
    }
    if (workletUrlRef.current) {
      try {
        URL.revokeObjectURL(workletUrlRef.current);
      } catch {
        /* noop */
      }
      workletUrlRef.current = null;
    }
  }, [stopLevelLoop]);

  const closeSocket = useCallback(() => {
    stopPing();
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws) {
      try {
        ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
      } catch {
        /* noop */
      }
      try {
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close();
      } catch {
        /* noop */
      }
    }
  }, [stopPing]);

  // ---- session end (End button / unmount) ----
  const endSession = useCallback(
    (clearTranscript: boolean) => {
      sessionActiveRef.current = false;
      if (mountedRef.current) {
        setSessionActive(false);
        setWsClosed(false);
        setConnecting(false);
      }
      if (flashTimerRef.current) {
        clearTimeout(flashTimerRef.current);
        flashTimerRef.current = null;
      }
      closeSocket();
      stopPlayback();
      teardownAudio();
      mp3ChunksRef.current = [];
      mp3BytesRef.current = 0;
      deltaActiveRef.current = false;
      silentFramesRef.current = 0;
      noSignalNotifiedRef.current = false;
      if (clearTranscript && mountedRef.current) setMessages([]);
      setBothStatus("Idle");
    },
    [closeSocket, setBothStatus, stopPlayback, teardownAudio]
  );

  // ---- incoming server messages ----
  const handleServerText = useCallback(
    (raw: string) => {
      let msg: ServerMsg;
      try {
        msg = JSON.parse(raw) as ServerMsg;
      } catch {
        return; // ignore non-JSON text
      }
      switch (msg.type) {
        case "transcript_final": {
          const text = (msg.text || "").trim();
          deltaActiveRef.current = false;
          if (text) setMessages((prev) => [...prev, { role: "user", text }]);
          break;
        }
        case "reply_text":
        case "reply_delta": {
          const text = msg.text || "";
          if (!text) break;
          if (msg.type === "reply_delta") deltaActiveRef.current = true;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            // Full reply_text after deltas would duplicate: replace instead.
            if (msg.type === "reply_text" && deltaActiveRef.current && last?.role === "agent") {
              return [...prev.slice(0, -1), { role: "agent", text }];
            }
            // Stream into the trailing agent bubble when possible.
            if (last && last.role === "agent" && statusRef.current !== "Idle") {
              return [...prev.slice(0, -1), { role: "agent", text: last.text + text }];
            }
            return [...prev, { role: "agent", text }];
          });
          if (statusRef.current === "Listening" || statusRef.current === "Idle")
            setBothStatus("Thinking");
          break;
        }
        case "sentence_start":
          // Audio for this sentence is on its way; bubble already streaming.
          break;
        case "audio_start":
          mp3ChunksRef.current = [];
          mp3BytesRef.current = 0;
          if (typeof msg.voice === "string" && msg.voice) setVoice(msg.voice);
          speakingRef.current = true;
          setBothStatus("Speaking");
          break;
        case "audio_end":
          void playCollectedMp3();
          break;
        case "state": {
          const mapped = mapServerState(msg.state);
          if (mapped) {
            // Don't let a stale server "listening" clobber local playback.
            if (mapped === "Listening" && speakingRef.current) break;
            setBothStatus(mapped);
          }
          break;
        }
        case "interrupted":
          stopPlayback();
          mp3ChunksRef.current = [];
          mp3BytesRef.current = 0;
          setBothStatus("Interrupted");
          if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
          flashTimerRef.current = setTimeout(() => {
            if (!mountedRef.current) return;
            setBothStatus(sessionActiveRef.current ? "Listening" : "Idle");
          }, 1200);
          break;
        case "error":
          showError(msg.message || "Server error — try again.");
          break;
        default:
          break;
      }
    },
    [playCollectedMp3, setBothStatus, showError, stopPlayback]
  );

  // ---- session start ----
  const startSession = useCallback(async () => {
    if (sessionActiveRef.current || connecting) return;
    setError(null);
    setWsClosed(false);
    setConnecting(true);
    // Fresh per-session streaming/audio state (stale deltas/buffers from a
    // previous call would corrupt the new transcript/audio queue).
    deltaActiveRef.current = false;
    mp3ChunksRef.current = [];
    mp3BytesRef.current = 0;
    silentFramesRef.current = 0;
    noSignalNotifiedRef.current = false;

    // 1) Mic first so permission errors surface before we dial the socket.
    let stream: MediaStream;
    try {
      if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        throw Object.assign(new Error("Microphone is not available in this browser."), {
          name: "NotSupportedError",
        });
      }
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (e) {
      showError(micErrorMessage(e));
      setConnecting(false);
      return;
    }
    if (!mountedRef.current) {
      stream.getTracks().forEach((t) => {
        try {
          t.stop();
        } catch {
          /* noop */
        }
      });
      setConnecting(false);
      return;
    }
    streamRef.current = stream;

    // 2) WebSocket to the realtime endpoint (no auth — demo grade).
    let ws: WebSocket;
    try {
      ws = new WebSocket(buildWsUrl());
      ws.binaryType = "arraybuffer";
    } catch {
      showError("Could not open the voice socket — is the backend running on :8000?");
      stream.getTracks().forEach((t) => {
        try {
          t.stop();
        } catch {
          /* noop */
        }
      });
      streamRef.current = null;
      setConnecting(false);
      return;
    }
    wsRef.current = ws;

    const onSocketClose = () => {
      stopPing();
      wsRef.current = null;
      if (!mountedRef.current) return;
      // Unexpected drop mid-session → stop capture, offer reconnect.
      if (sessionActiveRef.current) {
        sessionActiveRef.current = false;
        setSessionActive(false);
        stopPlayback();
        teardownAudio();
        speakingRef.current = false;
        setWsClosed(true);
        setBothStatus("Idle");
        showError("Connection closed — tap Reconnect to resume.");
      }
      setConnecting(false);
    };

    ws.onopen = () => {
      if (!mountedRef.current) {
        try {
          ws.close();
        } catch {
          /* noop */
        }
        return;
      }
      // Keepalive every 20s.
      stopPing();
      pingTimerRef.current = setInterval(() => {
        const s = wsRef.current;
        if (s && s.readyState === WebSocket.OPEN) {
          try {
            s.send(JSON.stringify({ type: "ping" }));
          } catch {
            /* ignore — close handler will fire */
          }
        }
      }, 20000);
      void startCapture();
    };

    ws.onmessage = (ev: MessageEvent) => {
      const data = ev.data as string | ArrayBuffer | Blob;
      if (typeof data === "string") {
        handleServerText(data);
        return;
      }
      // Binary MP3 chunk between audio_start/end.
      const push = (buf: ArrayBuffer) => {
        if (buf.byteLength === 0) return;
        const u8 = new Uint8Array(buf.slice(0));
        mp3ChunksRef.current.push(u8);
        mp3BytesRef.current += u8.length;
      };
      if (data instanceof ArrayBuffer) {
        push(data);
      } else if (typeof Blob !== "undefined" && data instanceof Blob) {
        void data
          .arrayBuffer()
          .then(push)
          .catch(() => {});
      }
    };

    ws.onerror = () => {
      showError("Voice connection error — check the backend on :8000 and retry.");
    };
    ws.onclose = onSocketClose;

    // 3) Capture pipeline: AudioContext(16k) -> analyser + inline-blob AudioWorklet -> ws.
    const startCapture = async () => {
      try {
        const AC: typeof AudioContext | undefined =
          window.AudioContext ??
          (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (!AC) throw new Error("Web Audio is not supported in this browser.");
        let cap: AudioContext;
        try {
          cap = new AC({ sampleRate: 16000 });
        } catch {
          cap = new AC(); // fallback: worklet resamples to 16k anyway
        }
        captureCtxRef.current = cap;
        if (cap.state === "suspended") await cap.resume().catch(() => {});

        if (!mountedRef.current || wsRef.current !== ws) {
          void cap.close().catch(() => {});
          return;
        }

        const src = cap.createMediaStreamSource(stream);
        sourceRef.current = src;

        const analyser = cap.createAnalyser();
        analyser.fftSize = 1024;
        analyser.smoothingTimeConstant = 0.4;
        src.connect(analyser);
        analyserRef.current = analyser;
        levelBufRef.current = new Uint8Array(analyser.fftSize);

        if (!cap.audioWorklet) throw new Error("AudioWorklet is not supported in this browser.");
        const blob = new Blob([WORKLET_CODE], { type: "application/javascript" });
        const url = URL.createObjectURL(blob);
        workletUrlRef.current = url;
        await cap.audioWorklet.addModule(url);

        if (!mountedRef.current || wsRef.current !== ws) return;
        const node = new AudioWorkletNode(cap, "talk-pcm");
        workletNodeRef.current = node;
        node.port.onmessage = (e: MessageEvent) => {
          const buf = e.data as ArrayBuffer;
          const s = wsRef.current;
          if (s && s.readyState === WebSocket.OPEN && buf && buf.byteLength > 0) {
            try {
              s.send(buf);
            } catch {
              /* ignore */
            }
          }
        };
        node.onprocessorerror = () => {
          showError("Mic capture failed mid-session — tap End and retry.");
        };
        src.connect(node);
        // NOTE: never connect mic to destination (feedback).

        startLevelLoop();
        sessionActiveRef.current = true;
        setSessionActive(true);
        setConnecting(false);
        setBothStatus("Listening");
      } catch (e) {
        const msg =
          e instanceof Error && /secure|worklet/i.test(e.message)
            ? "Realtime mic capture needs a secure context (HTTPS or localhost) with AudioWorklet support."
            : e instanceof Error
              ? `Could not start mic capture: ${e.message}`
              : "Could not start mic capture.";
        showError(msg);
        sessionActiveRef.current = false;
        setSessionActive(false);
        setConnecting(false);
        closeSocket();
        teardownAudio();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connecting]);

  // ---- mic level meter loop (analyser -> div width, + voice barge-in) ----
  const startLevelLoop = useCallback(() => {
    stopLevelLoop();
    let lastUi = 0;
    const tick = () => {
      if (!mountedRef.current || !sessionActiveRef.current) return;
      const analyser = analyserRef.current;
      if (analyser) {
        const buf = levelBufRef.current;
        if (buf) {
          analyser.getByteTimeDomainData(buf as Uint8Array<ArrayBuffer>);
          let sum = 0;
          for (let i = 0; i < buf.length; i++) {
            const v = (buf[i] - 128) / 128;
            sum += v * v;
          }
          const rms = Math.sqrt(sum / buf.length);
          const pct = Math.min(100, Math.round(rms * 320));
          if (levelBarRef.current) levelBarRef.current.style.width = `${pct}%`;
          // Hands-free cut-in: loud mic input while agent audio plays = barge-in.
          if (speakingRef.current && rms > 0.09) {
            sendBargeIn();
            stopPlayback();
          }
          // No-audio feedback: mic attached but (near-)silent for ~8s while
          // the agent isn't playing usually means muted input / wrong device.
          if (!speakingRef.current && rms < 0.004) {
            silentFramesRef.current += 1;
            if (silentFramesRef.current > 480 && !noSignalNotifiedRef.current) {
              noSignalNotifiedRef.current = true;
              showError("Mic sounds silent — check the input volume/mute switch, then talk. Dismiss anytime.");
            }
          } else if (!speakingRef.current) {
            silentFramesRef.current = 0;
          }
          lastUi = pct;
        }
      }
      levelRafRef.current = requestAnimationFrame(tick);
    };
    levelRafRef.current = requestAnimationFrame(tick);
    void lastUi;
  }, [sendBargeIn, showError, stopLevelLoop, stopPlayback]);

  // ---- auto-scroll transcript ----
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, status]);

  // ---- full cleanup on unmount ----
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current);
      stopPlayback();
      stopPing();
      stopLevelLoop();
      const ws = wsRef.current;
      wsRef.current = null;
      if (ws) {
        try {
          ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
        } catch {
          /* noop */
        }
        try {
          ws.close();
        } catch {
          /* noop */
        }
      }
      const node = workletNodeRef.current;
      workletNodeRef.current = null;
      if (node) {
        try {
          node.disconnect();
        } catch {
          /* noop */
        }
      }
      const src = sourceRef.current;
      sourceRef.current = null;
      if (src) {
        try {
          src.disconnect();
        } catch {
          /* noop */
        }
      }
      const cap = captureCtxRef.current;
      captureCtxRef.current = null;
      if (cap) void cap.close().catch(() => {});
      const play = playbackCtxRef.current;
      playbackCtxRef.current = null;
      if (play) void play.close().catch(() => {});
      const st = streamRef.current;
      streamRef.current = null;
      if (st) st.getTracks().forEach((t) => t.stop());
      if (workletUrlRef.current) {
        try {
          URL.revokeObjectURL(workletUrlRef.current);
        } catch {
          /* noop */
        }
        workletUrlRef.current = null;
      }
    };
  }, [stopLevelLoop, stopPing, stopPlayback]);

  const speaking = status === "Speaking";
  const listening = status === "Listening";
  const thinking = status === "Thinking";
  const interrupted = status === "Interrupted";

  return (
    <div className="min-h-[calc(100vh-4rem)] w-full bg-zinc-950 text-zinc-100">
      <style>{`
        @keyframes talk-pulse-ring { 0% { transform: scale(1); opacity: .5; } 100% { transform: scale(1.5); opacity: 0; } }
        @keyframes talk-flash { 0%, 100% { opacity: 1; } 50% { opacity: .45; } }
        @keyframes talk-eq { 0%, 100% { transform: scaleY(0.35); } 50% { transform: scaleY(1); } }
      `}</style>

      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-32 left-1/2 h-96 w-[42rem] -translate-x-1/2 rounded-full bg-orange-500/10 blur-3xl" />
        <div className="absolute bottom-0 right-0 h-72 w-72 rounded-full bg-amber-400/5 blur-3xl" />
      </div>

      <div className="relative mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-6 sm:px-6">
        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur-xl sm:p-5">
          <div>
            <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">Live Talk</h1>
            <p className="mt-1 text-sm text-zinc-400">Realtime full-duplex voice • 16kHz PCM in • MP3 out</p>
            {voice ? (
              <span className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-orange-400/30 bg-orange-500/10 px-2.5 py-1 text-xs font-medium text-orange-200">
                <Volume2 className="h-3.5 w-3.5" />
                {voice}
              </span>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => endSession(true)}
            className="inline-flex min-h-[56px] items-center gap-2 rounded-xl border border-red-400/30 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-200 transition hover:bg-red-500/20 active:scale-95"
          >
            <PhoneOff className="h-4 w-4" />
            End
          </button>
        </div>

        {/* State badge */}
        <div className="flex items-center justify-center" aria-live="polite">
          {status === "Idle" && !connecting && (
            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-zinc-800/80 px-4 py-1.5 text-sm font-medium text-zinc-300">
              <span className="h-2 w-2 rounded-full bg-zinc-400" />
              Idle
            </span>
          )}
          {connecting && (
            <span className="inline-flex items-center gap-2 rounded-full border border-sky-400/40 bg-sky-500/10 px-4 py-1.5 text-sm font-medium text-sky-200">
              <Loader2 className="h-4 w-4 animate-spin" />
              Connecting
            </span>
          )}
          {listening && (
            <span className="inline-flex items-center gap-2 rounded-full border border-red-400/40 bg-red-500/15 px-4 py-1.5 text-sm font-medium text-red-200">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-red-500" />
              </span>
              Listening
            </span>
          )}
          {thinking && (
            <span className="inline-flex items-center gap-2 rounded-full border border-amber-400/40 bg-amber-500/10 px-4 py-1.5 text-sm font-medium text-amber-200">
              <Loader2 className="h-4 w-4 animate-spin" />
              Thinking
            </span>
          )}
          {speaking && (
            <span className="inline-flex items-center gap-2 rounded-full border border-green-400/40 bg-green-500/10 px-4 py-1.5 text-sm font-medium text-green-200">
              <span className="flex h-4 items-end gap-[3px]">
                {[0, 1, 2, 3].map((i) => (
                  <span
                    key={i}
                    className="w-[3px] origin-bottom rounded-full bg-green-400"
                    style={{ height: "100%", animation: `talk-eq ${0.7 + i * 0.12}s ease-in-out ${i * 0.09}s infinite` }}
                  />
                ))}
              </span>
              Speaking
            </span>
          )}
          {interrupted && (
            <span
              className="inline-flex items-center gap-2 rounded-full border border-yellow-400/50 bg-yellow-500/15 px-4 py-1.5 text-sm font-medium text-yellow-200"
              style={{ animation: "talk-flash 0.5s ease-in-out 2" }}
            >
              <Zap className="h-4 w-4" />
              Interrupted
            </span>
          )}
        </div>

        {/* Center stage */}
        <div className="flex flex-col items-center gap-5 rounded-3xl border border-white/10 bg-white/5 px-4 py-8 backdrop-blur-xl sm:py-10">
          <div className="relative flex items-center justify-center">
            {sessionActive && listening && (
              <span
                className="absolute inline-flex h-[96px] w-[96px] rounded-full bg-red-500/30"
                style={{ animation: "talk-pulse-ring 1.6s ease-out infinite" }}
              />
            )}
            <button
              type="button"
              aria-label={sessionActive ? "End voice session" : "Start live talk session"}
              onClick={() => (sessionActive ? endSession(false) : void startSession())}
              disabled={connecting}
              className={`relative flex h-[96px] w-[96px] touch-none select-none items-center justify-center rounded-full border text-white shadow-2xl transition active:scale-95 ${
                connecting || thinking
                  ? "cursor-wait border-amber-400/40 bg-gradient-to-b from-zinc-700 to-zinc-800"
                  : sessionActive
                    ? "border-red-400/60 bg-gradient-to-b from-red-500 to-red-700 shadow-red-500/30"
                    : "border-orange-400/40 bg-gradient-to-b from-orange-500 to-orange-700 shadow-orange-500/25 hover:from-orange-400 hover:to-orange-600"
              } disabled:opacity-70`}
            >
              {connecting || thinking ? (
                <Loader2 className="h-10 w-10 animate-spin" />
              ) : sessionActive ? (
                <MicOff className="h-10 w-10" />
              ) : (
                <Mic className="h-10 w-10" />
              )}
            </button>
          </div>

          {/* Mic level meter */}
          <div className="w-full max-w-xs">
            <div
              className="h-2.5 w-full overflow-hidden rounded-full bg-zinc-800"
              role="meter"
              aria-label="Microphone level"
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                ref={levelBarRef}
                className="h-full rounded-full bg-gradient-to-r from-orange-600 via-orange-400 to-amber-200 transition-[width] duration-100"
                style={{ width: "0%" }}
              />
            </div>
          </div>

          <p className="text-center text-sm text-zinc-400">
            Talk naturally — pause and it answers. Tap <span className="text-amber-300">⚡</span> to cut in.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-2">
            {speaking && (
              <button
                type="button"
                onClick={handleInterrupt}
                className="inline-flex min-h-[56px] items-center gap-2 rounded-xl border border-amber-400/40 bg-amber-500/15 px-5 py-2 text-sm font-semibold text-amber-200 transition hover:bg-amber-500/25 active:scale-95"
              >
                <Zap className="h-4 w-4" />
                Cut in
              </button>
            )}
            {wsClosed && !sessionActive && (
              <button
                type="button"
                onClick={() => void startSession()}
                className="inline-flex min-h-[56px] items-center gap-2 rounded-xl border border-orange-400/40 bg-orange-500/15 px-5 py-2 text-sm font-semibold text-orange-200 transition hover:bg-orange-500/25 active:scale-95"
              >
                <RefreshCw className="h-4 w-4" />
                Reconnect
              </button>
            )}
          </div>
        </div>

        {/* Error toast */}
        {error && (
          <button
            type="button"
            onClick={() => setError(null)}
            className="min-h-[56px] w-full rounded-xl border border-red-400/40 bg-red-500/10 px-4 py-2.5 text-left text-sm text-red-200 backdrop-blur-xl"
          >
            {error} <span className="underline underline-offset-2">Dismiss</span>
          </button>
        )}

        {/* Live transcript */}
        <div className="rounded-3xl border border-white/10 bg-white/5 backdrop-blur-xl">
          <div className="border-b border-white/10 px-4 py-3 sm:px-5">
            <p className="text-sm font-medium text-zinc-300">
              {connecting ? "Connecting…" : listening ? "Listening…" : thinking ? "Thinking…" : speaking ? "Speaking…" : interrupted ? "Interrupted" : "Live transcript"}
              {(listening || thinking || speaking) && <span className="animate-pulse"> ▍</span>}
            </p>
          </div>
          <div ref={scrollRef} className="max-h-[42vh] min-h-[220px] space-y-3 overflow-y-auto px-4 py-4 sm:px-5">
            {messages.length === 0 ? (
              <div className="flex h-40 flex-col items-center justify-center gap-2 text-center">
                <Mic className="h-6 w-6 text-zinc-600" />
                <p className="text-sm text-zinc-500">No speech yet — tap the mic and talk naturally.</p>
              </div>
            ) : (
              messages.map((m, i) =>
                m.role === "user" ? (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[85%] rounded-2xl rounded-br-md border border-orange-400/25 bg-orange-500/15 px-3.5 py-2.5 text-sm leading-relaxed text-orange-100">
                      {m.text}
                    </div>
                  </div>
                ) : (
                  <div key={i} className="flex justify-start">
                    <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm leading-relaxed text-zinc-100 backdrop-blur">
                      {m.text}
                    </div>
                  </div>
                )
              )
            )}
            {thinking && (
              <div className="flex justify-start">
                <div className="inline-flex items-center gap-2 rounded-2xl rounded-bl-md border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-zinc-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Thinking…
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
