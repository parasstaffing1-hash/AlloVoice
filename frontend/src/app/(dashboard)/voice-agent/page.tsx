"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/store";
import { Mic, MicOff, Volume2, Trash2, Loader2, PhoneOff } from "lucide-react";

type Status = "Idle" | "Listening" | "Thinking" | "Speaking";
type Msg = { role: "user" | "assistant"; text: string };

const BAR_COUNT = 24;

function shortVoiceName(raw: string): string {
  if (!raw) return "";
  // e.g. "en-GB-SoniaNeural" -> "Sonia", "en-GB-LibbyNeural" -> "Libby"
  const parts = raw.split("-");
  const last = parts[parts.length - 1] || raw;
  return last.replace(/Neural$/i, "") || raw;
}

function statusLine(s: Status): string {
  if (s === "Listening") return "Listening…";
  if (s === "Thinking") return "Thinking…";
  if (s === "Speaking") return "Speaking…";
  return "Press and hold the mic, or tap to toggle";
}

export default function VoiceAgentPage() {
  const { token } = useAuth();
  const [status, setStatus] = useState<Status>("Idle");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [voicePrimary, setVoicePrimary] = useState<string>("");
  const [voiceFallback, setVoiceFallback] = useState<string>("");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const statusRef = useRef<Status>("Idle");
  const pressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const holdFiredRef = useRef(false);
  const recordingRef = useRef(false);
  const holdModeRef = useRef(false);
  const interruptArmedRef = useRef(false);
  const justStoppedHoldRef = useRef(false);
  const processingRef = useRef(false);
  const pressStartRef = useRef(0);

  const setBothStatus = useCallback((s: Status) => {
    statusRef.current = s;
    setStatus(s);
  }, []);

  const showError = useCallback((msg: string) => {
    setError(msg);
  }, []);

  const interruptPlayback = useCallback(() => {
    const a = audioRef.current;
    if (a) {
      try {
        a.pause();
      } catch {
        /* noop */
      }
      audioRef.current = null;
    }
  }, []);

  const stopStream = useCallback(() => {
    const st = streamRef.current;
    if (st) {
      st.getTracks().forEach((t) => {
        try {
          t.stop();
        } catch {
          /* noop */
        }
      });
      streamRef.current = null;
    }
  }, []);

  // ---- per-turn pipeline: base64 -> transcribe -> chat -> speak -> play ----
  const handleAudioBase64 = useCallback(
    (audioBase64: string) => {
      if (!token) {
        showError("Sign in required to use the voice assistant.");
        setBothStatus("Idle");
        processingRef.current = false;
        return;
      }
      setBothStatus("Thinking");
      api.voiceAgent
        .transcribe(audioBase64, token)
        .then((r: any) => {
          const transcript: string = (r?.transcript || "").trim();
          if (!transcript) {
            setMessages((prev) => [
              ...prev,
              { role: "assistant", text: "Didn't catch that — please try again." },
            ]);
            setBothStatus("Idle");
            processingRef.current = false;
            return;
          }
          setMessages((prev) => [...prev, { role: "user", text: transcript }]);
          api.voiceAgent
            .chat(transcript, sessionIdRef.current, token)
            .then((r: any) => {
              const reply: string = r?.reply || "";
              if (r?.session_id) sessionIdRef.current = r.session_id;
              if (!reply.trim()) {
                setMessages((prev) => [
                  ...prev,
                  { role: "assistant", text: "Didn't catch that — please try again." },
                ]);
                setBothStatus("Idle");
                processingRef.current = false;
                return;
              }
              setMessages((prev) => [...prev, { role: "assistant", text: reply }]);
              api.voiceAgent
                .speak(reply, token)
                .then((r: any) => {
                  const b64: string = r?.audio_base64 || "";
                  if (!b64) {
                    // No audio returned — still show text, back to idle.
                    setBothStatus("Idle");
                    processingRef.current = false;
                    return;
                  }
                  try {
                    interruptPlayback();
                    const audio = new Audio(`data:audio/mpeg;base64,${b64}`);
                    audioRef.current = audio;
                    setBothStatus("Speaking");
                    processingRef.current = false;
                    audio.onended = () => {
                      if (audioRef.current === audio) audioRef.current = null;
                      setBothStatus("Idle");
                    };
                    audio.onerror = () => {
                      if (audioRef.current === audio) audioRef.current = null;
                      showError("Reply playback failed.");
                      setBothStatus("Idle");
                    };
                    audio.play().catch(() => {
                      if (audioRef.current === audio) audioRef.current = null;
                      showError("Browser blocked autoplay — press replay to hear the reply.");
                      setBothStatus("Idle");
                    });
                  } catch {
                    showError("Reply playback failed.");
                    setBothStatus("Idle");
                    processingRef.current = false;
                  }
                })
                .catch((e: any) => {
                  showError(e?.message || "Voice synthesis failed.");
                  setBothStatus("Idle");
                  processingRef.current = false;
                });
            })
            .catch((e: any) => {
              showError(e?.message || "Chat request failed.");
              setBothStatus("Idle");
              processingRef.current = false;
            });
        })
        .catch((e: any) => {
          showError(e?.message || "Transcription failed.");
          setBothStatus("Idle");
          processingRef.current = false;
        });
    },
    [token, interruptPlayback, setBothStatus, showError]
  );

  const stopAndProcess = useCallback(() => {
    const rec = mediaRecorderRef.current;
    if (!rec || !recordingRef.current) return;
    if (processingRef.current) return;
    processingRef.current = true;
    recordingRef.current = false;
    if (pressTimerRef.current) {
      clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
    setBothStatus("Thinking");
    try {
      rec.onstop = () => {
        stopStream();
        mediaRecorderRef.current = null;
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        chunksRef.current = [];
        if (blob.size === 0) {
          showError("No audio captured — please try again.");
          setBothStatus("Idle");
          processingRef.current = false;
          return;
        }
        const reader = new FileReader();
        reader.onloadend = () => {
          const dataUrl = String(reader.result || "");
          const base64 = dataUrl.includes(",") ? dataUrl.split(",")[1] : dataUrl;
          if (!base64) {
            showError("Audio encoding failed — please try again.");
            setBothStatus("Idle");
            processingRef.current = false;
            return;
          }
          handleAudioBase64(base64);
        };
        reader.onerror = () => {
          showError("Audio encoding failed — please try again.");
          setBothStatus("Idle");
          processingRef.current = false;
        };
        reader.readAsDataURL(blob);
      };
      rec.stop();
    } catch {
      showError("Could not stop recording.");
      setBothStatus("Idle");
      processingRef.current = false;
    }
  }, [handleAudioBase64, setBothStatus, showError, stopStream]);

  const startRecording = useCallback(() => {
    if (recordingRef.current || statusRef.current === "Thinking") return;
    if (!token) {
      showError("Sign in required to use the voice assistant.");
      return;
    }
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      showError("Microphone is not available in this browser.");
      return;
    }
    if (typeof MediaRecorder === "undefined") {
      showError("Audio recording is not supported in this browser.");
      return;
    }
    // New utterance interrupts any playing reply.
    interruptPlayback();
    setError(null);
    chunksRef.current = [];
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream: MediaStream) => {
        streamRef.current = stream;
        const mimeType =
          MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : undefined;
        const rec = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
        mediaRecorderRef.current = rec;
        rec.ondataavailable = (e: BlobEvent) => {
          if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
        };
        // onstop is assigned in stopAndProcess; keep a no-op guard here.
        rec.onerror = () => {
          showError("Recording failed — please try again.");
          setBothStatus("Idle");
          stopStream();
          mediaRecorderRef.current = null;
          recordingRef.current = false;
          processingRef.current = false;
        };
        rec.start();
        pressStartRef.current = Date.now();
        recordingRef.current = true;
        setBothStatus("Listening");
      })
      .catch(() => {
        showError("Microphone access denied — allow the mic and try again.");
        setBothStatus("Idle");
      });
  }, [token, interruptPlayback, setBothStatus, showError, stopStream]);

  // ---- push-to-talk + click-toggle wiring ----
  // Single source of truth: recordingRef. Press starts a hold timer;
  // holding 350ms+ records in hold mode (release stops). A short tap
  // toggles via the click handler. No flag can swallow a stop twice.
  const handlePressStart = useCallback(() => {
    if (statusRef.current === "Thinking") return;
    if (statusRef.current === "Speaking") {
      // Barge-in: cut the reply, start listening (toggle-ON).
      // The trailing click is consumed so it can't instant-stop.
      interruptPlayback();
      setBothStatus("Idle");
      interruptArmedRef.current = true;
      startRecording();
      return;
    }
    if (recordingRef.current) return; // already listening; release/click stops
    holdModeRef.current = false;
    holdFiredRef.current = false;
    if (pressTimerRef.current) clearTimeout(pressTimerRef.current);
    pressTimerRef.current = setTimeout(() => {
      holdFiredRef.current = true;
      holdModeRef.current = true;
      startRecording();
    }, 350);
  }, [interruptPlayback, setBothStatus, startRecording]);

  const handlePressEnd = useCallback(() => {
    if (pressTimerRef.current) {
      clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
    if (!recordingRef.current) return;
    if (holdModeRef.current) {
      // Genuine press-and-hold release -> finish the turn.
      holdModeRef.current = false;
      justStoppedHoldRef.current = true;
      setTimeout(() => {
        justStoppedHoldRef.current = false;
      }, 400);
      stopAndProcess();
    }
    // Short tap: stay listening (toggle-ON). The click handler toggles.
  }, [stopAndProcess]);

  const handleMicClick = useCallback(() => {
    if (justStoppedHoldRef.current) return; // click trailing a hold-release
    if (interruptArmedRef.current) {
      interruptArmedRef.current = false;
      return; // click trailing a barge-in tap
    }
    // Toggle: stop while listening, start while idle.
    if (recordingRef.current) stopAndProcess();
    else startRecording();
  }, [stopAndProcess, startRecording]);

  const endChat = useCallback(() => {
    interruptPlayback();
    if (mediaRecorderRef.current && statusRef.current === "Listening") {
      try {
        mediaRecorderRef.current.onstop = null;
        mediaRecorderRef.current.stop();
      } catch {
        /* noop */
      }
      mediaRecorderRef.current = null;
    }
    stopStream();
    if (pressTimerRef.current) {
      clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
    sessionIdRef.current = null;
    chunksRef.current = [];
    processingRef.current = false;
    recordingRef.current = false;
    holdModeRef.current = false;
    interruptArmedRef.current = false;
    setMessages([]);
    setError(null);
    setBothStatus("Idle");
  }, [interruptPlayback, setBothStatus, stopStream]);

  const clearTranscript = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  const replayLast = useCallback(() => {
    if (!token) {
      showError("Sign in required to use the voice assistant.");
      return;
    }
    if (statusRef.current === "Listening" || statusRef.current === "Thinking") return;
    const last = [...messages].reverse().find((m) => m.role === "assistant");
    if (!last) {
      showError("Nothing to replay yet — hold the mic and speak first.");
      return;
    }
    interruptPlayback();
    setError(null);
    setBothStatus("Thinking");
    api.voiceAgent
      .speak(last.text, token)
      .then((r: any) => {
        const b64: string = r?.audio_base64 || "";
        if (!b64) {
          showError("No audio returned for replay.");
          setBothStatus("Idle");
          return;
        }
        try {
          const audio = new Audio(`data:audio/mpeg;base64,${b64}`);
          audioRef.current = audio;
          setBothStatus("Speaking");
          audio.onended = () => {
            if (audioRef.current === audio) audioRef.current = null;
            setBothStatus("Idle");
          };
          audio.onerror = () => {
            if (audioRef.current === audio) audioRef.current = null;
            showError("Replay failed.");
            setBothStatus("Idle");
          };
          audio.play().catch(() => {
            if (audioRef.current === audio) audioRef.current = null;
            showError("Browser blocked autoplay.");
            setBothStatus("Idle");
          });
        } catch {
          showError("Replay failed.");
          setBothStatus("Idle");
        }
      })
      .catch((e: any) => {
        showError(e?.message || "Replay failed.");
        setBothStatus("Idle");
      });
  }, [token, messages, interruptPlayback, setBothStatus, showError]);

  // Fetch voices once.
  useEffect(() => {
    if (!token) return;
    api.voiceAgent
      .voices(token)
      .then((r: any) => {
        if (r?.primary) setVoicePrimary(String(r.primary));
        if (r?.fallback) setVoiceFallback(String(r.fallback));
      })
      .catch(() => {
        /* voice badge stays on default subtitle */
      });
  }, [token]);

  // Auto-scroll transcript.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, status]);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      if (pressTimerRef.current) clearTimeout(pressTimerRef.current);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        try {
          mediaRecorderRef.current.stop();
        } catch {
          /* noop */
        }
      }
      const st = streamRef.current;
      if (st) st.getTracks().forEach((t) => t.stop());
      const a = audioRef.current;
      if (a) {
        try {
          a.pause();
        } catch {
          /* noop */
        }
      }
    };
  }, []);

  const listening = status === "Listening";
  const thinking = status === "Thinking";
  const speaking = status === "Speaking";
  const waveActive = listening || speaking;

  return (
    <div className="min-h-[calc(100vh-4rem)] w-full bg-zinc-950 text-zinc-100">
      <style>{`
        @keyframes va-bar { 0%, 100% { transform: scaleY(0.25); } 50% { transform: scaleY(1); } }
        @keyframes va-eq { 0%, 100% { transform: scaleY(0.35); } 50% { transform: scaleY(1); } }
      `}</style>

      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-32 left-1/2 h-96 w-[42rem] -translate-x-1/2 rounded-full bg-orange-500/10 blur-3xl" />
        <div className="absolute bottom-0 right-0 h-72 w-72 rounded-full bg-amber-400/5 blur-3xl" />
      </div>

      <div className="relative mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-6 sm:px-6">
        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur-xl sm:p-5">
          <div>
            <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">Voice Assistant</h1>
            <p className="mt-1 text-sm text-zinc-400">UK English • Sonia voice</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-orange-400/30 bg-orange-500/10 px-2.5 py-1 text-xs font-medium text-orange-200">
                <Volume2 className="h-3.5 w-3.5" />
                {voicePrimary ? shortVoiceName(voicePrimary) : "Sonia"}
              </span>
              {voiceFallback ? (
                <span className="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-zinc-400">
                  Fallback: {shortVoiceName(voiceFallback)}
                </span>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={endChat}
            className="inline-flex items-center gap-2 rounded-xl border border-red-400/30 bg-red-500/10 px-3.5 py-2 text-sm font-medium text-red-200 transition hover:bg-red-500/20 active:scale-95"
          >
            <PhoneOff className="h-4 w-4" />
            End chat
          </button>
        </div>

        {/* State badge */}
        <div className="flex items-center justify-center">
          {status === "Idle" && (
            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-zinc-800/80 px-4 py-1.5 text-sm font-medium text-zinc-300">
              <span className="h-2 w-2 rounded-full bg-zinc-400" />
              Idle
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
                    style={{
                      height: "100%",
                      animation: `va-eq ${0.7 + i * 0.12}s ease-in-out ${i * 0.09}s infinite`,
                    }}
                  />
                ))}
              </span>
              Speaking
            </span>
          )}
        </div>

        {/* Center stage */}
        <div className="flex flex-col items-center gap-5 rounded-3xl border border-white/10 bg-white/5 px-4 py-8 backdrop-blur-xl sm:py-10">
          <div className="relative flex items-center justify-center">
            {listening && (
              <>
                <span className="absolute inline-flex h-[88px] w-[88px] animate-ping rounded-full bg-red-500/30" />
                <span
                  className="absolute inline-flex h-[88px] w-[88px] animate-ping rounded-full bg-red-500/20"
                  style={{ animationDelay: "0.4s" }}
                />
              </>
            )}
            <button
              type="button"
              aria-label={listening ? "Stop listening" : "Hold to talk, or tap to toggle"}
              onPointerDown={handlePressStart}
              onPointerUp={handlePressEnd}
              onPointerLeave={handlePressEnd}
              onClick={handleMicClick}
              onContextMenu={(e) => e.preventDefault()}
              disabled={thinking}
              className={`relative flex h-[88px] w-[88px] touch-none select-none items-center justify-center rounded-full border text-white shadow-2xl transition active:scale-95 ${
                listening
                  ? "scale-105 border-red-400/60 bg-gradient-to-b from-red-500 to-red-700 shadow-red-500/30"
                  : thinking
                    ? "cursor-wait border-amber-400/40 bg-gradient-to-b from-zinc-700 to-zinc-800 opacity-90"
                    : speaking
                      ? "border-green-400/50 bg-gradient-to-b from-green-500 to-emerald-700 shadow-green-500/25"
                      : "border-orange-400/40 bg-gradient-to-b from-orange-500 to-orange-700 shadow-orange-500/25 hover:from-orange-400 hover:to-orange-600"
              } ${thinking ? "" : "cursor-pointer"}`}
            >
              {thinking ? (
                <Loader2 className="h-9 w-9 animate-spin" />
              ) : listening ? (
                <MicOff className="h-9 w-9" />
              ) : (
                <Mic className="h-9 w-9" />
              )}
            </button>
          </div>
          <p className="text-center text-sm text-zinc-400">
            {thinking ? "Working on your reply…" : "Press & hold to talk — or tap once, speak, tap again"}
          </p>

          {/* Voice wave */}
          <div className="flex h-12 items-center gap-1" aria-hidden="true">
            {Array.from({ length: BAR_COUNT }).map((_, i) => (
              <span
                key={i}
                className={`w-1 rounded-full ${
                  waveActive
                    ? "bg-gradient-to-t from-orange-600 via-orange-400 to-amber-200"
                    : "bg-zinc-700"
                }`}
                style={{
                  height: waveActive ? "100%" : `${18 + ((i * 37) % 20)}%`,
                  transformOrigin: "center",
                  animation: waveActive
                    ? `va-bar ${0.9 + ((i * 53) % 7) / 10}s ease-in-out ${(i % 8) * 0.08}s infinite`
                    : undefined,
                  opacity: waveActive ? 1 : 0.6,
                }}
              />
            ))}
          </div>

          {/* Secondary wired controls */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={replayLast}
              disabled={thinking || listening}
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-zinc-200 transition hover:bg-white/10 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Volume2 className="h-4 w-4" />
              Replay
            </button>
            <button
              type="button"
              onClick={clearTranscript}
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-zinc-200 transition hover:bg-white/10 active:scale-95"
            >
              <Trash2 className="h-4 w-4" />
              Clear
            </button>
          </div>
        </div>

        {/* Error toast line */}
        {error && (
          <button
            type="button"
            onClick={() => setError(null)}
            className="w-full rounded-xl border border-red-400/40 bg-red-500/10 px-4 py-2.5 text-left text-sm text-red-200 backdrop-blur-xl"
          >
            {error} <span className="underline underline-offset-2">Dismiss</span>
          </button>
        )}

        {/* Live transcript panel */}
        <div className="rounded-3xl border border-white/10 bg-white/5 backdrop-blur-xl">
          <div className="border-b border-white/10 px-4 py-3 sm:px-5">
            <p className="text-sm font-medium text-zinc-300">
              {statusLine(status)}
              {(listening || thinking || speaking) && <span className="animate-pulse"> ▍</span>}
            </p>
          </div>
          <div ref={scrollRef} className="max-h-[42vh] min-h-[220px] space-y-3 overflow-y-auto px-4 py-4 sm:px-5">
            {messages.length === 0 ? (
              <div className="flex h-40 flex-col items-center justify-center gap-2 text-center">
                <Mic className="h-6 w-6 text-zinc-600" />
                <p className="text-sm text-zinc-500">
                  No messages yet — hold the mic and ask something.
                </p>
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
            {listening && (
              <div className="flex justify-end">
                <div className="inline-flex items-center gap-2 rounded-2xl rounded-br-md border border-red-400/25 bg-red-500/10 px-3.5 py-2.5 text-sm text-red-200">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-red-500" />
                  </span>
                  Listening…
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
