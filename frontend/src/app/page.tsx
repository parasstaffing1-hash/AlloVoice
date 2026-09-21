"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Zap,
  Mic,
  MapPin,
  FileText,
  ArrowRight,
  Star,
  CheckCircle2,
  Calendar,
  PoundSterling,
  ShieldCheck,
  PhoneCall,
  MessageSquare,
  ChevronDown,
  Play,
  Volume2,
} from "lucide-react";

const WAVE_BARS = [14, 26, 38, 52, 66, 80, 92, 100, 92, 80, 66, 52, 38, 26, 18, 28, 44, 60, 74, 88, 96, 84, 68, 50, 34, 20, 12, 22, 36, 48];

const features = [
  { icon: Mic, title: "AI Voice Quotes", description: "Describe the job out loud. Itemised, VAT-correct quotes in seconds — with a spoken reply in a UK voice." },
  { icon: PhoneCall, title: "24/7 Voice Agent", description: "A polite British assistant that answers booking questions, explains documents needed, and captures leads while you're on a job." },
  { icon: Calendar, title: "Smart Scheduling", description: "Auto-assigns engineers by skill, postcode and availability. Calendar invites included." },
  { icon: MapPin, title: "Live Engineer Tracking", description: "Customers watch their engineer approach on a live map with accurate ETAs." },
  { icon: FileText, title: "Certificates & Invoicing", description: "Gas Safety CP12, F-Gas, EICR records plus Stripe card payments and Direct Debit." },
  { icon: Star, title: "Reviews on Autopilot", description: "Google and Trustpilot requests fire after every job. AI drafts the replies." },
];

const steps = [
  { n: "1", title: "Talk", description: "Speak or type a job description. The AI understands boilers, consumer units, U-values and trade slang." },
  { n: "2", title: "Review", description: "Check the itemised quote, tweak line items, pick Good / Better / Best presentation." },
  { n: "3", title: "Send", description: "PDF goes to the customer by email, SMS or WhatsApp. They accept, you get paid." },
];

const trades = [
  { name: "Plumbers", line: "Leak triage by voice, parts picked from the price book, invoice before you leave the driveway." },
  { name: "Gas Engineers", line: "CP12 certificates generated on site with customer signature captured on screen." },
  { name: "Electricians", line: "EICR observations coded C1–C4, remedial quotes built from the findings automatically." },
  { name: "HVAC & Heating", line: "F-Gas logbooks, seasonal service plans and Direct Debit memberships that renew themselves." },
];

const plans = [
  { name: "Starter", price: "£29", per: "/user/mo", features: ["Jobs, quotes & invoicing", "Customer management", "Email support"] },
  { name: "Growth", price: "£49", per: "/user/mo", popular: true, features: ["Everything in Starter", "Voice agent + scheduling", "Reviews & marketing", "Priority support"] },
  { name: "Trade", price: "£79", per: "/user/mo", features: ["Everything in Growth", "Multi-branch & fleet", "API access", "Dedicated support"] },
];

const faqs = [
  { q: "Do my customers need to install anything?", a: "No. Quotes, tracking links and payment pages open in any browser. Engineers use Allo on any phone or tablet — nothing to install." },
  { q: "How does the voice quoting work?", a: "Tap the mic, describe the job in plain English. Speech is transcribed locally in your browser, our AI builds an itemised quote, and a UK voice reads the total back to you." },
  { q: "Is my data safe?", a: "UK GDPR compliant with data processing agreements, encrypted storage, EU/UK data residency on managed infrastructure, and full export/erase tools built in." },
  { q: "Can it handle Gas Safety and F-Gas paperwork?", a: "Yes — CP12, F-Gas logbooks and EICR records are first-class citizens, with PDFs, signatures and renewal reminders." },
  { q: "What does it cost?", a: "From £29 per user per month with a 14-day trial. Card payments cost 1.5% + 20p via Stripe; AI voice and text messages are metered at pennies." },
];

function VoiceOrb({ active, typed }: { active: boolean; typed: string }) {
  return (
    <div className="relative mx-auto flex h-72 w-72 items-center justify-center md:h-96 md:w-96">
      <div className="absolute inset-0 rounded-full bg-primary/10 animate-ping [animation-duration:2.6s]" />
      <div className={`absolute inset-0 rounded-full border border-primary/30 vf-ring ${active ? "[animation-duration:1.1s]" : ""}`} />
      <div className="absolute inset-6 rounded-full border border-primary/20" />
      <div className="absolute inset-12 rounded-full border border-primary/30 bg-primary/5 backdrop-blur-xl" />
      <div className={`absolute inset-20 rounded-full bg-gradient-to-br from-primary/40 via-primary/15 to-transparent blur-md transition-all ${active ? "scale-110 from-primary/60" : ""}`} />
      <div className={`relative z-10 flex h-28 w-28 items-center justify-center rounded-full bg-gradient-to-br from-primary to-orange-700 transition-all md:h-36 md:w-36 ${active ? "scale-105 shadow-[0_0_120px_rgba(249,115,22,0.8)]" : "shadow-[0_0_80px_rgba(249,115,22,0.55)]"}`}>
        <Mic className="h-12 w-12 text-white md:h-16 md:w-16" />
      </div>
      <div className="absolute -bottom-2 z-10 flex h-12 items-end gap-1">
        {WAVE_BARS.map((h, i) => (
          <span
            key={i}
            className="w-1 rounded-full bg-primary/80 vf-wave"
            style={{ height: `${h * 0.5}px`, animationDelay: `${(i % 10) * 0.12}s`, animationDuration: active ? "0.7s" : "1.4s" }}
          />
        ))}
      </div>
      <div className="absolute -left-4 top-8 z-10 hidden min-w-44 rounded-xl border border-border/60 bg-card/80 px-3 py-2 text-xs backdrop-blur-xl md:block vf-float">
        <span className="text-muted-foreground">“{typed}<span className="vf-caret">|</span>”</span>
      </div>
      <div className="absolute -right-6 bottom-16 z-10 hidden rounded-xl border border-primary/30 bg-primary/10 px-3 py-2 text-xs backdrop-blur-xl md:block vf-float-delay">
        <span className="font-semibold text-primary">Quote ready · £240</span>
      </div>
    </div>
  );
}

const TYPE_PHRASES = [
  "Boiler losing pressure…",
  "Radiator cold at the top…",
  "EICR needed for rental flat…",
  "Consumer unit keeps tripping…",
];

export default function LandingPage() {
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const [typed, setTyped] = useState("");
  const [playing, setPlaying] = useState(false);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const heroRef = useRef<HTMLElement>(null);

  // Typewriter cycling through sample customer phrases
  useEffect(() => {
    let pi = 0, ci = 0, deleting = false, timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      const phrase = TYPE_PHRASES[pi];
      if (!deleting) {
        ci += 1;
        setTyped(phrase.slice(0, ci));
        if (ci >= phrase.length) { deleting = true; timer = setTimeout(tick, 1600); return; }
        timer = setTimeout(tick, 55);
      } else {
        ci -= 1;
        setTyped(phrase.slice(0, ci));
        if (ci <= 0) { deleting = false; pi = (pi + 1) % TYPE_PHRASES.length; timer = setTimeout(tick, 400); return; }
        timer = setTimeout(tick, 28);
      }
    };
    timer = setTimeout(tick, 600);
    return () => clearTimeout(timer);
  }, []);

  // One-click spoken demo — browser speech, no backend, no keys
  const playDemo = () => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const synth = window.speechSynthesis;
    if (playing) { synth.cancel(); setPlaying(false); return; }
    const utter = new SpeechSynthesisUtterance(
      "Here's your quote for a boiler service. The estimated cost is £240 including VAT. Would you like to proceed?"
    );
    utter.rate = 1.02;
    const voices = synth.getVoices();
    const gb = voices.find((v) => v.lang?.toLowerCase().startsWith("en-gb"))
      || voices.find((v) => v.lang?.toLowerCase().startsWith("en"));
    if (gb) utter.voice = gb;
    utter.onend = () => setPlaying(false);
    utter.onerror = () => setPlaying(false);
    synth.cancel();
    synth.speak(utter);
    setPlaying(true);
  };

  useEffect(() => () => { try { window.speechSynthesis?.cancel(); } catch {} }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <style>{`
        @keyframes vf-wave { 0%,100% { transform: scaleY(0.35); opacity:.55 } 50% { transform: scaleY(1); opacity:1 } }
        .vf-wave { transform-origin: bottom; animation: vf-wave 1.4s ease-in-out infinite; }
        @keyframes vf-float { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-10px) } }
        .vf-float { animation: vf-float 5s ease-in-out infinite; }
        .vf-float-delay { animation: vf-float 6s ease-in-out 1.2s infinite; }
        @keyframes vf-rise { from { opacity: 0; transform: translateY(28px) } to { opacity: 1; transform: none } }
        .vf-rise { opacity: 0; animation: vf-rise 0.85s cubic-bezier(0.2,0.7,0.2,1) forwards; }
        @keyframes vf-pan { 0% { background-position: 0% 50% } 50% { background-position: 100% 50% } 100% { background-position: 0% 50% } }
        .vf-gradient-text { background: linear-gradient(90deg,#fdba74,#f97316,#ef4444,#fdba74); background-size: 220% auto; -webkit-background-clip: text; background-clip: text; color: transparent; animation: vf-pan 6s linear infinite; }
        @keyframes vf-caret { 0%,100% { opacity: 1 } 50% { opacity: 0 } }
        .vf-caret { animation: vf-caret 1s step-end infinite; }
        @keyframes vf-drift { 0%,100% { transform: translate(0,0) scale(1) } 50% { transform: translate(40px,-30px) scale(1.15) } }
        .vf-blob { animation: vf-drift 12s ease-in-out infinite; filter: blur(90px); }
        @keyframes vf-ring { 0% { transform: scale(0.85); opacity: 0.7 } 100% { transform: scale(1.25); opacity: 0 } }
        .vf-ring { animation: vf-ring 2.6s ease-out infinite; }
      `}</style>

      {/* Nav */}
      <nav className="fixed top-0 z-50 w-full border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <div className="flex items-center gap-2">
            <Zap className="h-6 w-6 text-primary" />
            <span className="text-xl font-bold gradient-text">Allo</span>
          </div>
          <div className="hidden items-center gap-6 text-sm text-muted-foreground md:flex">
            <a href="#features" className="hover:text-foreground">Features</a>
            <a href="#how" className="hover:text-foreground">How it works</a>
            <a href="#trades" className="hover:text-foreground">Trades</a>
            <a href="#pricing" className="hover:text-foreground">Pricing</a>
            <a href="#faq" className="hover:text-foreground">FAQ</a>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login"><Button variant="ghost">Log in</Button></Link>
            <Link href="/register"><Button>Get Started</Button></Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section
        ref={heroRef}
        className="relative overflow-hidden pt-32 pb-16"
        onMouseMove={(e) => {
          const r = heroRef.current?.getBoundingClientRect();
          if (!r) return;
          setTilt({
            x: ((e.clientX - r.left) / r.width - 0.5) * 16,
            y: ((e.clientY - r.top) / r.height - 0.5) * 16,
          });
        }}
      >
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-primary/15 via-background to-background" />
        <div className="vf-blob absolute -left-24 top-24 h-72 w-72 rounded-full bg-primary/15" />
        <div className="vf-blob absolute -right-24 top-64 h-80 w-80 rounded-full bg-orange-700/15 [animation-delay:3s]" />
        <div className="relative mx-auto max-w-7xl px-6 text-center">
          <div className="vf-rise mb-6 inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/5 px-4 py-1.5 text-sm text-primary">
            <Volume2 className="h-4 w-4" />
            UK voice AI · Live today · Free trial
          </div>
          <h1 className="vf-rise mb-6 text-5xl font-bold tracking-tight md:text-7xl" style={{ animationDelay: "0.12s" }}>
            Your business,
            <br />
            <span className="vf-gradient-text">answered in your own voice</span>
          </h1>
          <p className="vf-rise mx-auto mb-10 max-w-2xl text-lg text-muted-foreground" style={{ animationDelay: "0.24s" }}>
            Allo is the AI voice assistant for UK field service. It quotes jobs from speech,
            answers customers 24/7 in a British voice, and handles dispatch, certificates and payments.
          </p>
          <div className="vf-rise mb-6 flex flex-col items-center gap-4 sm:flex-row sm:justify-center" style={{ animationDelay: "0.36s" }}>
            <Link href="/register">
              <Button size="lg" className="gap-2 px-8 text-base glow">
                <Play className="h-4 w-4" /> Start free trial <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Button size="lg" variant="outline" className="gap-2 px-8 text-base" onClick={playDemo}>
              {playing ? <Volume2 className="h-4 w-4 animate-pulse" /> : <Mic className="h-4 w-4" />}
              {playing ? "Stop demo" : "Play voice demo"}
            </Button>
          </div>
          <div className="vf-rise mb-12" style={{ animationDelay: "0.44s" }}>
            <Link href="/voice-agent" className="text-sm text-muted-foreground underline-offset-4 hover:text-primary hover:underline">
              or open the full interactive voice agent →
            </Link>
          </div>
          <div className="vf-rise" style={{ animationDelay: "0.55s", transform: `translate(${tilt.x}px, ${tilt.y}px)`, transition: "transform 0.3s ease-out" }}>
            <VoiceOrb active={playing} typed={typed} />
          </div>
          <p className="vf-rise mt-6 text-xs uppercase tracking-widest text-muted-foreground" style={{ animationDelay: "0.65s" }}>
            Trusted by 2,000+ UK boiler engineers · plumbers · electricians · HVAC teams
          </p>
        </div>
      </section>

      {/* Stats */}
      <section className="border-y border-border/50 py-10">
        <div className="mx-auto grid max-w-6xl grid-cols-2 gap-8 px-6 text-center md:grid-cols-4">
          {[["10x", "faster quoting"], ["24/7", "AI call cover"], ["35+", "trades workflows"], ["20%", "UK VAT handled"]].map(([v, l]) => (
            <div key={l}>
              <div className="text-3xl font-bold gradient-text">{v}</div>
              <div className="mt-1 text-sm text-muted-foreground">{l}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20">
        <div className="mx-auto max-w-7xl px-6">
          <div className="mb-14 text-center">
            <h2 className="mb-4 text-4xl font-bold">One assistant. <span className="gradient-text">Every job covered.</span></h2>
            <p className="text-lg text-muted-foreground">From first call to final payment — without typing.</p>
          </div>
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <div key={f.title} className="group rounded-2xl border border-border/50 bg-card/50 p-6 transition-all hover:border-primary/50">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:bg-primary/20">
                  <f.icon className="h-6 w-6" />
                </div>
                <h3 className="mb-2 text-lg font-semibold">{f.title}</h3>
                <p className="text-sm text-muted-foreground">{f.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="border-t border-border/50 py-20">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="mb-12 text-center text-4xl font-bold">Speak. Review. <span className="gradient-text">Send.</span></h2>
          <div className="grid gap-6 md:grid-cols-3">
            {steps.map((s) => (
              <div key={s.n} className="rounded-2xl border border-border/50 bg-card/50 p-8 text-center">
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-xl font-bold text-white shadow-[0_0_30px_rgba(249,115,22,0.4)]">{s.n}</div>
                <h3 className="mb-2 text-xl font-semibold">{s.title}</h3>
                <p className="text-sm text-muted-foreground">{s.description}</p>
              </div>
            ))}
          </div>
          <div className="mx-auto mt-10 max-w-2xl rounded-2xl border border-primary/25 bg-primary/5 p-5">
            <div className="flex items-start gap-3">
              <MessageSquare className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
              <p className="text-sm italic text-muted-foreground">
                “Boiler losing pressure and banging. Worcester combi, Manchester M1.”
                <span className="mt-2 block font-semibold not-italic text-foreground">→ Itemised quote £240 inc. VAT, read back in 8 seconds.</span>
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Trades */}
      <section id="trades" className="border-t border-border/50 py-20">
        <div className="mx-auto max-w-7xl px-6">
          <h2 className="mb-12 text-center text-4xl font-bold">Built for <span className="gradient-text">your trade</span></h2>
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {trades.map((t) => (
              <div key={t.name} className="rounded-2xl border border-border/50 bg-card/50 p-6">
                <div className="mb-3 flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-green-400" />
                  <h3 className="font-semibold">{t.name}</h3>
                </div>
                <p className="text-sm text-muted-foreground">{t.line}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="border-t border-border/50 py-20">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="mb-2 text-center text-4xl font-bold">Simple <span className="gradient-text">per-user pricing</span></h2>
          <p className="mb-12 text-center text-muted-foreground">14-day trial · Cancel anytime · Prices ex. VAT</p>
          <div className="grid gap-6 md:grid-cols-3">
            {plans.map((p) => (
              <div key={p.name} className={`rounded-2xl border p-8 text-center ${p.popular ? "border-primary bg-primary/5 shadow-[0_0_50px_rgba(249,115,22,0.15)]" : "border-border/50 bg-card/50"}`}>
                {p.popular && <div className="mb-3 text-xs font-bold uppercase tracking-widest text-primary">Most popular</div>}
                <h3 className="text-lg font-semibold">{p.name}</h3>
                <div className="my-4"><span className="text-5xl font-bold">{p.price}</span><span className="text-muted-foreground">{p.per}</span></div>
                <ul className="mb-8 space-y-2 text-sm text-muted-foreground">
                  {p.features.map((f) => <li key={f} className="flex items-center justify-center gap-2"><CheckCircle2 className="h-4 w-4 text-green-400" />{f}</li>)}
                </ul>
                <Link href="/register"><Button className="w-full" variant={p.popular ? "default" : "outline"}>Choose {p.name}</Button></Link>
              </div>
            ))}
          </div>
          <p className="mt-6 flex items-center justify-center gap-2 text-sm text-muted-foreground">
            <PoundSterling className="h-4 w-4" /> Card payments 1.5% + 20p · AI voice & texts metered at pennies
          </p>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="border-t border-border/50 py-20">
        <div className="mx-auto max-w-3xl px-6">
          <h2 className="mb-10 text-center text-4xl font-bold">Questions, <span className="gradient-text">answered</span></h2>
          <div className="space-y-3">
            {faqs.map((f, i) => (
              <div key={f.q} className="rounded-xl border border-border/50 bg-card/50">
                <button className="flex w-full items-center justify-between p-5 text-left font-medium" onClick={() => setOpenFaq(openFaq === i ? null : i)}>
                  {f.q}
                  <ChevronDown className={`h-5 w-5 shrink-0 text-muted-foreground transition-transform ${openFaq === i ? "rotate-180" : ""}`} />
                </button>
                {openFaq === i && <p className="px-5 pb-5 text-sm text-muted-foreground">{f.a}</p>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border/50 py-20">
        <div className="mx-auto max-w-4xl px-6 text-center">
          <h2 className="mb-4 text-4xl font-bold">Put your business <span className="gradient-text">on voice</span></h2>
          <p className="mb-8 text-lg text-muted-foreground">Free 14-day trial. No credit card. Live in an afternoon.</p>
          <Link href="/register">
            <Button size="lg" className="gap-2 px-12 py-6 text-lg glow">Start Free <ArrowRight className="h-5 w-5" /></Button>
          </Link>
        </div>
      </section>

      <footer className="border-t border-border/50 py-8">
        <div className="mx-auto max-w-7xl px-6 text-center text-sm text-muted-foreground">
          <div className="mb-4 flex items-center justify-center gap-2">
            <Zap className="h-4 w-4 text-primary" />
            <span className="font-semibold gradient-text">Allo</span>
          </div>
          <p>&copy; 2026 Allo. Built for UK field service businesses.</p>
        </div>
      </footer>
    </div>
  );
}
