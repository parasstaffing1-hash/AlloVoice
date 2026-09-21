"use client";

import dynamic from "next/dynamic";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2, Mic, Send, Volume2 } from "lucide-react";

import type { AvatarViewerProps } from "@/components/avatar-viewer";

const AvatarViewer = dynamic<AvatarViewerProps>(
  () => import("@/components/avatar-viewer").then((r: any) => r.default),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full min-h-[280px] w-full flex-col items-center justify-center gap-2">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-600 border-t-orange-400" />
        <p className="text-xs text-zinc-400">Loading avatar…</p>
      </div>
    ),
  }
);

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const FALLBACK_BRAND = "#f97316";

type Bubble = { role: "user" | "assistant"; text: string };

interface Brand {
  brand_name: string;
  primary_color: string;
  logo_url: string;
}

function EmbedAvatarInner() {
  const params = useSearchParams();
  const vrm = (() => {
    try {
      return (params.get("vrm") || "").trim();
    } catch {
      return "";
    }
  })();
  const business = (() => {
    try {
      return (params.get("business") || params.get("subdomain") || "").trim();
    } catch {
      return "";
    }
  })();

  const [brand, setBrand] = useState<Brand>({ brand_name: "", primary_color: FALLBACK_BRAND, logo_url: "" });
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recogRef = useRef<any>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const accent = brand.primary_color || FALLBACK_BRAND;

  // Brand header (public endpoint, no login).
  useEffect(() => {
    if (!business) return;
    fetch(`${API}/api/branding/portal-theme?subdomain=${encodeURIComponent(business)}`)
      .then((r: any) => r.json().then((j: any) => ({ ok: r.ok, body: j })))
      .then((r: any) => {
        if (!r.ok) return;
        try {
          setBrand({
            brand_name: String(r?.body?.brand_name || ""),
            primary_color: String(r?.body?.primary_color || FALLBACK_BRAND),
            logo_url: String(r?.body?.logo_url || ""),
          });
        } catch {
          /* keep fallback brand */
        }
      })
      .catch((e: any) => {
        /* brand is decorative; stay on fallback */
      });
  }, [business]);

  // Keep the latest bubbles in view.
  useEffect(() => {
    try {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    } catch {
      /* noop */
    }
  }, [bubbles, busy]);

  // Stop speech recognition on unmount.
  useEffect(() => {
    return () => {
      try {
        recogRef.current?.stop?.();
      } catch {
        /* noop */
      }
      try {
        audioRef.current?.pause?.();
      } catch {
        /* noop */
      }
    };
  }, []);

  const speak = useCallback((text: string) => {
    const clean = (text || "").trim();
    if (!clean) return;
    fetch(`${API}/api/voice-agent/demo-speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: clean }),
    })
      .then((r: any) => r.json().then((j: any) => ({ ok: r.ok, body: j })))
      .then((r: any) => {
        if (!r.ok) throw new Error(r?.body?.detail || "Speech failed");
        const b64 = String(r?.body?.audio_base64 || "");
        if (!b64) return;
        try {
          const el = audioRef.current;
          if (!el) return;
          el.src = `data:audio/mpeg;base64,${b64}`;
          el.play().catch(() => {
            /* autoplay blocks: text remains visible */
          });
        } catch {
          /* text remains visible */
        }
      })
      .catch((e: any) => {
        /* spoken audio is enhancement; the text reply already shows */
      });
  }, []);

  const send = useCallback(
    (raw: string) => {
      const message = (raw || "").trim();
      if (!message || busy) return;
      setBusy(true);
      setError(null);
      setBubbles((prev) => [...prev, { role: "user", text: message }]);
      setInput("");
      fetch(`${API}/api/voice-agent/demo-chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      })
        .then((r: any) => r.json().then((j: any) => ({ ok: r.ok, body: j })))
        .then((r: any) => {
          if (!r.ok) throw new Error(r?.body?.detail || "Chat failed");
          const reply = String(r?.body?.reply || "").trim() || "Thanks for getting in touch — how else can I help?";
          setBubbles((prev) => [...prev, { role: "assistant", text: reply }]);
          setBusy(false);
          speak(reply);
        })
        .catch((e: any) => {
          setError(e?.message || "Something went wrong — please try again.");
          setBusy(false);
        });
    },
    [busy, speak]
  );

  const toggleMic = useCallback(() => {
    try {
      if (listening) {
        try {
          recogRef.current?.stop?.();
        } catch {
          /* noop */
        }
        setListening(false);
        return;
      }
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (!SR) {
        setError("Voice input is not supported in this browser — please type instead.");
        return;
      }
      const recog = new SR();
      recogRef.current = recog;
      recog.lang = "en-GB";
      recog.interimResults = false;
      recog.maxAlternatives = 1;
      recog.onresult = (e: any) => {
        try {
          const text = String(e?.results?.[0]?.[0]?.transcript || "").trim();
          if (text) send(text);
        } catch {
          /* noop */
        }
      };
      recog.onerror = () => {
        try {
          setListening(false);
        } catch {
          /* noop */
        }
      };
      recog.onend = () => {
        try {
          setListening(false);
        } catch {
          /* noop */
        }
      };
      setError(null);
      recog.start();
      setListening(true);
    } catch {
      setError("Could not start voice input — please type instead.");
      setListening(false);
    }
  }, [listening, send]);

  const visible = bubbles.slice(-3);

  return (
    <div className="flex h-[100dvh] w-full flex-col bg-zinc-950 text-zinc-100">
      {/* Brand header */}
      <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3" style={{ borderTop: `3px solid ${accent}` }}>
        {brand.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={brand.logo_url} alt="" className="h-7 w-7 rounded-full object-cover" />
        ) : (
          <span
            className="flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold text-white"
            style={{ background: accent }}
          >
            {(brand.brand_name || "V").slice(0, 1).toUpperCase()}
          </span>
        )}
        <p className="truncate text-sm font-semibold">{brand.brand_name || "Voice Assistant"}</p>
      </div>

      {/* Avatar or voice-only fallback */}
      <div className="relative min-h-0 flex-1">
        {vrm ? (
          <AvatarViewer vrmUrl={vrm} audioRef={audioRef} emotion="warm" className="relative h-full w-full overflow-hidden" />
        ) : (
          <div className="flex h-full min-h-[280px] flex-col items-center justify-center gap-3 p-6 text-center">
            <span
              className="flex h-16 w-16 items-center justify-center rounded-full text-white"
              style={{ background: accent }}
            >
              <Volume2 className="h-7 w-7" />
            </span>
            <p className="text-sm font-medium text-zinc-200">Voice assistant</p>
            <p className="max-w-[28ch] text-xs text-zinc-500">No avatar configured — tap the mic or type below to talk.</p>
          </div>
        )}
        <audio ref={audioRef} className="hidden" playsInline preload="auto" />
      </div>

      {/* Transcript (max 3 visible) */}
      <div ref={scrollRef} className="max-h-44 space-y-2 overflow-y-auto px-4 py-2">
        {visible.map((b, i) =>
          b.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md px-3 py-2 text-sm text-white" style={{ background: accent }}>
                {b.text}
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-white/10 bg-white/5 px-3 py-2 text-sm text-zinc-100">
                {b.text}
              </div>
            </div>
          )
        )}
        {busy ? (
          <div className="flex justify-start">
            <div className="inline-flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-zinc-400">
              <Loader2 className="h-4 w-4 animate-spin" />
              Thinking…
            </div>
          </div>
        ) : null}
      </div>

      {error ? (
        <button
          type="button"
          onClick={() => setError(null)}
          className="mx-4 mb-1 rounded-xl border border-red-400/40 bg-red-500/10 px-3 py-2 text-left text-xs text-red-200"
        >
          {error}
        </button>
      ) : null}

      {/* Input row */}
      <form
        className="flex items-center gap-2 border-t border-white/10 p-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <button
          type="button"
          aria-label={listening ? "Stop listening" : "Talk with your voice"}
          onClick={toggleMic}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-white"
          style={{ background: listening ? "#dc2626" : accent }}
        >
          <Mic className="h-5 w-5" />
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message…"
          className="h-10 min-w-0 flex-1 rounded-xl border border-white/10 bg-white/5 px-3 text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none"
        />
        <button
          type="submit"
          aria-label="Send message"
          disabled={busy || !input.trim()}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-white disabled:opacity-40"
          style={{ background: accent }}
        >
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
}

export default function EmbedAvatarPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-[100dvh] w-full items-center justify-center bg-zinc-950 text-sm text-zinc-400">
          Loading…
        </div>
      }
    >
      <EmbedAvatarInner />
    </Suspense>
  );
}
