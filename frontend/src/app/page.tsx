"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Mic, PhoneOff, Calendar, Users, MessageSquare, Zap, Mail, Webhook, Code,
  ArrowRight, Check, Play, Menu, X, ChevronDown, Activity, Clock,
  PhoneCall, ShieldCheck, Lock, FileText, Headset, BarChart3,
} from "lucide-react";

/* ---------------------------------- data ---------------------------------- */

const NAV = ["Product", "Solutions", "Integrations", "Pricing", "Resources"];

const LOGOS = ["Northgate", "Helios Energy", "Brightline", "Corelink", "Medford & Co", "Skylark Homes", "ProServe", "Alto Dental"];

const USE_CASES = [
  {
    id: "receptionist", icon: Headset, title: "Receptionist",
    desc: "Answers every call in seconds, routes with context, never sleeps.",
    preview: [
      { from: "Customer", text: "Hi, do you have anything tomorrow morning?" },
      { from: "AI", text: "Yes — I can offer 9:40 or 11:15. Which suits you?" },
    ],
    done: ["Caller identified", "Intent classified"],
  },
  {
    id: "sales", icon: BarChart3, title: "Sales Agent",
    desc: "Qualifies inbound interest and books the meeting before they cool off.",
    preview: [
      { from: "Customer", text: "What does the Growth plan include?" },
      { from: "AI", text: "2,500 minutes, 5 agents and all integrations. Want a walkthrough Thursday?" },
    ],
    done: ["Lead scored: hot", "Meeting proposed"],
  },
  {
    id: "leadqual", icon: Activity, title: "Lead Qualification",
    desc: "Budget, authority, need, timeline — captured naturally in conversation.",
    preview: [
      { from: "Customer", text: "We're a 12-van plumbing firm." },
      { from: "AI", text: "Perfect fit. How many calls a week go unanswered?" },
    ],
    done: ["Firm size captured", "Pain point logged"],
  },
  {
    id: "support", icon: MessageSquare, title: "Customer Support",
    desc: "Resolves the routine 70% instantly, escalates the rest with full context.",
    preview: [
      { from: "Customer", text: "My invoice looks wrong." },
      { from: "AI", text: "I can see invoice #INV-2041 — the VAT line. One moment…" },
    ],
    done: ["Record retrieved", "Fix drafted"],
  },
  {
    id: "booking", icon: Calendar, title: "Appointment Booking",
    desc: "Real calendar holds, confirmations and reminders — no phone tag.",
    preview: [
      { from: "Customer", text: "I need an appointment tomorrow." },
      { from: "AI", text: "I have an opening at 10 AM." },
    ],
    done: ["Appointment booked", "CRM updated", "Confirmation sent"],
  },
  {
    id: "collections", icon: Clock, title: "Collections",
    desc: "Polite, persistent payment follow-ups that humans hate making.",
    preview: [
      { from: "Customer", text: "Sorry — can I pay Friday?" },
      { from: "AI", text: "Of course. I've scheduled a reminder and held the invoice." },
    ],
    done: ["Promise logged", "Reminder scheduled"],
  },
];

const HERO_SCRIPT: Array<{ from: "ai" | "user"; text: string; actions?: string[] }> = [
  { from: "user", text: "Hi, I'd like to move my appointment to tomorrow." },
  { from: "ai", text: "Of course — I found you. I have 10 AM or 2 PM free.", actions: ["Customer record found"] },
  { from: "user", text: "2 PM works." },
  { from: "ai", text: "Done — moved to tomorrow at 2 PM.", actions: ["Calendar updated", "CRM updated", "SMS confirmation sent"] },
];

const CONVO_SCRIPT = [
  { from: "Customer", text: "Can you help me reschedule my appointment?" },
  { from: "Agent", text: "Absolutely. I found an opening tomorrow at 2 PM." },
];

const CONVO_ACTIONS = ["Calendar updated", "Customer record updated", "SMS confirmation sent"];

const FLOW = ["Incoming Call", "Understand Intent", "Access Knowledge", "Use Tools", "Complete Action"];

const INTEGRATIONS = [
  { icon: Calendar, name: "Google Calendar" },
  { icon: Users, name: "HubSpot" },
  { icon: BarChart3, name: "Salesforce" },
  { icon: MessageSquare, name: "Slack" },
  { icon: Zap, name: "Zapier" },
  { icon: Mail, name: "Gmail" },
  { icon: Webhook, name: "Webhooks" },
  { icon: Code, name: "REST API" },
];

const AGENTS = ["Sales Agent", "Receptionist", "Support Agent", "Booking Agent", "Collections Agent"];

const SECURITY = [
  { icon: ShieldCheck, title: "Secure infrastructure", desc: "Encrypted in transit and at rest, EU/US regions." },
  { icon: Users, title: "Role-based access", desc: "Owners, admins and agents see only what they need." },
  { icon: FileText, title: "Audit logs", desc: "Every call, action and change is recorded." },
  { icon: Headset, title: "Human handoff", desc: "Warm transfer with full context, any time." },
  { icon: Code, title: "API access", desc: "Keys, scopes and webhooks for everything." },
  { icon: PhoneCall, title: "Reliable call routing", desc: "Carrier-grade telephony with failover." },
];

const TESTIMONIALS = [
  { quote: "Our missed calls went to zero in the first week. It books like our best receptionist and never takes a day off.", person: "Sarah Whitfield", company: "Whitfield Plumbing & Heating", role: "Owner" },
  { quote: "We stopped losing weekend enquiries entirely. The agent qualifies, books and syncs our CRM before Monday morning.", person: "Marcus Doyle", company: "Doyle Electrical", role: "Director" },
  { quote: "Patients think they're talking to our front desk. No-shows dropped by a third in two months.", person: "Dr. Amara Osei", company: "Alto Dental Studio", role: "Practice Manager" },
];

const PLANS = [
  { name: "Starter", monthly: 49, minutes: "500 min/mo", agents: "1 agent", integrations: "Core integrations", support: "Email support" },
  { name: "Growth", monthly: 149, minutes: "2,500 min/mo", agents: "5 agents", integrations: "All integrations", support: "Priority support", popular: true },
  { name: "Enterprise", monthly: -1, minutes: "Unlimited volume", agents: "Unlimited agents", integrations: "Custom + SLA", support: "Dedicated engineer" },
];

/* --------------------------------- hooks ---------------------------------- */

function useInView<T extends HTMLElement>(threshold = 0.2) {
  const ref = useRef<T | null>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } }),
      { threshold }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);
  return { ref, seen };
}

function Counter({ to, decimals = 0, suffix = "", prefix = "" }: { to: number; decimals?: number; suffix?: string; prefix?: string }) {
  const { ref, seen } = useInView<HTMLSpanElement>(0.4);
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!seen) return;
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / 1400);
      setVal(to * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [seen, to]);
  return (
    <span ref={ref}>
      {prefix}{val.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}{suffix}
    </span>
  );
}

function Reveal({ children, delay = 0, className = "" }: { children: React.ReactNode; delay?: number; className?: string }) {
  const { ref, seen } = useInView<HTMLDivElement>(0.15);
  return (
    <div ref={ref} className={`av-reveal ${seen ? "av-seen" : ""} ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

/* ------------------------------- hero demo -------------------------------- */

const WAVE = [12, 22, 34, 48, 62, 76, 88, 96, 88, 76, 62, 48, 34, 22, 14, 20, 32, 46, 60, 74, 86, 94, 82, 66, 50, 36, 24, 14];

function LiveAgentCard() {
  const [lineIdx, setLineIdx] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const [secs, setSecs] = useState(0);
  const [shownActions, setShownActions] = useState<string[]>([]);

  useEffect(() => {
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timers: ReturnType<typeof setTimeout>[] = [];
    const play = () => {
      if (cancelled) return;
      const line = HERO_SCRIPT[lineIdx % HERO_SCRIPT.length];
      setSpeaking(line.from === "ai");
      setShownActions([]);
      if (line.from === "ai" && line.actions) {
        line.actions.forEach((_, i) => {
          timers.push(setTimeout(() => { if (!cancelled) setShownActions((a) => [...a, line.actions![i]]); }, 900 * (i + 1)));
        });
      }
      timers.push(setTimeout(() => { if (!cancelled) setLineIdx((v) => (v + 1) % (HERO_SCRIPT.length + 2)); }, line.from === "ai" ? 4200 : 2600));
    };
    play();
    return () => { cancelled = true; timers.forEach(clearTimeout); };
  }, [lineIdx]);

  const visible = HERO_SCRIPT.slice(0, Math.min(lineIdx + 1, HERO_SCRIPT.length));
  const mm = String(Math.floor(secs / 60)).padStart(2, "0");
  const ss = String(secs % 60).padStart(2, "0");

  return (
    <div className="av-float relative w-full max-w-md rounded-3xl border border-white/10 bg-white/[0.04] p-6 shadow-[0_0_120px_rgba(47,123,255,0.15)] backdrop-blur-xl">
      <div className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="relative flex h-10 w-10 items-center justify-center rounded-full bg-[#2f7bff]/20">
            <Mic className="h-5 w-5 text-[#6ea8ff]" />
            <span className="absolute -right-0.5 -top-0.5 flex h-3 w-3">
              <span className="absolute h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="h-3 w-3 rounded-full bg-emerald-400" />
            </span>
          </span>
          <div>
            <p className="text-sm font-semibold text-white">Ava · Receptionist</p>
            <p className="flex items-center gap-1.5 text-xs text-zinc-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Online · {speaking ? "Speaking…" : "Listening…"}
            </p>
          </div>
        </div>
        <span className="rounded-md bg-white/5 px-2 py-1 font-mono text-xs text-zinc-300">{mm}:{ss}</span>
      </div>

      <div className="mb-5 flex h-14 items-center justify-center gap-[3px]" aria-hidden>
        {WAVE.map((h, i) => (
          <span key={i} className="av-wave w-[3px] rounded-full bg-[#2f7bff]/80" style={{ height: `${h}%`, animationDelay: `${(i % 12) * 0.09}s`, animationDuration: speaking ? "0.7s" : "1.5s" }} />
        ))}
      </div>

      <div className="min-h-32 space-y-3">
        {visible.slice(-3).map((l, i) => (
          <div key={`${lineIdx}-${i}`} className={`av-msg flex ${l.from === "ai" ? "justify-start" : "justify-end"}`}>
            <div className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-[13px] leading-relaxed ${l.from === "ai" ? "bg-white/[0.07] text-zinc-100" : "bg-[#2f7bff]/20 text-white"}`}>
              {l.text}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 space-y-1.5 border-t border-white/[0.07] pt-3">
        {shownActions.map((a) => (
          <p key={a} className="av-msg flex items-center gap-2 text-xs text-emerald-300">
            <Check className="h-3.5 w-3.5" /> {a}
          </p>
        ))}
        {shownActions.length === 0 && <p className="text-xs text-zinc-500">Waiting for the next action…</p>}
      </div>

      <div className="mt-5 flex items-center justify-between border-t border-white/[0.07] pt-4">
        <span className="flex items-center gap-2 text-xs text-zinc-400">
          <span className={`h-2 w-2 rounded-full ${speaking ? "bg-[#2f7bff]" : "bg-red-400"} animate-pulse`} />
          {speaking ? "Agent speaking" : "Mic live"}
        </span>
        <button className="flex items-center gap-2 rounded-full bg-red-500/15 px-4 py-2 text-xs font-medium text-red-300 transition hover:bg-red-500/25">
          <PhoneOff className="h-3.5 w-3.5" /> End call
        </button>
      </div>
    </div>
  );
}

/* --------------------------------- sections ------------------------------- */

function UseCases() {
  const [sel, setSel] = useState("booking");
  const active = USE_CASES.find((u) => u.id === sel)!;
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
      <div className="grid gap-4 sm:grid-cols-2">
        {USE_CASES.map((u) => (
          <button
            key={u.id}
            onMouseEnter={() => setSel(u.id)}
            onClick={() => setSel(u.id)}
            className={`group rounded-3xl border p-5 text-left transition-all duration-300 hover:-translate-y-1 ${sel === u.id ? "border-[#2f7bff]/50 bg-[#2f7bff]/[0.07]" : "border-white/10 bg-white/[0.03] hover:border-white/20"}`}
          >
            <u.icon className="mb-3 h-5 w-5 text-[#6ea8ff]" />
            <p className="mb-1 font-semibold text-white">{u.title}</p>
            <p className="mb-3 text-[13px] leading-relaxed text-zinc-400">{u.desc}</p>
            <div className="flex h-6 items-end gap-[2px]" aria-hidden>
              {[40, 70, 55, 85, 60, 90, 50].map((h, i) => (
                <span key={i} className="av-wave w-[3px] rounded-full bg-[#2f7bff]/50" style={{ height: `${h}%`, animationDelay: `${i * 0.12}s` }} />
              ))}
            </div>
          </button>
        ))}
      </div>
      <div className="rounded-3xl border border-[#2f7bff]/25 bg-[#2f7bff]/[0.05] p-6 backdrop-blur-xl lg:sticky lg:top-24 lg:self-start">
        <p className="mb-1 text-xs uppercase tracking-[0.2em] text-zinc-500">Live preview</p>
        <p className="mb-4 text-lg font-semibold text-white">{active.title}</p>
        <div className="space-y-3">
          {active.preview.map((l, i) => (
            <div key={i} className={`flex ${l.from === "AI" ? "justify-start" : "justify-end"}`}>
              <div className={`max-w-[90%] rounded-2xl px-3.5 py-2 text-[13px] ${l.from === "AI" ? "bg-white/[0.07] text-zinc-100" : "bg-[#2f7bff]/20 text-white"}`}>
                <span className="mb-0.5 block text-[11px] text-zinc-400">{l.from}</span>{l.text}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 space-y-1.5 border-t border-white/10 pt-3">
          {active.done.map((d) => (
            <p key={d} className="flex items-center gap-2 text-xs text-emerald-300"><Check className="h-3.5 w-3.5" />{d}</p>
          ))}
        </div>
      </div>
    </div>
  );
}

function LiveConversation() {
  const { ref, seen } = useInView<HTMLDivElement>(0.3);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!seen) return;
    setN(0);
    const t1 = setTimeout(() => setN(1), 1200);
    const t2 = setTimeout(() => setN(2), 2600);
    const t3 = setTimeout(() => setN(3), 3800);
    const t4 = setTimeout(() => setN(4), 5000);
    const t5 = setTimeout(() => setN(0), 9000);
    return () => [t1, t2, t3, t4, t5].forEach(clearTimeout);
  }, [seen, n === 0]);
  const showAll = n >= 2;
  return (
    <div ref={ref} className="grid items-stretch gap-4 lg:grid-cols-2">
      <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-xl">
        <div className="mb-4 flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#2f7bff]/20">
            <PhoneCall className="h-5 w-5 text-[#6ea8ff]" />
          </span>
          <div>
            <p className="text-sm font-semibold text-white">Live call · +44 7700 900123</p>
            <p className="text-xs text-emerald-300">● Connected 01:24</p>
          </div>
          <div className="ml-auto flex h-8 items-end gap-[2px]">
            {WAVE.slice(0, 14).map((h, i) => (
              <span key={i} className="av-wave w-[3px] rounded-full bg-[#2f7bff]/70" style={{ height: `${h * 0.5}px`, animationDelay: `${i * 0.1}s` }} />
            ))}
          </div>
        </div>
        <div className="space-y-3">
          {n >= 1 && (
            <div className="av-msg flex justify-end"><div className="max-w-[85%] rounded-2xl bg-[#2f7bff]/20 px-3.5 py-2 text-[13px] text-white">Can you help me reschedule my appointment?</div></div>
          )}
          {n >= 2 && (
            <div className="av-msg flex justify-start"><div className="max-w-[85%] rounded-2xl bg-white/[0.07] px-3.5 py-2 text-[13px] text-zinc-100">Absolutely. I found an opening tomorrow at 2 PM.</div></div>
          )}
        </div>
      </div>
      <div className="relative rounded-3xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-xl">
        <div className="absolute bottom-6 left-0 top-6 hidden w-px bg-gradient-to-b from-transparent via-[#2f7bff]/60 to-transparent lg:block" />
        <p className="mb-4 text-xs uppercase tracking-[0.2em] text-zinc-500">Actions triggered</p>
        <div className="space-y-3">
          {CONVO_ACTIONS.map((a, i) => (
            <div key={a} className={`flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm transition-all duration-500 ${n >= i + 3 ? "border-emerald-400/30 bg-emerald-400/[0.07] text-white opacity-100" : "border-white/[0.07] text-zinc-600 opacity-40"}`}>
              <span className={`flex h-6 w-6 items-center justify-center rounded-full ${n >= i + 3 ? "bg-emerald-400/20 text-emerald-300" : "bg-white/5 text-zinc-600"}`}>
                <Check className="h-3.5 w-3.5" />
              </span>
              {a}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Workflow() {
  const { ref, seen } = useInView<HTMLDivElement>(0.25);
  return (
    <div ref={ref}>
      <div className="relative mb-2 hidden h-px bg-white/10 md:block">
        <div className={`absolute inset-y-0 left-0 bg-gradient-to-r from-[#2f7bff] to-[#6ea8ff] shadow-[0_0_16px_rgba(47,123,255,0.8)] transition-all duration-[2000ms] ${seen ? "w-full" : "w-0"}`} />
      </div>
      <div className="grid gap-4 md:grid-cols-5">
        {FLOW.map((f, i) => (
          <div key={f} className={`rounded-3xl border p-5 text-center transition-all duration-700 ${seen ? "translate-y-0 opacity-100" : "translate-y-6 opacity-0"} ${i === FLOW.length - 1 ? "border-[#2f7bff]/40 bg-[#2f7bff]/[0.07]" : "border-white/10 bg-white/[0.03]"}`} style={{ transitionDelay: `${i * 180}ms` }}>
            <p className="mx-auto mb-3 flex h-8 w-8 items-center justify-center rounded-full bg-[#2f7bff]/15 text-sm font-bold text-[#6ea8ff]">{i + 1}</p>
            <p className="text-sm font-semibold text-white">{f}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function BuilderMock() {
  const panels = ["Agent name", "System instructions", "Voice selector", "Knowledge base", "Tools", "CRM integration", "Calendar integration", "Call transfer"];
  return (
    <div className="overflow-hidden rounded-3xl border border-white/10 bg-[#07090c] shadow-[0_0_100px_rgba(47,123,255,0.08)]">
      <div className="flex items-center gap-2 border-b border-white/[0.07] px-4 py-3">
        <span className="h-2.5 w-2.5 rounded-full bg-white/15" /><span className="h-2.5 w-2.5 rounded-full bg-white/15" /><span className="h-2.5 w-2.5 rounded-full bg-white/15" />
        <span className="ml-3 rounded-md bg-white/5 px-3 py-1 font-mono text-xs text-zinc-400">app.allovoice.ai/builder</span>
      </div>
      <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
        {panels.map((p) => (
          <div key={p} className="group rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-[#2f7bff]/40 hover:bg-[#2f7bff]/[0.05]">
            <div className="mb-3 h-2 w-16 rounded-full bg-white/10 transition-colors group-hover:bg-[#2f7bff]/40" />
            <p className="mb-2 text-[13px] font-medium text-zinc-200">{p}</p>
            <div className="space-y-1.5">
              <div className="h-1.5 rounded-full bg-white/[0.06]" /><div className="h-1.5 w-3/4 rounded-full bg-white/[0.06]" />
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between border-t border-white/[0.07] px-4 py-3">
        <p className="text-xs text-zinc-500">Draft saved · all systems connected</p>
        <Link href="/demo" className="flex items-center gap-2 rounded-full bg-[#2f7bff] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#3b82f6]">
          <Play className="h-3.5 w-3.5" /> Test call
        </Link>
      </div>
    </div>
  );
}

function AnalyticsMock() {
  const { ref, seen } = useInView<HTMLDivElement>(0.25);
  const bars = [35, 55, 42, 70, 58, 82, 66, 92, 74, 100, 86, 96];
  const outcomes = [
    { label: "Booked", pct: 62 }, { label: "Resolved", pct: 24 }, { label: "Transferred", pct: 9 }, { label: "Missed", pct: 5 },
  ];
  const feed = ["Call answered · Receptionist", "Appointment booked · +£240", "Lead qualified · hot", "Review SMS sent", "Call transferred · human"];
  const [fi, setFi] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setFi((v) => v + 1), 2200);
    return () => clearInterval(t);
  }, []);
  return (
    <div ref={ref} className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-xl md:p-8">
      <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
        {[
          { l: "Calls answered", v: <Counter to={12481} /> },
          { l: "Avg response", v: <><Counter to={0.8} decimals={1} />s</> },
          { l: "Appointments booked", v: <Counter to={1276} /> },
          { l: "Resolution rate", v: <Counter to={93} suffix="%" /> },
        ].map((s) => (
          <div key={s.l} className="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4">
            <p className="text-2xl font-bold text-white md:text-3xl">{s.v}</p>
            <p className="mt-1 text-xs text-zinc-500">{s.l}</p>
          </div>
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div>
          <p className="mb-3 text-xs uppercase tracking-[0.2em] text-zinc-500">Calls over time</p>
          <div className="flex h-36 items-end gap-1.5">
            {bars.map((h, i) => (
              <div key={i} className="flex-1 origin-bottom rounded-t bg-gradient-to-t from-[#2f7bff]/30 to-[#2f7bff]/80 transition-transform duration-1000" style={{ height: `${h}%`, transform: seen ? "scaleY(1)" : "scaleY(0)", transitionDelay: `${i * 60}ms` }} />
            ))}
          </div>
        </div>
        <div className="space-y-4">
          <div>
            <p className="mb-3 text-xs uppercase tracking-[0.2em] text-zinc-500">Call outcomes</p>
            {outcomes.map((o, i) => (
              <div key={o.label} className="mb-2 flex items-center gap-2 text-xs">
                <span className="w-20 text-zinc-400">{o.label}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.07]">
                  <div className="h-full rounded-full bg-[#2f7bff] transition-all duration-1000" style={{ width: seen ? `${o.pct}%` : "0%", transitionDelay: `${i * 120}ms` }} />
                </div>
                <span className="w-8 text-right text-zinc-300">{o.pct}%</span>
              </div>
            ))}
          </div>
          <div>
            <p className="mb-2 text-xs uppercase tracking-[0.2em] text-zinc-500">Live activity</p>
            <p key={fi} className="av-msg rounded-xl border border-white/[0.07] bg-white/[0.02] px-3 py-2 text-xs text-zinc-300">
              <span className="mr-2 inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />{feed[fi % feed.length]}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function AgentOrbit() {
  const pos = [
    "left-1/2 top-0 -translate-x-1/2 -translate-y-1/3",
    "right-0 top-1/4 translate-x-1/4",
    "right-[8%] bottom-[8%]",
    "left-[8%] bottom-[8%]",
    "left-0 top-1/4 -translate-x-1/4",
  ];
  return (
    <div className="relative mx-auto hidden h-96 max-w-3xl md:block">
      <svg className="absolute inset-0 h-full w-full" aria-hidden>
        {[50, 25, 75].map((_, i) => (
          <line key={i} x1="50%" y1="50%" x2={`${[50, 88, 78, 22, 12][i] || 50}%`} y2={`${[8, 30, 82, 82, 30][i] || 50}%`} stroke="#2f7bff" strokeOpacity="0.3" strokeWidth="1">
            <animate attributeName="stroke-opacity" values="0.15;0.5;0.15" dur="3s" begin={`${i * 0.6}s`} repeatCount="indefinite" />
          </line>
        ))}
      </svg>
      <div className="absolute left-1/2 top-1/2 flex h-28 w-28 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-[#2f7bff]/40 bg-[#2f7bff]/10 shadow-[0_0_60px_rgba(47,123,255,0.35)] backdrop-blur-xl">
        <span className="text-sm font-bold text-white">AlloVoice</span>
      </div>
      {AGENTS.map((a, i) => (
        <div key={a} className={`av-float absolute rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm text-zinc-200 backdrop-blur-xl ${pos[i]}`} style={{ animationDelay: `${i * 0.8}s` }}>
          {a}
        </div>
      ))}
      <div className="mt-4 grid gap-3 md:hidden">
        {AGENTS.map((a) => (
          <div key={a} className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-center text-sm text-zinc-200">{a}</div>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------- page ---------------------------------- */

function SectionHead({ eyebrow, title, sub }: { eyebrow?: string; title: React.ReactNode; sub?: string }) {
  return (
    <Reveal className="mx-auto mb-12 max-w-3xl text-center">
      {eyebrow && <p className="mb-3 text-xs font-semibold uppercase tracking-[0.25em] text-[#6ea8ff]">{eyebrow}</p>}
      <h2 className="text-4xl font-bold tracking-tight text-white md:text-5xl">{title}</h2>
      {sub && <p className="mt-4 text-lg text-zinc-400">{sub}</p>}
    </Reveal>
  );
}

export default function AlloVoiceLanding() {
  const [scrolled, setScrolled] = useState(false);
  const [menu, setMenu] = useState(false);
  const [annual, setAnnual] = useState(true);
  const [spot, setSpot] = useState({ x: 50, y: 30 });
  const heroRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="min-h-screen bg-[#050607] text-white antialiased">
      <style>{`
        .av-reveal { opacity: 0; transform: translateY(28px); transition: opacity .8s cubic-bezier(.2,.7,.2,1), transform .8s cubic-bezier(.2,.7,.2,1); }
        .av-seen { opacity: 1; transform: none; }
        @keyframes av-wave { 0%,100% { transform: scaleY(.3); opacity:.5 } 50% { transform: scaleY(1); opacity:1 } }
        .av-wave { transform-origin: center; animation: av-wave 1.4s ease-in-out infinite; }
        @keyframes av-float { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-10px) } }
        .av-float { animation: av-float 5s ease-in-out infinite; }
        @keyframes av-msg { from { opacity: 0; transform: translateY(8px) } to { opacity: 1; transform: none } }
        .av-msg { animation: av-msg .45s ease-out both; }
        @keyframes av-marquee { from { transform: translateX(0) } to { transform: translateX(-50%) } }
        .av-marquee { animation: av-marquee 28s linear infinite; }
        @keyframes av-wavebg { 0%,100% { transform: scaleY(.4); opacity:.35 } 50% { transform: scaleY(1); opacity:.7 } }
        .av-wavebg { transform-origin: center; animation: av-wavebg 3.2s ease-in-out infinite; }
        .av-btn { transition: transform .25s cubic-bezier(.34,1.56,.64,1), box-shadow .25s ease, background-color .2s ease; }
        .av-btn:hover { transform: scale(1.045); box-shadow: 0 0 32px rgba(47,123,255,.45); }
        .av-btn:hover .av-btn-icon { transform: translateX(3px); }
        .av-btn-icon { transition: transform .25s ease; }
      `}</style>

      {/* Nav */}
      <nav className={`fixed top-0 z-50 w-full transition-all duration-300 ${scrolled ? "border-b border-white/[0.07] bg-[#050607]/85 backdrop-blur-xl" : "border-b border-transparent bg-transparent"}`}>
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <span className="text-lg font-bold tracking-tight text-white">AlloVoice</span>
          <div className="hidden items-center gap-7 text-sm text-zinc-400 md:flex">
            {NAV.map((n) => (
              <a key={n} href={`#${n.toLowerCase()}`} className="transition hover:text-white">{n}</a>
            ))}
          </div>
          <div className="hidden items-center gap-3 md:flex">
            <Link href="/login" className="text-sm text-zinc-300 transition hover:text-white">Log in</Link>
            <Link href="/register" className="av-btn rounded-full bg-[#2f7bff] px-5 py-2 text-sm font-semibold text-white hover:bg-[#3b82f6]">Start building</Link>
          </div>
          <button className="md:hidden" onClick={() => setMenu(!menu)} aria-label="Menu">
            {menu ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>
        {menu && (
          <div className="border-t border-white/[0.07] bg-[#050607]/95 px-6 py-4 backdrop-blur-xl md:hidden">
            {NAV.map((n) => (
              <a key={n} href={`#${n.toLowerCase()}`} onClick={() => setMenu(false)} className="block py-2.5 text-sm text-zinc-300">{n}</a>
            ))}
            <div className="mt-3 flex gap-3">
              <Link href="/login" className="flex-1 rounded-full border border-white/15 py-2.5 text-center text-sm">Log in</Link>
              <Link href="/register" className="flex-1 rounded-full bg-[#2f7bff] py-2.5 text-center text-sm font-semibold">Start building</Link>
            </div>
          </div>
        )}
      </nav>

      {/* Hero */}
      <section
        ref={heroRef}
        className="relative flex min-h-screen items-center overflow-hidden pt-16"
        onMouseMove={(e) => {
          const r = heroRef.current?.getBoundingClientRect();
          if (!r) return;
          setSpot({ x: ((e.clientX - r.left) / r.width) * 100, y: ((e.clientY - r.top) / r.height) * 100 });
        }}
      >
        <div className="pointer-events-none absolute inset-0" style={{ background: `radial-gradient(600px at ${spot.x}% ${spot.y}%, rgba(47,123,255,0.09), transparent 70%)` }} />
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-[700px] w-[700px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#2f7bff]/[0.07] blur-[120px]" />
        <div className="relative mx-auto grid w-full max-w-7xl items-center gap-12 px-6 py-16 lg:grid-cols-2">
          <div>
            <p className="av-reveal av-seen mb-5 inline-block rounded-full border border-[#2f7bff]/30 bg-[#2f7bff]/[0.08] px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.25em] text-[#6ea8ff]">
              AI voice infrastructure
            </p>
            <h1 className="text-6xl font-bold leading-[1.02] tracking-tight md:text-8xl">
              Voice agents<br />that actually<br /><span className="text-[#6ea8ff]">work.</span>
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-zinc-400">
              Answer calls, qualify leads, book appointments, update your CRM, and take action automatically — 24/7.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Link href="/register" className="av-btn flex items-center justify-center gap-2 rounded-full bg-[#2f7bff] px-8 py-3.5 font-semibold text-white hover:bg-[#3b82f6]">
                Start building <ArrowRight className="av-btn-icon h-4 w-4" />
              </Link>
              <Link href="/demo" className="av-btn flex items-center justify-center gap-2 rounded-full border border-white/15 bg-white/[0.04] px-8 py-3.5 font-semibold text-white hover:border-[#2f7bff]/50">
                <Mic className="av-btn-icon h-4 w-4 text-[#6ea8ff]" /> Talk to an agent
              </Link>
            </div>
            <div className="mt-8 flex items-center gap-6 text-sm text-zinc-500">
              <span><strong className="text-white">12,481</strong> calls answered</span>
              <span><strong className="text-white">0.8s</strong> avg response</span>
            </div>
          </div>
          <div className="flex justify-center lg:justify-end">
            <LiveAgentCard />
          </div>
        </div>
      </section>

      {/* Trust */}
      <section className="border-y border-white/[0.07] py-12">
        <p className="mb-8 text-center text-2xl font-bold text-white md:text-3xl">Powering conversations that matter.</p>
        <div className="relative overflow-hidden">
          <div className="av-marquee flex w-max gap-14 pr-14">
            {[...LOGOS, ...LOGOS].map((l, i) => (
              <span key={i} className="whitespace-nowrap text-lg font-semibold text-zinc-600">{l}</span>
            ))}
          </div>
          <div className="pointer-events-none absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-[#050607] to-transparent" />
          <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-[#050607] to-transparent" />
        </div>
      </section>

      {/* Use cases */}
      <section id="solutions" className="mx-auto max-w-7xl px-6 py-24">
        <SectionHead eyebrow="Use cases" title="One voice. Any workflow." sub="Hover any workflow to preview a real conversation." />
        <Reveal><UseCases /></Reveal>
      </section>

      {/* Live conversation */}
      <section id="product" className="border-t border-white/[0.07] bg-white/[0.01]">
        <div className="mx-auto max-w-7xl px-6 py-24">
          <SectionHead eyebrow="Live demo" title="See the conversation. Watch the action happen." sub="More than talk — every call performs real tasks." />
          <Reveal><LiveConversation /></Reveal>
        </div>
      </section>

      {/* How it works */}
      <section className="mx-auto max-w-7xl px-6 py-24">
        <SectionHead title="From first hello to completed action." />
        <Reveal><Workflow /></Reveal>
      </section>

      {/* Builder */}
      <section id="resources" className="border-t border-white/[0.07]">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <SectionHead eyebrow="Builder" title="Build your agent without rebuilding your business." sub="Name it, instruct it, give it knowledge and tools — test with a live call." />
          <Reveal><BuilderMock /></Reveal>
        </div>
      </section>

      {/* Integrations */}
      <section id="integrations" className="border-t border-white/[0.07]">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <SectionHead title="Connect the systems you already use." />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {INTEGRATIONS.map((g) => (
              <Reveal key={g.name} className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 text-center transition-all duration-300 hover:-translate-y-1 hover:border-[#2f7bff]/40 hover:shadow-[0_0_30px_rgba(47,123,255,0.15)]">
                <g.icon className="mx-auto mb-3 h-6 w-6 text-zinc-500 transition-colors" />
                <p className="text-sm font-medium text-zinc-200">{g.name}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Analytics */}
      <section className="border-t border-white/[0.07] bg-white/[0.01]">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <SectionHead eyebrow="Analytics" title="Every conversation, measurable." />
          <Reveal><AnalyticsMock /></Reveal>
        </div>
      </section>

      {/* Multi-agent */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <SectionHead title="One platform. Every conversation." />
        <Reveal><AgentOrbit /></Reveal>
        <div className="mt-4 grid gap-3 md:hidden">
          {AGENTS.map((a) => (
            <div key={a} className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-center text-sm text-zinc-200">{a}</div>
          ))}
        </div>
      </section>

      {/* Security */}
      <section className="border-t border-white/[0.07]">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <SectionHead title="Built for real businesses." sub="Serious infrastructure, zero drama." />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {SECURITY.map((s) => (
              <Reveal key={s.title} className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
                <s.icon className="mb-3 h-5 w-5 text-[#6ea8ff]" />
                <p className="mb-1 font-semibold text-white">{s.title}</p>
                <p className="text-sm text-zinc-400">{s.desc}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="overflow-hidden border-t border-white/[0.07]">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <SectionHead eyebrow="Customers" title="Loved by businesses that live on the phone." />
          <div className="grid gap-6 lg:grid-cols-3">
            {TESTIMONIALS.map((t, i) => (
              <Reveal key={t.person} delay={i * 120} className={i === 1 ? "lg:-translate-y-4" : ""}>
                <figure className="flex h-full flex-col justify-between rounded-3xl border border-white/10 bg-white/[0.03] p-8">
                  <blockquote className="text-xl font-medium leading-relaxed text-white">“{t.quote}”</blockquote>
                  <figcaption className="mt-6">
                    <p className="font-semibold text-white">{t.person}</p>
                    <p className="text-sm text-zinc-500">{t.role} · {t.company}</p>
                  </figcaption>
                </figure>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="border-t border-white/[0.07] bg-white/[0.01]">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <SectionHead title="Start small. Scale without limits." />
          <div className="mb-10 flex items-center justify-center gap-3 text-sm">
            <span className={!annual ? "text-white" : "text-zinc-500"}>Monthly</span>
            <button onClick={() => setAnnual(!annual)} className="relative h-7 w-13 rounded-full bg-white/10 p-1 transition" style={{ width: 52 }} aria-label="Toggle billing period">
              <span className={`block h-5 w-5 rounded-full bg-[#2f7bff] transition-all ${annual ? "translate-x-6" : ""}`} />
            </button>
            <span className={annual ? "text-white" : "text-zinc-500"}>Annual <span className="text-xs text-emerald-300">−20%</span></span>
          </div>
          <div className="grid gap-5 md:grid-cols-3">
            {PLANS.map((p) => (
              <div key={p.name} className={`rounded-3xl p-8 backdrop-blur-xl ${p.popular ? "border border-[#2f7bff]/60 bg-[#2f7bff]/[0.07] shadow-[0_0_60px_rgba(47,123,255,0.18)]" : "border border-white/10 bg-white/[0.03]"}`}>
                <p className="mb-2 font-semibold text-white">{p.name}</p>
                <p className="mb-6">
                  {p.monthly < 0 ? (
                    <span className="text-4xl font-bold text-white">Custom</span>
                  ) : (
                    <>
                      <span className="text-5xl font-bold text-white">${annual ? Math.round(p.monthly * 0.8) : p.monthly}</span>
                      <span className="text-zinc-500">/mo</span>
                    </>
                  )}
                </p>
                <ul className="mb-8 space-y-2.5 text-sm text-zinc-300">
                  {[p.minutes, p.agents, p.integrations, p.support].map((f) => (
                    <li key={f} className="flex items-center gap-2"><Check className="h-4 w-4 text-[#6ea8ff]" />{f}</li>
                  ))}
                </ul>
                <Link href="/register" className={`block rounded-full py-3 text-center text-sm font-semibold transition ${p.popular ? "bg-[#2f7bff] text-white hover:bg-[#3b82f6]" : "border border-white/15 text-white hover:border-white/30"}`}>
                  {p.monthly < 0 ? "Talk to sales" : "Start building"}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="border-t border-white/[0.07]">
        <div className="mx-auto max-w-3xl px-6 py-24">
          <SectionHead title="Questions, answered." />
          <Faq />
        </div>
      </section>

      {/* Final CTA */}
      <section className="relative overflow-hidden border-t border-white/[0.07] py-32">
        <div className="pointer-events-none absolute left-1/2 top-1/2 h-[500px] w-[900px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#2f7bff]/10 blur-[130px]" />
        <div className="pointer-events-none absolute inset-x-0 bottom-8 flex h-24 items-center justify-center gap-1 opacity-40" aria-hidden>
          {WAVE.map((h, i) => (
            <span key={i} className="av-wavebg w-1.5 rounded-full bg-[#2f7bff]/60" style={{ height: `${h * 0.7}px`, animationDelay: `${(i % 14) * 0.15}s` }} />
          ))}
        </div>
        <div className="relative mx-auto max-w-4xl px-6 text-center">
          <h2 className="text-5xl font-bold tracking-tight md:text-7xl">Give your business<br />a <span className="text-[#6ea8ff]">voice.</span></h2>
          <p className="mx-auto mt-5 max-w-xl text-lg text-zinc-400">Build an AI voice agent that answers, understands, and takes action.</p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href="/register" className="av-btn rounded-full bg-[#2f7bff] px-9 py-3.5 font-semibold text-white hover:bg-[#3b82f6]">Start building</Link>
            <Link href="/demo" className="av-btn flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.04] px-9 py-3.5 font-semibold text-white hover:border-[#2f7bff]/50"><Mic className="av-btn-icon h-4 w-4 text-[#6ea8ff]" /> Talk to an agent</Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/[0.07]">
        <div className="mx-auto max-w-7xl px-6 py-14">
          <div className="grid gap-10 md:grid-cols-[1.5fr_1fr_1fr_1fr_1fr_1fr]">
            <div>
              <p className="mb-3 text-lg font-bold text-white">AlloVoice</p>
              <p className="max-w-xs text-sm leading-relaxed text-zinc-500">AI voice infrastructure for businesses that live on the phone.</p>
            </div>
            {[
              { h: "Product", l: ["Voice agents", "Phone numbers", "Analytics", "Pricing"] },
              { h: "Solutions", l: ["Receptionist", "Sales", "Support", "Collections"] },
              { h: "Developers", l: ["Documentation", "API reference", "Webhooks", "Status"] },
              { h: "Company", l: ["About", "Blog", "Careers", "Contact"] },
              { h: "Resources", l: ["Showcase", "Help center", "Community", "Changelog"] },
            ].map((c) => (
              <div key={c.h}>
                <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-zinc-500">{c.h}</p>
                <ul className="space-y-2.5 text-sm text-zinc-400">
                  {c.l.map((l) => (
                    <li key={l}><a href={l === "Showcase" ? "/showcase" : "#"} className="transition hover:text-white">{l}</a></li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-white/[0.07] pt-6 text-xs text-zinc-500 md:flex-row">
            <p>© AlloVoice</p>
            <div className="flex gap-5">
              <Link href="/privacy" className="hover:text-zinc-300">Privacy</Link>
              <Link href="/terms" className="hover:text-zinc-300">Terms</Link>
              <span className="cursor-default">Security</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

function Faq() {
  const [open, setOpen] = useState(0);
  const items = [
    { q: "How long does setup take?", a: "Most businesses take their first live call within a day. Connect a number, pick a voice, add your FAQs — done." },
    { q: "Does it work with our systems?", a: "Yes — calendar, CRM, Slack, Gmail and 8,000+ apps via Zapier, plus webhooks and a REST API for anything custom." },
    { q: "What happens when the AI can't help?", a: "Warm transfer to your team with full conversation context, or a ticket with transcript and summary. Nothing gets lost." },
    { q: "Is call data secure?", a: "Encrypted in transit and at rest, EU/US regions, audit logs, role-based access and PII redaction on every plan." },
  ];
  return (
    <div className="space-y-3">
      {items.map((f, i) => (
        <div key={f.q} className="rounded-2xl border border-white/10 bg-white/[0.03]">
          <button className="flex w-full items-center justify-between p-5 text-left font-medium text-white" onClick={() => setOpen(open === i ? -1 : i)}>
            {f.q}
            <ChevronDown className={`h-5 w-5 shrink-0 text-zinc-500 transition-transform ${open === i ? "rotate-180" : ""}`} />
          </button>
          {open === i && <p className="px-5 pb-5 text-sm leading-relaxed text-zinc-400">{f.a}</p>}
        </div>
      ))}
    </div>
  );
}
