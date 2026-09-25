"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Box,
  Mic,
  Copy,
  Check,
  Smile,
  Palette,
  Code,
  Loader2,
  Play,
  Save,
} from "lucide-react";
import type { AvatarEmotion, AvatarViewerProps } from "@/components/avatar-viewer";

const AvatarViewer = dynamic<AvatarViewerProps>(
  () => import("@/components/avatar-viewer").then((r: any) => r.default),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[420px] w-full flex-col items-center justify-center gap-2 rounded-2xl border border-white/10 bg-zinc-900/60">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-600 border-t-orange-400" />
        <p className="text-xs text-zinc-400">Preparing 3D preview…</p>
      </div>
    ),
  }
);

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const RPM_URL = "https://demo.readyplayer.me/avatar?frameApi";
const STORE_KEY = "vf_avatar";

const EMOTIONS: AvatarEmotion[] = ["calm", "neutral", "rushed", "frustrated", "upset", "warm", "worried"];

const EMOTION_HINT: Record<AvatarEmotion, string> = {
  calm: "Soft, relaxed face",
  neutral: "Resting face",
  rushed: "Alert, slightly surprised",
  frustrated: "Angry preset",
  upset: "Sad preset",
  warm: "Happy, smiling",
  worried: "Surprised + sad blend",
};

export default function AvatarStudioPage() {
  const [draftUrl, setDraftUrl] = useState("");
  // Bundled default so the studio is never empty (RPM is unreachable
  // in some regions — see RPM iframe below, kept as an optional extra).
  const [vrmUrl, setVrmUrl] = useState("/avatars/default.glb");
  const [voice, setVoice] = useState("Sonia");
  const [emotion, setEmotion] = useState<AvatarEmotion>("neutral");
  const [testText, setTestText] = useState("Hi there! Thanks for visiting — how can I help today?");
  const [busy, setBusy] = useState(false);
  const [lastReply, setLastReply] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [savedTick, setSavedTick] = useState(false);
  const [copiedTick, setCopiedTick] = useState(false);
  const [origin, setOrigin] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const rpmFrameRef = useRef<HTMLIFrameElement | null>(null);

  // Restore saved avatar + origin for the embed snippet.
  useEffect(() => {
    try {
      setOrigin(window.location.origin);
    } catch {
      /* noop */
    }
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (raw) {
        const saved: any = JSON.parse(raw);
        if (saved?.avatar_glb_url) {
          setVrmUrl(String(saved.avatar_glb_url));
          setDraftUrl(String(saved.avatar_glb_url));
        }
        if (saved?.avatar_voice) setVoice(String(saved.avatar_voice));
      }
    } catch {
      /* corrupted storage is ignored */
    }
  }, []);

  // Ready Player Me frameApi: pick up the exported avatar URL automatically.
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      try {
        let data: any = e.data;
        if (typeof data === "string") {
          try {
            data = JSON.parse(data);
          } catch {
            return;
          }
        }
        if (!data || typeof data !== "object") return;
        const name = String(data.eventName || data.event || "");
        if (name === "v1.avatar.exported" || name === "v1.avatar.exported.glb") {
          const url = String(data?.data?.url || data?.url || "");
          if (url) {
            setDraftUrl(url);
            setVrmUrl(url);
          }
        }
      } catch {
        /* never crash on creator messages */
      }
    };
    try {
      window.addEventListener("message", onMessage);
    } catch {
      /* noop */
    }
    return () => {
      try {
        window.removeEventListener("message", onMessage);
      } catch {
        /* noop */
      }
    };
  }, []);

  const playReplyAudio = useCallback((base64: string) => {
    try {
      const el = audioRef.current;
      if (!el || !base64) return false;
      el.src = `data:audio/mpeg;base64,${base64}`;
      el.play().catch(() => {
        /* autoplay blocks are surfaced via the hint text */
      });
      return true;
    } catch {
      return false;
    }
  }, []);

  const handleTestTalk = useCallback(() => {
    const message = (testText || "").trim();
    if (!message || busy) return;
    setBusy(true);
    setError(null);
    setLastReply("");
    fetch(`${API}/api/voice-agent/demo-chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    })
      .then((r: any) => r.json().then((j: any) => ({ ok: r.ok, body: j })))
      .then((r: any) => {
        if (!r.ok) throw new Error(r?.body?.detail || "Chat request failed");
        const reply = String(r?.body?.reply || "").trim();
        if (!reply) throw new Error("Empty reply from demo chat");
        setLastReply(reply);
        // Backend demo-speak accepts { text } (voice choice is stored locally).
        return fetch(`${API}/api/voice-agent/demo-speak`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: reply, voice }),
        }).then((rr: any) => rr.json().then((jj: any) => ({ ok: rr.ok, body: jj })));
      })
      .then((r: any) => {
        if (!r.ok) throw new Error(r?.body?.detail || "Speech request failed");
        const b64 = String(r?.body?.audio_base64 || "");
        if (!b64) throw new Error("No audio returned");
        playReplyAudio(b64);
        setBusy(false);
      })
      .catch((e: any) => {
        setError(e?.message || "Test talk failed — please try again.");
        setBusy(false);
      });
  }, [testText, busy, voice, playReplyAudio]);

  const handleSave = useCallback(() => {
    try {
      localStorage.setItem(
        STORE_KEY,
        JSON.stringify({ avatar_glb_url: vrmUrl.trim(), avatar_voice: voice })
      );
      setSavedTick(true);
      setTimeout(() => {
        try {
          setSavedTick(false);
        } catch {
          /* noop */
        }
      }, 2000);
    } catch {
      setError("Could not save — browser storage is unavailable.");
    }
  }, [vrmUrl, voice]);

  const embedSnippet = useMemo(() => {
    try {
      const base = origin || "{origin}";
      const q = vrmUrl.trim() ? `?vrm=${encodeURIComponent(vrmUrl.trim())}` : "";
      return `<iframe src="${base}/embed/avatar${q}" width="380" height="640" style="border:0;border-radius:16px" allow="microphone; autoplay" title="Allo avatar"></iframe>`;
    } catch {
      return "";
    }
  }, [origin, vrmUrl]);

  const handleCopy = useCallback(() => {
    try {
      const done = () => {
        setCopiedTick(true);
        setTimeout(() => {
          try {
            setCopiedTick(false);
          } catch {
            /* noop */
          }
        }, 2000);
      };
      if (navigator?.clipboard?.writeText) {
        navigator.clipboard
          .writeText(embedSnippet)
          .then((r: any) => done())
          .catch((e: any) => setError("Copy failed — select the snippet manually."));
      } else {
        const ta = document.createElement("textarea");
        ta.value = embedSnippet;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        done();
      }
    } catch {
      setError("Copy failed — select the snippet manually.");
    }
  }, [embedSnippet]);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-orange-500/15 text-orange-300">
            <Box className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-xl font-semibold tracking-tight sm:text-2xl">Avatar Studio</h1>
            <p className="text-sm text-zinc-400">Make a 3D greeter, pick a voice and mood, then publish the embed.</p>
          </div>
          <Badge variant="secondary">3 steps</Badge>
        </div>

        <div className="grid gap-6 lg:grid-cols-[400px_minmax(0,1fr)]">
          {/* Viewer (left / sticky on desktop, stacked on mobile) */}
          <div className="lg:sticky lg:top-6 lg:self-start">
            <Card className="border-white/10 bg-white/5">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Live preview</CardTitle>
                <CardDescription>
                  {voice} voice · {emotion} mood
                </CardDescription>
              </CardHeader>
              <CardContent>
                <AvatarViewer vrmUrl={vrmUrl} audioRef={audioRef} emotion={emotion} className="relative h-[420px] w-full overflow-hidden rounded-2xl border border-white/10 bg-zinc-900/60" />
                <p className="mt-3 text-xs leading-relaxed text-zinc-500">
                  Drag to orbit · scroll to zoom. Lips follow the test reply and any spoken audio.
                </p>
                {/* Shared hidden audio element drives lip-sync in the viewer */}
                <audio ref={audioRef} className="hidden" playsInline preload="auto" />
              </CardContent>
            </Card>
          </div>

          {/* Controls (right) */}
          <div className="flex min-w-0 flex-col gap-6">
            {/* Step 1 */}
            <Card className="border-white/10 bg-white/5">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Badge>Step 1</Badge>
                  <CardTitle className="text-base">Make your avatar</CardTitle>
                </div>
                <CardDescription>Build with Ready Player Me below (may not load in all regions), or paste a .glb / .vrm URL — a default avatar is preloaded.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="overflow-hidden rounded-xl border border-white/10 bg-zinc-900">
                  <iframe
                    ref={rpmFrameRef}
                    src={RPM_URL}
                    title="Ready Player Me creator"
                    className="h-[440px] w-full"
                    allow="camera *; microphone *"
                  />
                </div>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Input
                    value={draftUrl}
                    onChange={(e) => setDraftUrl(e.target.value)}
                    placeholder="https://… .glb or .vrm URL"
                    className="flex-1 border-white/10 bg-zinc-900"
                  />
                  <Button type="button" onClick={() => setVrmUrl(draftUrl.trim())} disabled={!draftUrl.trim()}>
                    <Play className="mr-2 h-4 w-4" />
                    Load
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Step 2 */}
            <Card className="border-white/10 bg-white/5">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Badge>Step 2</Badge>
                  <CardTitle className="text-base">Voice &amp; mood</CardTitle>
                </div>
                <CardDescription>Voice labels the demo speech; mood previews faces instantly.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div>
                  <p className="mb-2 flex items-center gap-2 text-sm font-medium text-zinc-300">
                    <Mic className="h-4 w-4 text-orange-300" /> Voice
                  </p>
                  <div className="flex gap-2">
                    {(["Sonia", "Ryan"] as const).map((v) => (
                      <Button
                        key={v}
                        type="button"
                        variant={voice === v ? "default" : "outline"}
                        onClick={() => setVoice(v)}
                        className="flex-1"
                      >
                        {v}
                        {v === "Sonia" ? <span className="ml-1 text-xs opacity-70">(default)</span> : null}
                      </Button>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-2 flex items-center gap-2 text-sm font-medium text-zinc-300">
                    <Palette className="h-4 w-4 text-orange-300" /> Mood preview
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {EMOTIONS.map((m) => (
                      <Button
                        key={m}
                        type="button"
                        size="sm"
                        variant={emotion === m ? "default" : "outline"}
                        onClick={() => setEmotion(m)}
                        title={EMOTION_HINT[m]}
                      >
                        <Smile className="mr-1.5 h-3.5 w-3.5" />
                        {m}
                      </Button>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Step 3 */}
            <Card className="border-white/10 bg-white/5">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Badge>Step 3</Badge>
                  <CardTitle className="text-base">Test + publish</CardTitle>
                </div>
                <CardDescription>Type a message — the avatar replies out loud with moving lips.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Input
                    value={testText}
                    onChange={(e) => setTestText(e.target.value)}
                    placeholder="Type something to say…"
                    className="flex-1 border-white/10 bg-zinc-900"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleTestTalk();
                    }}
                  />
                  <Button type="button" onClick={handleTestTalk} disabled={busy || !testText.trim()}>
                    {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Mic className="mr-2 h-4 w-4" />}
                    {busy ? "Talking…" : "Test talk"}
                  </Button>
                </div>
                {lastReply ? (
                  <div className="rounded-xl border border-white/10 bg-zinc-900/80 p-3 text-sm leading-relaxed text-zinc-200">
                    {lastReply}
                  </div>
                ) : null}
                {error ? (
                  <button
                    type="button"
                    onClick={() => setError(null)}
                    className="rounded-xl border border-red-400/40 bg-red-500/10 px-4 py-2.5 text-left text-sm text-red-200"
                  >
                    {error} <span className="underline underline-offset-2">Dismiss</span>
                  </button>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="secondary" onClick={handleSave} disabled={!vrmUrl.trim()}>
                    {savedTick ? <Check className="mr-2 h-4 w-4" /> : <Save className="mr-2 h-4 w-4" />}
                    {savedTick ? "Saved" : "Save avatar"}
                  </Button>
                </div>
                <div>
                  <p className="mb-2 flex items-center gap-2 text-sm font-medium text-zinc-300">
                    <Code className="mr-1 h-4 w-4 text-orange-300" /> Embed snippet
                  </p>
                  <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-xl border border-white/10 bg-zinc-950 p-3 text-xs text-zinc-300">
                    {embedSnippet}
                  </pre>
                  <Button type="button" variant="outline" size="sm" className="mt-2" onClick={handleCopy}>
                    {copiedTick ? <Check className="mr-2 h-3.5 w-3.5" /> : <Copy className="mr-2 h-3.5 w-3.5" />}
                    {copiedTick ? "Copied" : "Copy snippet"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
