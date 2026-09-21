"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Send, Loader2, MessageCircle } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

type Msg = { from: "user" | "agent"; text: string };

function ChatEmbedInner() {
  const params = useSearchParams();
  const business = params.get("business") || params.get("subdomain") || "";
  const [brand, setBrand] = useState({ name: "Allo", color: "#f97316" });
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [chips, setChips] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API}/api/branding/portal-theme${business ? `?subdomain=${encodeURIComponent(business)}` : ""}`)
      .then((r: any) => r.json())
      .then((r: any) => {
        if (r?.brand_name) setBrand({ name: r.brand_name, color: r.primary_color || "#f97316" });
      })
      .catch(() => {});
  }, [business]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, typing]);

  const send = async (text: string) => {
    const clean = text.trim();
    if (!clean || typing) return;
    setError("");
    setInput("");
    setChips([]);
    setMsgs((m) => [...m, { from: "user", text: clean }]);
    setTyping(true);
    try {
      const res = await fetch(`${API}/api/chatbot/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: clean,
          session_id: sessionId || undefined,
          page_url: typeof document !== "undefined" ? document.referrer : undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Chat failed");
      if (data.session_id) setSessionId(data.session_id);
      setMsgs((m) => [...m, { from: "agent", text: data.reply || "Sorry — try again?" }]);
      setChips(Array.isArray(data.quick_replies) ? data.quick_replies.slice(0, 3) : []);
    } catch (e: any) {
      setError(e?.message || "Chat failed — try again.");
    } finally {
      setTyping(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-[#0a0a0b] text-zinc-100">
      <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-full text-white text-sm font-bold"
          style={{ backgroundColor: brand.color }}>
          {brand.name.charAt(0).toUpperCase()}
        </span>
        <div>
          <p className="text-sm font-semibold">{brand.name}</p>
          <p className="text-[11px] text-zinc-400 flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-green-400" /> Typically replies instantly
          </p>
        </div>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4" style={{ maxHeight: "calc(100vh - 190px)" }}>
        {msgs.length === 0 && (
          <div className="text-center py-8">
            <MessageCircle className="h-8 w-8 mx-auto mb-2" style={{ color: brand.color }} />
            <p className="text-sm text-zinc-400">Hi! Ask about services, pricing or booking.</p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.from === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-sm ${
              m.from === "user" ? "text-white" : "bg-white/10"
            }`} style={m.from === "user" ? { backgroundColor: brand.color } : undefined}>
              {m.text}
            </div>
          </div>
        ))}
        {typing && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-white/10 px-4 py-2.5 flex gap-1">
              {[0, 1, 2].map((d) => (
                <span key={d} className="h-1.5 w-1.5 rounded-full bg-zinc-400 animate-bounce" style={{ animationDelay: `${d * 0.15}s` }} />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {chips.length > 0 && (
        <div className="flex gap-2 px-4 pb-2 overflow-x-auto">
          {chips.map((c) => (
            <button key={c} onClick={() => send(c)}
              className="shrink-0 rounded-full border px-3 py-1.5 text-xs hover:bg-white/10"
              style={{ borderColor: brand.color }}>
              {c}
            </button>
          ))}
        </div>
      )}

      {error && <p className="px-4 pb-1 text-xs text-red-400">{error}</p>}

      <form className="flex gap-2 border-t border-white/10 p-3"
        onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your message…"
          className="bg-white/5"
        />
        <Button type="submit" size="icon" disabled={typing || !input.trim()}
          style={{ backgroundColor: brand.color }}>
          {typing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </form>
      <p className="pb-2 text-center text-[10px] text-zinc-600">Powered by Allo</p>
    </div>
  );
}

export default function EmbedChatPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#0a0a0b] text-zinc-400 text-center pt-20 text-sm">Loading…</div>}>
      <ChatEmbedInner />
    </Suspense>
  );
}
