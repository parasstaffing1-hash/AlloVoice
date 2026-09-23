"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Wrench, Flame, Zap, ArrowRight, WifiOff, Loader2, PhoneCall, Home, Stethoscope, Sparkles, Scale, Car, BedDouble, Briefcase, ShoppingBag, HardHat, ShieldCheck, Dumbbell, UtensilsCrossed, Plane, GraduationCap, HeartPulse, Building2, Star } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

type Template = {
  id: string;
  kind: string;
  industry: string;
  locale: string;
  name: string;
  greeting: string;
  voice: string;
  brand_color?: string;
};

type Filter = "All" | "Voice" | "Chat";

const FALLBACK_TEMPLATES: Template[] = [
  {
    id: "voice-plumbing-uk",
    kind: "voice",
    industry: "plumbing",
    locale: "en-GB",
    name: "AquaFlow Plumbing — AI Receptionist",
    greeting: "Thanks for calling AquaFlow Plumbing, how can I help today?",
    voice: "en-GB-female",
    brand_color: "#0ea5e9",
  },
  {
    id: "voice-hvac-uk",
    kind: "voice",
    industry: "hvac",
    locale: "en-GB",
    name: "CosyHeat HVAC — AI Receptionist",
    greeting: "Thanks for calling CosyHeat, is it a boiler or heating issue I can help with?",
    voice: "en-GB-male",
    brand_color: "#f97316",
  },
  {
    id: "voice-electrician-uk",
    kind: "voice",
    industry: "electrician",
    locale: "en-GB",
    name: "SparkSafe Electrics — AI Receptionist",
    greeting: "Thanks for calling SparkSafe Electrics, what electrical job can I book in for you?",
    voice: "en-GB-female",
    brand_color: "#eab308",
  },
];

const STATIC_FEATURES: Record<string, string[]> = {
  "voice-plumbing-uk": ["24/7 leak & blockage triage", "Fixed-price callout quotes", "Same-day slot booking"],
  "voice-hvac-uk": ["Boiler breakdown triage", "Annual service reminders", "Gas-safe escalation handoff"],
  "voice-electrician-uk": ["Fault-finding intake questions", "EICR & rewiring quotes", "Emergency callout routing"],
};

function slugFor(t: Template): string {
  const id = (t.id || "").toLowerCase();
  const m = id.match(/^(?:voice|chat)-(.+?)-(?:uk|us|ae)$/);
  if (m) return m[1];
  const raw = (t.industry || t.id || "").toLowerCase();
  if (raw.includes("plumb")) return "plumbing";
  if (raw.includes("hvac") || raw.includes("heat") || raw.includes("boiler")) return "hvac";
  if (raw.includes("electr")) return "electrician";
  return raw.replace(/[^a-z-]/g, "") || "plumbing";
}

function iconFor(slug: string, cls: string) {
  const map: Record<string, any> = {
    plumbing: Wrench, hvac: Flame, electrician: Zap,
    "real-estate": Home, dental: Stethoscope, cleaning: Sparkles,
    roofing: Building2, "law-firm": Scale, "auto-repair": Car,
    hotel: BedDouble, "crm-voice": Briefcase, saas: Star,
    ecommerce: ShoppingBag, recruitment: Briefcase, construction: HardHat,
    insurance: ShieldCheck, gym: Dumbbell, restaurant: UtensilsCrossed,
    travel: Plane, education: GraduationCap, medical: HeartPulse,
  };
  const Icon = map[slug] || Wrench;
  return <Icon className={cls} />;
}

export default function ShowcasePage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("All");

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/api/agents/templates`)
      .then((r: any) => {
        if (!r.ok) throw new Error(`templates ${r.status}`);
        return r.json();
      })
      .then((d: any) => {
        const list = Array.isArray(d) ? d : d.templates || [];
        if (!list || list.length === 0) {
          setTemplates(FALLBACK_TEMPLATES);
          setOffline(true);
        } else {
          setTemplates(list);
          setOffline(false);
        }
        setLoading(false);
      })
      .catch((e: any) => {
        setTemplates(FALLBACK_TEMPLATES);
        setOffline(true);
        setError(e?.message || "API unreachable");
        setLoading(false);
      });
  }, []);

  const visible =
    filter === "Chat"
      ? templates.filter((t) => (t.kind || "voice").toLowerCase() === "chat")
      : filter === "Voice"
        ? templates.filter((t) => (t.kind || "voice").toLowerCase() === "voice")
        : templates;

  const pills: Filter[] = ["All", "Voice", "Chat"];

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* Hero */}
      <section className="border-b border-white/10 bg-gradient-to-b from-purple-950/60 via-zinc-950 to-zinc-950">
        <div className="mx-auto max-w-6xl px-4 py-14 text-center sm:py-20">
          <p className="mx-auto mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs text-zinc-300">
            <PhoneCall className="h-3.5 w-3.5 text-purple-400" />
            Allo portfolio — live voice agent demos
          </p>
          <h1 className="mx-auto max-w-3xl text-3xl font-bold leading-tight sm:text-5xl">
            Voice agents that answer like your best receptionist
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-sm text-zinc-400 sm:text-base">
            Real AI receptionists for UK trades — they greet callers, triage jobs, quote fixed prices and book
            slots around the clock. Pick a trade below and try a live demo.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-2">
            {pills.map((p) => (
              <button
                key={p}
                onClick={() => setFilter(p)}
                className={`rounded-full px-5 py-2 text-sm font-medium transition-colors ${
                  filter === p
                    ? "bg-purple-600 text-white"
                    : "border border-white/10 bg-white/5 text-zinc-300 hover:bg-white/10"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </section>

      <main className="mx-auto max-w-6xl px-4 py-10">
        {offline && (
          <div className="mb-6 flex items-start gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            <WifiOff className="mt-0.5 h-4 w-4 shrink-0" />
            <p>
              Live demo unavailable offline — showing built-in preview cards. Connect to {API} for live templates.
              {error ? ` (${error})` : ""}
            </p>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-20 text-sm text-zinc-400">
            <Loader2 className="h-5 w-5 animate-spin" /> Loading voice agents…
          </div>
        ) : filter === "Chat" && visible.length === 0 ? (
          <div className="mx-auto max-w-md rounded-2xl border border-white/10 bg-white/5 px-6 py-12 text-center">
            <p className="text-lg font-semibold">No chat agents found</p>
            <p className="mt-2 text-sm text-zinc-400">
              Try a different filter to see live agents.
            </p>
            <button
              onClick={() => setFilter("All")}
              className="mt-6 rounded-full bg-purple-600 px-5 py-2 text-sm font-medium text-white hover:bg-purple-500"
            >
              View all agents
            </button>
          </div>
        ) : visible.length === 0 ? (
          <div className="mx-auto max-w-md rounded-2xl border border-white/10 bg-white/5 px-6 py-12 text-center">
            <p className="text-lg font-semibold">No agents in this filter</p>
            <p className="mt-2 text-sm text-zinc-400">Try a different filter to see live trades.</p>
          </div>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((t) => {
              const slug = slugFor(t);
              const feats = STATIC_FEATURES[t.id] || ["24/7 call answering", "Job triage & quotes", "Calendar booking"];
              const accent = t.brand_color || "#a855f7";
              return (
                <article
                  key={t.id}
                  className="flex flex-col rounded-2xl border border-white/10 bg-white/5 p-6 backdrop-blur-xl transition-colors hover:border-white/20"
                >
                  <div className="flex items-center justify-between">
                    <span
                      className="flex h-11 w-11 items-center justify-center rounded-xl"
                      style={{ backgroundColor: `${accent}22`, color: accent }}
                    >
                      {iconFor(slug, "h-5 w-5")}
                    </span>
                    <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] text-zinc-300">
                      {t.locale || "en-GB"}
                    </span>
                  </div>
                  <h2 className="mt-4 text-lg font-semibold leading-snug">{t.name}</h2>
                  <p className="mt-1 line-clamp-2 text-sm italic text-zinc-400">“{t.greeting}”</p>
                  <ul className="mt-4 space-y-2 text-sm text-zinc-300">
                    {feats.slice(0, 3).map((f) => (
                      <li key={f} className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: accent }} />
                        {f}
                      </li>
                    ))}
                  </ul>
                  <Link
                    href={`/showcase/${slug}`}
                    className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-purple-300 hover:text-purple-200"
                  >
                    Try live demo <ArrowRight className="h-4 w-4" />
                  </Link>
                </article>
              );
            })}
          </div>
        )}

        {/* Stats strip */}
        <section className="mt-12 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ["24/7", "always answering"],
            ["<2s", "median replies"],
            ["3", "trades live"],
            ["en-GB", "UK voice & tone"],
          ].map(([big, small]) => (
            <div key={small} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-5 text-center">
              <p className="text-2xl font-bold text-white">{big}</p>
              <p className="mt-1 text-xs text-zinc-400">{small}</p>
            </div>
          ))}
        </section>

        {/* CTA banner */}
        <section className="mt-10 overflow-hidden rounded-2xl border border-purple-500/30 bg-gradient-to-r from-purple-900/60 via-zinc-900 to-zinc-900 px-6 py-10 text-center sm:px-12">
          <h2 className="text-xl font-bold sm:text-2xl">Like what you hear? Put one on your phones.</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-zinc-400">
            Talk to us about call volumes, pricing and onboarding — most trades go live in days, not months.
          </p>
          <Link
            href="/demo"
            className="mt-6 inline-flex items-center gap-2 rounded-full bg-purple-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-purple-500"
          >
            Talk to us <ArrowRight className="h-4 w-4" />
          </Link>
        </section>
      </main>
    </div>
  );
}
