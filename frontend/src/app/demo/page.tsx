"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/lib/store";
import { enterDemo } from "@/lib/demo";
import { Mic, MicOff, Volume2, Trash2, PhoneOff, Loader2, Zap, Play } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const WAVE = [14, 26, 38, 52, 66, 80, 92, 100, 92, 80, 66, 52, 38, 26, 18, 28, 44, 60, 74, 88, 96, 84, 68, 50];

type State = "idle" | "listening" | "thinking" | "speaking";
type Msg = { from: "user" | "agent"; text: string };

export default function VoiceDemoPage() {
  const [state, setState] = useState<State>("idle");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [status, setStatus] = useState("Tap the mic and speak — no login needed.");
  const [error, setError] = useState("");
  const [demoLoading, setDemoLoading] = useState(false);
  const { login, register } = useAuth();
  const router = useRouter();
  const recRef = useRef<any>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, status]);

  useEffect(() => () => {
    try { recRef.current?.stop(); } catch {}
    audioRef.current?.pause();
  }, []);

  const stopAudio = () => {
    try { audioRef.current?.pause(); } catch {}
    audioRef.current = null;
  };

  const speak = async (text: string) => {
    setState("speaking");
    setStatus("Speaking…");
    try {
      const res = await fetch(`${API}/api/voice-agent/demo-speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text.slice(0, 300) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Voice failed");
      const audio = new Audio(`data:audio/mpeg;base64,${data.audio_base64}`);
      audioRef.current = audio;
      audio.onended = () => { setState("idle"); setStatus("Tap the mic and speak."); };
      audio.onerror = () => { setState("idle"); setStatus("Tap the mic and speak."); };
      await audio.play();
    } catch (e: any) {
      setError(e?.message || "Voice failed");
      setState("idle");
      setStatus("Tap the mic and speak.");
    }
  };

  const ask = async (text: string) => {
    setState("thinking");
    setStatus("Thinking…");
    try {
      const res = await fetch(`${API}/api/voice-agent/demo-chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Chat failed");
      const reply = data.reply || "Sorry, I didn't catch that.";
      setMsgs((m) => [...m, { from: "agent", text: reply }]);
      await speak(reply);
    } catch (e: any) {
      setError(e?.message || "Chat failed");
      setState("idle");
      setStatus("Tap the mic and speak.");
    }
  };

  const startListening = () => {
    setError("");
    stopAudio();
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      setError("This browser can't do speech recognition — use Chrome or Edge.");
      return;
    }
    const rec = new SR();
    rec.lang = "en-GB";
    rec.interimResults = false;
    rec.continuous = false;
    rec.onstart = () => { setState("listening"); setStatus("Listening… speak now."); };
    rec.onresult = (event: any) => {
      const text = event.results[event.results.length - 1][0].transcript as string;
      setMsgs((m) => [...m, { from: "user", text }]);
      ask(text);
    };
    rec.onerror = () => { setState("idle"); setStatus("Tap the mic and speak."); };
    rec.onend = () => {
      setState((s) => (s === "listening" ? "idle" : s));
    };
    recRef.current = rec;
    try { rec.start(); } catch { setState("idle"); }
  };

  const stopListening = () => {
    try { recRef.current?.stop(); } catch {}
    setState("idle");
    setStatus("Tap the mic and speak.");
  };

  const endChat = () => {
    try { recRef.current?.stop(); } catch {}
    stopAudio();
    setMsgs([]);
    setError("");
    setState("idle");
    setStatus("Tap the mic and speak — no login needed.");
  };

  const enterFullDemo = async () => {
    setError("");
    setDemoLoading(true);
    try {
      await enterDemo(login, register);
      router.push("/voice-agent");
    } catch (e: any) {
      setError(e?.message || "Could not start full demo");
    } finally {
      setDemoLoading(false);
    }
  };

  const stateColor: Record<State, string> = {
    idle: "bg-zinc-500/15 text-zinc-300",
    listening: "bg-red-500/15 text-red-300 animate-pulse",
    thinking: "bg-amber-500/15 text-amber-300",
    speaking: "bg-green-500/15 text-green-300",
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <style>{`
        @keyframes va-bar { 0%,100% { transform: scaleY(0.35); opacity:.55 } 50% { transform: scaleY(1); opacity:1 } }
        .va-bar { transform-origin: bottom; animation: va-bar 1.1s ease-in-out infinite; }
        .va-frozen { transform: scaleY(0.35); opacity:.4; }
      `}</style>

      <nav className="border-b border-border/50">
        <div className="mx-auto flex h-16 max-w-4xl items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-primary" />
            <span className="font-bold gradient-text">Allo</span>
            <span className="text-xs text-muted-foreground">· voice demo</span>
          </div>
          <Link href="/register"><Button size="sm">Get started</Button></Link>
        </div>
      </nav>

      <div className="mx-auto max-w-2xl px-4 py-8 space-y-6">
        <div className="text-center">
          <h1 className="text-3xl font-bold">Talk to the assistant</h1>
          <p className="text-sm text-muted-foreground mt-1">UK English · live demo, no account needed</p>
        </div>

        <div className="flex justify-center">
          <span className={`rounded-full px-4 py-1.5 text-sm font-medium ${stateColor[state]}`}>
            {state === "idle" && "Idle"}
            {state === "listening" && "● Listening"}
            {state === "thinking" && "Thinking…"}
            {state === "speaking" && "Speaking"}
          </span>
        </div>

        <div className="flex justify-center">
          <button
            onClick={state === "listening" ? stopListening : startListening}
            aria-label={state === "listening" ? "Stop listening" : "Start talking"}
            className={`relative flex h-24 w-24 items-center justify-center rounded-full transition-all ${
              state === "listening"
                ? "bg-red-500 shadow-[0_0_60px_rgba(239,68,68,0.5)]"
                : "bg-gradient-to-br from-primary to-orange-700 shadow-[0_0_60px_rgba(249,115,22,0.45)]"
            }`}
          >
            {state === "listening" && (
              <span className="absolute inset-0 rounded-full bg-red-500/40 animate-ping" />
            )}
            {state === "listening" ? <MicOff className="h-10 w-10 text-white" /> : <Mic className="h-10 w-10 text-white" />}
          </button>
        </div>

        <div className="flex h-10 items-end justify-center gap-1">
          {WAVE.map((h, i) => (
            <span
              key={i}
              className={`w-1 rounded-full bg-primary/80 ${state === "listening" || state === "speaking" ? "va-bar" : "va-frozen"}`}
              style={{ height: `${h * 0.4}px`, animationDelay: `${(i % 10) * 0.1}s` }}
            />
          ))}
        </div>
        <p className="text-center text-sm text-muted-foreground">{status}</p>

        {error && (
          <Card className="border-red-500/50">
            <CardContent className="py-3 text-sm text-red-400">{error}</CardContent>
          </Card>
        )}

        <Card>
          <CardContent className="py-4 space-y-3 max-h-80 overflow-y-auto">
            {msgs.length === 0 && (
              <p className="text-center text-sm text-muted-foreground py-6">
                Try: “Hello” · “I need help creating an account” · “What documents do I need?”
              </p>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`flex ${m.from === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                  m.from === "user"
                    ? "bg-primary/20 text-foreground"
                    : "bg-white/5 border border-border/50 backdrop-blur-xl"
                }`}>
                  {m.text}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </CardContent>
        </Card>

        <div className="flex justify-center gap-2 flex-wrap">
          <Button className="gap-1" size="sm" onClick={enterFullDemo} disabled={demoLoading}>
            <Play className="h-3.5 w-3.5" />
            {demoLoading ? "Preparing…" : "Enter full demo — jobs, signatures, offline"}
          </Button>
          <Button variant="outline" size="sm" className="gap-1" onClick={endChat}>
            <PhoneOff className="h-3.5 w-3.5" /> End chat
          </Button>
          <Button variant="outline" size="sm" className="gap-1" onClick={() => setMsgs([])}>
            <Trash2 className="h-3.5 w-3.5" /> Clear
          </Button>
          <Link href="/login"><Button variant="ghost" size="sm">Log in for full version</Button></Link>
        </div>

        <p className="text-center text-xs text-muted-foreground">
          <Volume2 className="inline h-3 w-3 mr-1" />
          Demo is rate-limited · full version has job tools, signatures & offline mode
        </p>
      </div>
    </div>
  );
}
