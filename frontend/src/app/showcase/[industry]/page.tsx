"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Mic,
  MicOff,
  Send,
  Volume2,
  CheckCircle2,
  Clock,
  ShieldAlert,
  Banknote,
  Loader2,
  ArrowLeft,
  WifiOff,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const SLUG_TO_ID: Record<string, string> = {
  plumbing: "voice-plumbing-uk",
  hvac: "voice-hvac-uk",
  electrician: "voice-electrician-uk",
  "real-estate": "voice-real-estate-uk",
  dental: "voice-dental-uk",
  cleaning: "voice-cleaning-uk",
  roofing: "voice-roofing-us",
  "law-firm": "voice-lawfirm-uk",
  "auto-repair": "voice-autorepair-us",
  hotel: "voice-hotel-ae",
  "crm-voice": "voice-crm-uk",
  saas: "chat-saas",
  ecommerce: "chat-ecommerce",
  recruitment: "chat-recruitment-uk",
  construction: "chat-construction-uk",
  insurance: "chat-insurance-uk",
  gym: "chat-gym-uk",
  travel: "chat-travel-uk",
  education: "chat-education-uk",
  medical: "chat-medical-uk",
  locksmith: "voice-locksmith-uk",
  driving: "voice-driving-uk",
  maid: "voice-maid-ae",
  pharmacy: "voice-pharmacy-uk",
  "property-mgmt": "voice-property-mgmt-uk",
  chimney: "voice-chimney-uk",
  wedding: "voice-wedding-uk",
  security: "voice-security-uk",
  pool: "voice-pool-us",
  "student-housing": "chat-student-housing-uk",
  airline: "chat-airline",
  subscription: "chat-subscription",
  furniture: "chat-furniture-uk",
  coworking: "chat-coworking-uk",
  clinic: "voice-clinic-in",
  property: "voice-property-in",
  salon: "voice-salon-in",
  "restaurant-uk": "chat-restaurant-uk",
  "restaurant-in": "voice-restaurant-in",
  coaching: "voice-coaching-in",
  "appliance-us": "voice-appliance-us",
  "appliance-in": "voice-appliance-in",
};

const ID_TO_SLUG: Record<string, string> = Object.fromEntries(
  Object.entries(SLUG_TO_ID).map(([slug, id]) => [id, slug])
);

type Pack = {
  id: string;
  kind: string;
  industry: string;
  locale: string;
  name: string;
  greeting: string;
  voice: string;
  system_prompt?: string;
  faqs?: any[];
  services?: any[];
  booking_fields?: any[];
  hours?: any;
  escalation?: string;
  brand_color?: string;
  demo_script?: string[];
};

type ChatMsg = { from: "user" | "agent"; text: string };

const FALLBACK_PACKS: Record<string, Pack> = {
  plumbing: {
    id: "voice-plumbing-uk",
    kind: "voice",
    industry: "plumbing",
    locale: "en-GB",
    name: "AquaFlow Plumbing — AI Receptionist",
    greeting: "Thanks for calling AquaFlow Plumbing, how can I help today?",
    voice: "en-GB-female",
    brand_color: "#0ea5e9",
    system_prompt: "Friendly UK plumbing receptionist. Triage leaks, blockages and installs.",
    faqs: [
      { q: "How fast can you come out?", a: "Emergency callouts within 2 hours across Greater London; standard slots same-day or next-day." },
      { q: "What does a callout cost?", a: "Fixed £89 callout including the first 30 minutes of labour, parts extra." },
      { q: "Do you guarantee work?", a: "Yes — 12-month workmanship guarantee on all repairs and installs." },
    ],
    services: [
      { name: "Emergency leak repair", price: "from £89" },
      { name: "Blocked drain clearance", price: "from £120" },
      { name: "Boiler service add-on", price: "from £75" },
    ],
    booking_fields: ["name", "phone", "postcode", "preferred_time"],
    hours: "Mon–Sat 8:00–18:00 · 24/7 emergency line",
    escalation: "Burst pipes or gas smells are escalated to the on-call engineer immediately.",
    demo_script: ["Hi, I've got a leak under my kitchen sink", "How much is a callout?", "Can I book tomorrow morning?"],
  },
  hvac: {
    id: "voice-hvac-uk",
    kind: "voice",
    industry: "hvac",
    locale: "en-GB",
    name: "CosyHeat HVAC — AI Receptionist",
    greeting: "Thanks for calling CosyHeat, is it a boiler or heating issue I can help with?",
    voice: "en-GB-male",
    brand_color: "#f97316",
    system_prompt: "Friendly UK heating receptionist. Triage boiler breakdowns and book Gas Safe engineers.",
    faqs: [
      { q: "My boiler has no hot water — what now?", a: "We run a 60-second triage (pressure, pilot, thermostat) then book a Gas Safe engineer." },
      { q: "Do you offer annual servicing?", a: "Yes — £95 annual service with reminders and priority breakdown cover." },
      { q: "Are your engineers certified?", a: "All engineers are Gas Safe registered; certificates emailed after every visit." },
    ],
    services: [
      { name: "Boiler breakdown visit", price: "from £99" },
      { name: "Annual boiler service", price: "from £95" },
      { name: "Radiator repair / bleed", price: "from £65" },
    ],
    booking_fields: ["name", "phone", "postcode", "boiler_model"],
    hours: "Mon–Fri 8:00–18:00, Sat 9:00–14:00 · winter emergency cover",
    escalation: "Suspected gas leaks or carbon-monoxide alarms go straight to the emergency line and National Gas.",
    demo_script: ["My boiler keeps losing pressure", "How much is a service?", "Book me in for Friday please"],
  },
  electrician: {
    id: "voice-electrician-uk",
    kind: "voice",
    industry: "electrician",
    locale: "en-GB",
    name: "SparkSafe Electrics — AI Receptionist",
    greeting: "Thanks for calling SparkSafe Electrics, what electrical job can I book in for you?",
    voice: "en-GB-female",
    brand_color: "#eab308",
    system_prompt: "Friendly UK electrician receptionist. Intake for faults, EICRs and rewires.",
    faqs: [
      { q: "Do you do emergency callouts?", a: "Yes — faulty fuse boxes, sparking sockets and power loss get same-day priority." },
      { q: "How much is an EICR?", a: "EICRs from £149 for flats, £189 for houses, certificate included." },
      { q: "Are you certified?", a: "NICEIC-approved electricians; Part P certificates issued for notifiable work." },
    ],
    services: [
      { name: "Emergency fault visit", price: "from £95" },
      { name: "EICR certificate", price: "from £149" },
      { name: "Socket / lighting install", price: "from £60" },
    ],
    booking_fields: ["name", "phone", "postcode", "job_type"],
    hours: "Mon–Sat 8:00–18:00 · 24/7 emergency faults line",
    escalation: "Burning smells, sparking or shocks are escalated to the duty electrician at once — isolate power first.",
    demo_script: ["My sockets keep tripping", "How much for an EICR?", "I need someone next Tuesday"],
  },
};

function faqText(f: any, i: number): { q: string; a: string } {
  if (typeof f === "string") return { q: f, a: "" };
  return {
    q: f?.q || f?.question || `Question ${i + 1}`,
    a: f?.a || f?.answer || "",
  };
}

function serviceRow(s: any, i: number): { name: string; price: string; detail: string } {
  if (typeof s === "string") return { name: s, price: "", detail: "" };
  return {
    name: s?.name || s?.title || `Service ${i + 1}`,
    price: s?.price || s?.price_gbp || s?.from || "",
    detail: s?.description || s?.detail || "",
  };
}

export default function ShowcaseDetailPage() {
  const params = useParams();
  const rawIndustry = Array.isArray((params as any)?.industry)
    ? (params as any).industry[0]
    : ((params as any)?.industry as string);
  const industry = (rawIndustry || "").toLowerCase();
  const templateId = SLUG_TO_ID[industry] || "";

  const [pack, setPack] = useState<Pack | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState("");
  const [comingSoon, setComingSoon] = useState(false);
  const [tab, setTab] = useState<"voice" | "text">("voice");
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  const [sessionId, setSessionId] = useState("");
  const [textMsgs, setTextMsgs] = useState<ChatMsg[]>([]);
  const [quickReplies, setQuickReplies] = useState<string[]>([]);
  const [stage, setStage] = useState("");
  const [leadRef, setLeadRef] = useState("");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState("");

  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("Tap the mic and speak — UK English.");
  const [voiceMsgs, setVoiceMsgs] = useState<ChatMsg[]>([]);
  const [voiceError, setVoiceError] = useState("");
  const recRef = useRef<any>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSessionId(`web-${Date.now()}-${Math.floor(Math.random() * 1000000)}`);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [textMsgs, voiceMsgs]);

  useEffect(() => {
    return () => {
      try {
        recRef.current?.stop();
      } catch {}
      try {
        audioRef.current?.pause();
      } catch {}
    };
  }, []);

  useEffect(() => {
    if (!industry) return;
    if (!templateId) {
      setComingSoon(true);
      setLoading(false);
      return;
    }
    setComingSoon(false);
    setLoading(true);
    setError("");
    fetch(`${API}/api/agents/templates/${templateId}`)
      .then((r: any) => {
        if (r.status === 404) throw new Error("NOT_FOUND");
        if (!r.ok) throw new Error(`detail ${r.status}`);
        return r.json();
      })
      .then((d: any) => {
        const p = d?.pack || d?.template || d;
        setPack({ ...(FALLBACK_PACKS[industry] || {}), ...p, id: templateId } as Pack);
        setOffline(false);
        setLoading(false);
      })
      .catch((e: any) => {
        if (e?.message === "NOT_FOUND") {
          setComingSoon(true);
          setLoading(false);
          return;
        }
        setPack((FALLBACK_PACKS[industry] as Pack) || null);
        setOffline(true);
        setError(e?.message || "API unreachable");
        setLoading(false);
      });
  }, [industry, templateId]);

  const stopAudio = () => {
    try {
      audioRef.current?.pause();
    } catch {}
    audioRef.current = null;
    setSpeaking(false);
  };

  const speakText = (text: string, tid: string) => {
    setSpeaking(true);
    setVoiceStatus("Speaking…");
    fetch(`${API}/api/agents/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template_id: tid, text: text.slice(0, 300) }),
    })
      .then((r: any) => {
        if (!r.ok) throw new Error(`speak ${r.status}`);
        return r.json();
      })
      .then((d: any) => {
        if (!d?.audio_base64) throw new Error("no audio");
        const audio = new Audio(`data:audio/mpeg;base64,${d.audio_base64}`);
        audioRef.current = audio;
        audio.onended = () => {
          setSpeaking(false);
          setVoiceStatus("Tap the mic and speak — UK English.");
        };
        audio.onerror = () => {
          setSpeaking(false);
          setVoiceStatus("Tap the mic and speak — UK English.");
        };
        const played: any = audio.play();
        if (played && typeof played.catch === "function") {
          played.catch(() => {
            setSpeaking(false);
            setVoiceStatus("Tap the mic and speak — UK English.");
          });
        }
      })
      .catch((e: any) => {
        setVoiceError(e?.message || "Voice playback failed");
        setSpeaking(false);
        setVoiceStatus("Tap the mic and speak — UK English.");
      });
  };

  const sendChat = (message: string, source: "voice" | "text") => {
    const text = message.trim();
    const tid = pack?.id || templateId;
    if (!text || !tid) return;
    if (source === "text") {
      setSending(true);
      setChatError("");
      setTextMsgs((m) => [...m, { from: "user", text }]);
      setInput("");
    } else {
      setVoiceMsgs((m) => [...m, { from: "user", text }]);
      setVoiceStatus("Thinking…");
    }
    fetch(`${API}/api/agents/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template_id: tid, message: text, session_id: sessionId }),
    })
      .then((r: any) => {
        if (!r.ok) throw new Error(`chat ${r.status}`);
        return r.json();
      })
      .then((d: any) => {
        const reply = d?.reply || "Sorry, I didn't catch that — could you say it again?";
        const qr = Array.isArray(d?.quick_replies) ? d.quick_replies.slice(0, 3) : [];
        if (source === "text") {
          setTextMsgs((m) => [...m, { from: "agent", text: reply }]);
          setQuickReplies(qr);
          setStage(d?.stage || "");
          setLeadRef(d?.lead_reference || "");
          setSending(false);
        } else {
          setVoiceMsgs((m) => [...m, { from: "agent", text: reply }]);
          setStage(d?.stage || "");
          setLeadRef(d?.lead_reference || "");
          speakText(reply, tid);
        }
      })
      .catch((e: any) => {
        if (source === "text") {
          setChatError(e?.message || "Chat failed — is the API running?");
          setSending(false);
        } else {
          setVoiceError(e?.message || "Chat failed — is the API running?");
          setVoiceStatus("Tap the mic and speak — UK English.");
        }
      });
  };

  const startListening = () => {
    setVoiceError("");
    stopAudio();
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      setVoiceError("This browser can't do speech recognition — use Chrome or Edge.");
      return;
    }
    const rec = new SR();
    rec.lang = "en-GB";
    rec.interimResults = false;
    rec.continuous = false;
    rec.onstart = () => {
      setListening(true);
      setVoiceStatus("Listening… speak now.");
    };
    rec.onresult = (event: any) => {
      const text = event.results[event.results.length - 1][0].transcript as string;
      setListening(false);
      sendChat(text, "voice");
    };
    rec.onerror = () => {
      setListening(false);
      setVoiceStatus("Tap the mic and speak — UK English.");
    };
    rec.onend = () => {
      setListening(false);
    };
    recRef.current = rec;
    try {
      rec.start();
    } catch {
      setListening(false);
    }
  };

  const stopListening = () => {
    try {
      recRef.current?.stop();
    } catch {}
    setListening(false);
    setVoiceStatus("Tap the mic and speak — UK English.");
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-2 bg-zinc-950 text-sm text-zinc-400">
        <Loader2 className="h-5 w-5 animate-spin" /> Loading agent…
      </div>
    );
  }

  if (comingSoon || !templateId) {
    const others = Object.keys(SLUG_TO_ID).filter((s) => s !== industry);
    return (
      <div className="min-h-screen bg-zinc-950 px-4 py-16 text-zinc-100">
        <div className="mx-auto max-w-md rounded-2xl border border-white/10 bg-white/5 px-6 py-10 text-center">
          <p className="text-lg font-semibold">This agent is coming soon</p>
          <p className="mt-2 text-sm text-zinc-400">
            “{rawIndustry || "unknown"}” isn&apos;t live yet. Try one of our live trades instead:
          </p>
          <div className="mt-6 space-y-2">
            {others.map((s) => (
              <Link
                key={s}
                href={`/showcase/${s}`}
                className="block rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm capitalize text-purple-200 hover:bg-white/10"
              >
                {s} demo →
              </Link>
            ))}
          </div>
          <Link href="/showcase" className="mt-6 inline-block text-sm text-zinc-400 hover:text-zinc-200">
            ← Back to showcase
          </Link>
        </div>
      </div>
    );
  }

  if (!pack) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-zinc-950 px-4 text-center text-zinc-300">
        <p className="font-semibold">Agent not found</p>
        <p className="text-sm text-zinc-400">The API returned nothing for this template and no fallback exists.</p>
        <Link href="/showcase" className="text-sm text-purple-300 hover:text-purple-200">
          ← Back to showcase
        </Link>
      </div>
    );
  }

  const accent = pack.brand_color || "#a855f7";
  const faqs = Array.isArray(pack.faqs) ? pack.faqs : [];
  const services = Array.isArray(pack.services) ? pack.services : [];
  const hoursText =
    typeof pack.hours === "string" ? pack.hours : pack.hours ? JSON.stringify(pack.hours) : "Mon–Sat · daytime + emergency cover";

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* Hero */}
      <section className="border-b border-white/10" style={{ background: `linear-gradient(180deg, ${accent}26, transparent)` }}>
        <div className="mx-auto max-w-6xl px-4 py-10">
          <Link href="/showcase" className="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200">
            <ArrowLeft className="h-4 w-4" /> All agents
          </Link>
          <div className="mt-4 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div>
              <span className="inline-block rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-zinc-300">
                {pack.locale || "en-GB"} · {pack.kind || "voice"} agent
              </span>
              <h1 className="mt-3 text-2xl font-bold sm:text-4xl">{pack.name}</h1>
              <p className="mt-1 text-sm capitalize text-zinc-400">{pack.industry} · {pack.id}</p>
            </div>
          </div>
          <figure className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-5 backdrop-blur-xl">
            <blockquote className="text-sm italic text-zinc-200 sm:text-base">“{pack.greeting}”</blockquote>
            <figcaption className="mt-2 flex items-center gap-1.5 text-xs text-zinc-400">
              <Volume2 className="h-3.5 w-3.5" /> Voice: {pack.voice || "en-GB"} — live demo below
            </figcaption>
          </figure>
          {offline && (
            <div className="mt-4 flex items-start gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              <WifiOff className="mt-0.5 h-4 w-4 shrink-0" />
              <p>Live demo unavailable offline — showing built-in preview content. {error ? `(${error})` : ""}</p>
            </div>
          )}
        </div>
      </section>

      <main className="mx-auto max-w-6xl space-y-10 px-4 py-10">
        {/* Live demo tabs */}
        <section className="rounded-2xl border border-white/10 bg-white/5 p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Live demo</h2>
            <div className="flex rounded-full border border-white/10 bg-zinc-950 p-1 text-sm">
              {(["voice", "text"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`rounded-full px-4 py-1.5 font-medium capitalize transition-colors ${
                    tab === t ? "bg-purple-600 text-white" : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {tab === "voice" ? (
            <div className="mt-6">
              <div className="flex flex-col items-center gap-3">
                <button
                  onClick={listening ? stopListening : startListening}
                  aria-label={listening ? "Stop listening" : "Start talking"}
                  className={`relative flex h-20 w-20 items-center justify-center rounded-full transition-all ${
                    listening
                      ? "bg-red-500 shadow-[0_0_50px_rgba(239,68,68,0.5)]"
                      : "bg-gradient-to-br from-purple-600 to-purple-900 shadow-[0_0_50px_rgba(147,51,234,0.4)]"
                  }`}
                >
                  {listening && <span className="absolute inset-0 animate-ping rounded-full bg-red-500/40" />}
                  {listening ? <MicOff className="h-8 w-8 text-white" /> : <Mic className="h-8 w-8 text-white" />}
                </button>
                <p className="text-sm text-zinc-400">
                  {speaking ? "Speaking…" : voiceStatus}
                </p>
                {speaking && (
                  <button onClick={stopAudio} className="text-xs text-zinc-400 underline hover:text-zinc-200">
                    Stop playback
                  </button>
                )}
              </div>
              {voiceError && <p className="mx-auto mt-4 max-w-md rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-2 text-center text-sm text-red-300">{voiceError}</p>}
              <div className="mt-5 space-y-2">
                {voiceMsgs.length === 0 && (
                  <p className="rounded-xl border border-white/10 bg-zinc-950 px-4 py-4 text-center text-sm text-zinc-500">
                    No voice transcript yet — tap the mic and try a demo line below.
                  </p>
                )}
                {voiceMsgs.map((m, i) => (
                  <div key={i} className={`flex ${m.from === "user" ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                        m.from === "user" ? "bg-purple-600/30" : "border border-white/10 bg-zinc-950"
                      }`}
                    >
                      {m.text}
                    </div>
                  </div>
                ))}
              </div>
              {(pack.demo_script || []).length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {(pack.demo_script || []).map((line) => (
                    <button
                      key={line}
                      onClick={() => sendChat(line, "voice")}
                      className="rounded-full border border-white/10 bg-zinc-950 px-3 py-1.5 text-xs text-zinc-300 hover:bg-white/10"
                    >
                      Try: “{line}”
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="mt-6">
              <div className="max-h-80 space-y-2 overflow-y-auto rounded-xl border border-white/10 bg-zinc-950 p-4">
                {textMsgs.length === 0 && (
                  <p className="py-6 text-center text-sm text-zinc-500">
                    Say hello to {pack.name} — ask about prices, availability or bookings.
                  </p>
                )}
                {textMsgs.map((m, i) => (
                  <div key={i} className={`flex ${m.from === "user" ? "justify-end" : "justify-start"}`}>
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                        m.from === "user" ? "bg-purple-600/30" : "border border-white/10 bg-white/5"
                      }`}
                    >
                      {m.text}
                    </div>
                  </div>
                ))}
                {sending && <p className="text-xs text-zinc-500">Agent is typing…</p>}
                <div ref={bottomRef} />
              </div>
              {quickReplies.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {quickReplies.map((q) => (
                    <button
                      key={q}
                      onClick={() => sendChat(q, "text")}
                      className="rounded-full border border-purple-500/40 bg-purple-500/10 px-3 py-1.5 text-xs text-purple-200 hover:bg-purple-500/20"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}
              {(stage || leadRef) && (
                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                  {stage && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-zinc-300">
                      <CheckCircle2 className="h-3.5 w-3.5 text-green-400" /> Stage: {stage}
                    </span>
                  )}
                  {leadRef && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-green-500/40 bg-green-500/10 px-2.5 py-1 text-green-200">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Booking ref: {leadRef}
                    </span>
                  )}
                </div>
              )}
              {chatError && <p className="mt-3 rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-300">{chatError}</p>}
              <form
                className="mt-3 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  sendChat(input, "text");
                }}
              >
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Type your message…"
                  className="min-w-0 flex-1 rounded-xl border border-white/10 bg-zinc-950 px-4 py-2.5 text-sm outline-none placeholder:text-zinc-500 focus:border-purple-500"
                />
                <button
                  type="submit"
                  disabled={sending || !input.trim()}
                  className="flex items-center gap-1.5 rounded-xl bg-purple-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
                >
                  <Send className="h-4 w-4" /> Send
                </button>
              </form>
            </div>
          )}
        </section>

        {/* FAQs */}
        <section>
          <h2 className="text-lg font-semibold">FAQs this agent answers</h2>
          {faqs.length === 0 ? (
            <p className="mt-3 rounded-xl border border-white/10 bg-white/5 px-4 py-4 text-sm text-zinc-500">
              No FAQs published for this pack yet.
            </p>
          ) : (
            <div className="mt-3 space-y-2">
              {faqs.map((f, i) => {
                const { q, a } = faqText(f, i);
                const open = openFaq === i;
                return (
                  <div key={i} className="overflow-hidden rounded-xl border border-white/10 bg-white/5">
                    <button
                      onClick={() => setOpenFaq(open ? null : i)}
                      className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm font-medium"
                    >
                      {q}
                      <span className="shrink-0 text-zinc-500">{open ? "−" : "+"}</span>
                    </button>
                    {open && <p className="border-t border-white/10 px-4 py-3 text-sm text-zinc-400">{a || "Ask the live demo above."}</p>}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Services / pricing */}
        <section>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Banknote className="h-5 w-5 text-green-400" /> Services & pricing
          </h2>
          {services.length === 0 ? (
            <p className="mt-3 rounded-xl border border-white/10 bg-white/5 px-4 py-4 text-sm text-zinc-500">
              Pricing is confirmed on the call — try the demo for a fixed quote.
            </p>
          ) : (
            <div className="mt-3 overflow-hidden rounded-xl border border-white/10">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="bg-white/5 text-xs uppercase tracking-wide text-zinc-400">
                    <th className="px-4 py-3">Service</th>
                    <th className="px-4 py-3 text-right">Price (£)</th>
                  </tr>
                </thead>
                <tbody>
                  {services.map((s, i) => {
                    const row = serviceRow(s, i);
                    return (
                      <tr key={i} className="border-t border-white/10 bg-zinc-950/60">
                        <td className="px-4 py-3">
                          <p className="font-medium">{row.name}</p>
                          {row.detail && <p className="mt-0.5 text-xs text-zinc-500">{row.detail}</p>}
                        </td>
                        <td className="px-4 py-3 text-right text-zinc-200">{row.price || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Hours / escalation */}
        <section className="grid gap-3 sm:grid-cols-2">
          <div className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/5 p-5">
            <Clock className="mt-0.5 h-5 w-5 shrink-0 text-sky-400" />
            <div>
              <p className="text-sm font-semibold">Hours</p>
              <p className="mt-1 text-sm text-zinc-400">{hoursText}</p>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-2xl border border-white/10 bg-white/5 p-5">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
            <div>
              <p className="text-sm font-semibold">Escalation</p>
              <p className="mt-1 text-sm text-zinc-400">{pack.escalation || "Urgent or unsafe jobs are handed to a human engineer straight away."}</p>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section
          className="rounded-2xl border px-6 py-10 text-center"
          style={{ borderColor: `${accent}55`, background: `linear-gradient(120deg, ${accent}22, transparent)` }}
        >
          <h2 className="text-xl font-bold sm:text-2xl">Want one answering your phones?</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-zinc-400">
            Start a free trial and we&apos;ll configure {pack.name} with your greeting, prices and calendar.
          </p>
          <Link
            href="/register"
            className="mt-6 inline-block rounded-full bg-purple-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-purple-500"
          >
            Start free trial
          </Link>
        </section>
      </main>
    </div>
  );
}
