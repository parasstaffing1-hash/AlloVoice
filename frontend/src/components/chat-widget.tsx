"use client";

import { useEffect, useRef, useState } from "react";
import { MessageCircle, X, Send } from "lucide-react";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const FALLBACK_QUICK_REPLIES = [
  "Get a quote",
  "Book a visit",
  "Our services",
  "Pricing",
];

const WELCOME_TEXT =
  "Hi there! Thanks for visiting VoiceField. I can help with services, pricing, availability or booking a visit. What do you need help with today?";

function makeSessionId(): string {
  return (
    Math.random().toString(36).substring(2, 10) + Date.now().toString(36)
  );
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", text: WELCOME_TEXT },
  ]);
  const [quickReplies, setQuickReplies] = useState<string[]>(
    FALLBACK_QUICK_REPLIES
  );
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [unread, setUnread] = useState(false);

  const sessionIdRef = useRef<string>("");
  if (!sessionIdRef.current) {
    sessionIdRef.current = makeSessionId();
  }

  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, typing, open]);

  const pushAssistant = (text: string) => {
    setMessages((prev) => [...prev, { role: "assistant", text }]);
    if (!open) {
      setUnread(true);
    }
  };

  const sendMessage = async (rawText: string) => {
    const text = rawText.trim();
    if (!text || typing) return;

    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setQuickReplies([]);
    setTyping(true);

    try {
      const res = await fetch(`${API_BASE}/api/chatbot/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: sessionIdRef.current,
          page_url:
            typeof window !== "undefined" ? window.location.href : null,
        }),
      });

      if (!res.ok) throw new Error(`Chat failed: ${res.status}`);

      const data = await res.json();
      pushAssistant(
        data.reply ?? "Sorry, something went wrong. Please try again."
      );
      if (Array.isArray(data.quick_replies) && data.quick_replies.length > 0) {
        setQuickReplies(data.quick_replies);
      }
    } catch {
      pushAssistant(
        "Sorry, I'm having trouble connecting right now. Please call us on 0161 496 0000 and we'll help straight away."
      );
      setQuickReplies(["Try again", "Our services"]);
    } finally {
      setTyping(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void sendMessage(input);
  };

  const toggleOpen = () => {
    const next = !open;
    setOpen(next);
    if (next) setUnread(false);
  };

  return (
    <>
      {/* Floating bubble button */}
      <button
        onClick={toggleOpen}
        aria-label={open ? "Close chat" : "Open chat"}
        className="fixed bottom-4 right-4 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-orange-500 text-white shadow-lg transition-colors hover:bg-orange-600 focus:outline-none focus:ring-2 focus:ring-orange-400 focus:ring-offset-2"
      >
        {open ? <X className="h-6 w-6" /> : <MessageCircle className="h-6 w-6" />}
        {!open && unread && (
          <span className="absolute -right-1 -top-1 h-4 w-4 rounded-full border-2 border-white bg-red-500" />
        )}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-20 right-4 z-50 flex h-[520px] max-h-[70vh] w-[calc(100vw-2rem)] max-w-[380px] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl">
          {/* Header */}
          <div className="flex items-center gap-3 bg-orange-500 px-4 py-3 text-white">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/20">
              <MessageCircle className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">VoiceField Assistant</p>
              <p className="flex items-center gap-1.5 text-xs text-orange-100">
                <span className="inline-block h-2 w-2 rounded-full bg-green-300" />
                Online — replies instantly
              </p>
            </div>
            <button
              onClick={toggleOpen}
              aria-label="Close chat"
              className="rounded-full p-1 transition-colors hover:bg-white/20"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 space-y-3 overflow-y-auto bg-gray-50 px-3 py-4">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${
                  msg.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed shadow-sm ${
                    msg.role === "user"
                      ? "rounded-br-md bg-orange-500 text-white"
                      : "rounded-bl-md border border-gray-100 bg-white text-gray-800"
                  }`}
                >
                  {msg.text}
                </div>
              </div>
            ))}

            {typing && (
              <div className="flex justify-start">
                <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-md border border-gray-100 bg-white px-4 py-3 shadow-sm">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-orange-400 [animation-delay:-0.3s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-orange-400 [animation-delay:-0.15s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-orange-400" />
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Quick replies */}
          {quickReplies.length > 0 && !typing && (
            <div className="flex flex-wrap gap-2 border-t border-gray-100 bg-white px-3 pt-2.5">
              {quickReplies.map((reply) => (
                <button
                  key={reply}
                  onClick={() => void sendMessage(reply)}
                  className="rounded-full border border-orange-200 bg-orange-50 px-3 py-1.5 text-xs font-medium text-orange-700 transition-colors hover:bg-orange-100"
                >
                  {reply}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <form
            onSubmit={handleSubmit}
            className="flex items-center gap-2 bg-white p-3"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your message…"
              maxLength={2000}
              className="min-w-0 flex-1 rounded-full border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-orange-400 focus:outline-none focus:ring-1 focus:ring-orange-400"
            />
            <button
              type="submit"
              disabled={!input.trim() || typing}
              aria-label="Send message"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-orange-500 text-white transition-colors hover:bg-orange-600 disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
