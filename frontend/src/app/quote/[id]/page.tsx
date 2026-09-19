"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { formatCurrency, formatDateTime } from "@/lib/utils";
import { QRCodeSVG } from "qrcode.react";
import {
  Check,
  X,
  Crown,
  Star,
  Shield,
  Loader2,
  Heart,
  MessageSquare,
  CheckCircle2,
} from "lucide-react";

interface TierFeature {
  name: string;
  included: boolean;
}

interface QuoteTier {
  id: string;
  name: "Good" | "Better" | "Best";
  description: string;
  price: number;
  materials_cost: number;
  labour_cost: number;
  vat_amount: number;
  features: TierFeature[];
  is_recommended: boolean;
}

interface QuoteData {
  id: string;
  quote_number: string;
  title: string;
  customer_name: string;
  subtotal: number;
  tax_rate: number;
  tax_amount: number;
  total: number;
  notes: string;
  valid_until: string;
  is_accepted: boolean;
  created_at: string;
  tiers?: QuoteTier[];
  items?: { description: string; quantity: number; unit_price: number; total: number }[];
}

const tierConfig = {
  Good: {
    icon: Shield,
    gradient: "from-slate-500 to-slate-600",
    border: "border-slate-500/30",
    glow: "shadow-slate-500/10",
    badge: "bg-slate-500/20 text-slate-300",
    buttonVariant: "outline" as const,
  },
  Better: {
    icon: Star,
    gradient: "from-blue-500 to-cyan-500",
    border: "border-blue-500/30",
    glow: "shadow-blue-500/20",
    badge: "bg-blue-500/20 text-blue-300",
    buttonVariant: "default" as const,
  },
  Best: {
    icon: Crown,
    gradient: "from-purple-500 to-pink-500",
    border: "border-purple-500/30",
    glow: "shadow-purple-500/20",
    badge: "bg-purple-500/20 text-purple-300",
    buttonVariant: "default" as const,
  },
};

function generateTiersFromFlatQuote(quote: QuoteData): QuoteTier[] {
  const base = quote.total;
  return [
    {
      id: "good",
      name: "Good",
      description: "Essential service with standard materials and workmanship guarantee.",
      price: Math.round(base * 0.7),
      materials_cost: Math.round(base * 0.7 * 0.4),
      labour_cost: Math.round(base * 0.7 * 0.5),
      vat_amount: Math.round(base * 0.7 * 0.1),
      features: [
        { name: "Standard materials", included: true },
        { name: "12-month warranty", included: true },
        { name: "Basic inspection", included: true },
        { name: "Priority scheduling", included: false },
        { name: "Premium materials", included: false },
        { name: "Extended 24-month warranty", included: false },
        { name: "Annual maintenance check", included: false },
      ],
      is_recommended: false,
    },
    {
      id: "better",
      name: "Better",
      description: "Enhanced service with quality materials and extended coverage.",
      price: Math.round(base * 0.85),
      materials_cost: Math.round(base * 0.85 * 0.42),
      labour_cost: Math.round(base * 0.85 * 0.48),
      vat_amount: Math.round(base * 0.85 * 0.1),
      features: [
        { name: "Standard materials", included: true },
        { name: "12-month warranty", included: true },
        { name: "Basic inspection", included: true },
        { name: "Priority scheduling", included: true },
        { name: "Premium materials", included: true },
        { name: "Extended 24-month warranty", included: false },
        { name: "Annual maintenance check", included: false },
      ],
      is_recommended: true,
    },
    {
      id: "best",
      name: "Best",
      description: "Premium service with top-grade materials and comprehensive care.",
      price: base,
      materials_cost: Math.round(base * 0.42),
      labour_cost: Math.round(base * 0.48),
      vat_amount: Math.round(base * 0.1),
      features: [
        { name: "Standard materials", included: true },
        { name: "12-month warranty", included: true },
        { name: "Basic inspection", included: true },
        { name: "Priority scheduling", included: true },
        { name: "Premium materials", included: true },
        { name: "Extended 24-month warranty", included: true },
        { name: "Annual maintenance check", included: true },
      ],
      is_recommended: false,
    },
  ];
}

function ThankYouScreen({ quote, selectedTier }: { quote: QuoteData; selectedTier: QuoteTier }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-6">
      <Card className="max-w-lg w-full animate-slide-up">
        <CardContent className="py-12 px-8 text-center space-y-6">
          <div className="flex justify-center">
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-green-400 to-emerald-500 shadow-lg shadow-green-500/20">
              <CheckCircle2 className="h-10 w-10 text-white" />
            </div>
          </div>

          <div>
            <h1 className="text-3xl font-extrabold tracking-tight mb-2">Thank You!</h1>
            <p className="text-muted-foreground text-lg">
              You&apos;ve selected the <span className="text-foreground font-semibold">{selectedTier.name}</span> plan.
            </p>
          </div>

          <div className="rounded-xl bg-muted/50 p-4 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Quote</span>
              <span className="font-medium">{quote.quote_number}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Plan</span>
              <span className="font-medium">{selectedTier.name}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Total</span>
              <span className="font-bold gradient-text text-lg">{formatCurrency(selectedTier.price)}</span>
            </div>
          </div>

          <p className="text-sm text-muted-foreground">
            We&apos;ll be in touch shortly to confirm the details and schedule your appointment.
          </p>

          <div className="pt-2">
            <Heart className="h-5 w-5 text-primary mx-auto animate-pulse" />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function TierCard({
  tier,
  index,
  onSelect,
  disabled,
}: {
  tier: QuoteTier;
  index: number;
  onSelect: () => void;
  disabled: boolean;
}) {
  const config = tierConfig[tier.name];
  const Icon = config.icon;

  return (
    <div
      className={`relative flex flex-col rounded-2xl border ${config.border} bg-card/80 backdrop-blur-sm transition-all duration-300 hover:scale-[1.02] hover:shadow-2xl ${config.glow} ${
        tier.is_recommended ? "ring-2 ring-primary/50 shadow-lg" : ""
      }`}
      style={{ animationDelay: `${index * 150}ms` }}
    >
      {tier.is_recommended && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-10">
          <Badge className="bg-primary text-primary-foreground px-3 py-1 text-xs font-bold tracking-wide uppercase">
            Recommended
          </Badge>
        </div>
      )}

      <div className={`rounded-t-2xl bg-gradient-to-r ${config.gradient} p-6 text-center`}>
        <Icon className="h-8 w-8 mx-auto mb-2 text-white/90" />
        <h3 className="text-xl font-bold text-white">{tier.name}</h3>
        <p className="text-sm text-white/70 mt-1 max-w-[220px] mx-auto">{tier.description}</p>
      </div>

      <div className="flex-1 flex flex-col p-6">
        <div className="text-center mb-6">
          <div className="text-4xl font-extrabold tracking-tight gradient-text">
            {formatCurrency(tier.price)}
          </div>
          <p className="text-xs text-muted-foreground mt-1">inc. VAT</p>
        </div>

        <div className="space-y-1.5 mb-6 text-sm">
          <div className="flex justify-between text-muted-foreground">
            <span>Materials</span>
            <span className="text-foreground">{formatCurrency(tier.materials_cost)}</span>
          </div>
          <div className="flex justify-between text-muted-foreground">
            <span>Labour</span>
            <span className="text-foreground">{formatCurrency(tier.labour_cost)}</span>
          </div>
          <div className="flex justify-between text-muted-foreground">
            <span>VAT</span>
            <span className="text-foreground">{formatCurrency(tier.vat_amount)}</span>
          </div>
          <div className="border-t border-border/50 pt-1.5 flex justify-between font-semibold">
            <span>Total</span>
            <span className="gradient-text">{formatCurrency(tier.price)}</span>
          </div>
        </div>

        <div className="space-y-2.5 mb-6 flex-1">
          {tier.features.map((feature, i) => (
            <div key={i} className="flex items-center gap-2.5">
              {feature.included ? (
                <div className="flex h-5 w-5 items-center justify-center rounded-full bg-green-500/20 shrink-0">
                  <Check className="h-3 w-3 text-green-400" />
                </div>
              ) : (
                <div className="flex h-5 w-5 items-center justify-center rounded-full bg-white/5 shrink-0">
                  <X className="h-3 w-3 text-muted-foreground/50" />
                </div>
              )}
              <span
                className={`text-sm ${
                  feature.included ? "text-foreground" : "text-muted-foreground/50 line-through"
                }`}
              >
                {feature.name}
              </span>
            </div>
          ))}
        </div>

        <Button
          variant={config.buttonVariant}
          disabled={disabled}
          className={`w-full h-11 font-semibold ${
            tier.is_recommended
              ? "bg-gradient-to-r from-primary to-purple-500 hover:from-primary/90 hover:to-purple-500/90 text-white shadow-lg"
              : ""
          }`}
          onClick={onSelect}
        >
          Choose {tier.name}
        </Button>
      </div>
    </div>
  );
}

export default function PublicQuotePage() {
  const { id } = useParams<{ id: string }>();
  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTier, setSelectedTier] = useState<QuoteTier | null>(null);
  const [customerNotes, setCustomerNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [showDecline, setShowDecline] = useState(false);
  const [declined, setDeclined] = useState(false);

  useEffect(() => {
    if (!id) return;
    loadQuote();
  }, [id]);

  const loadQuote = async () => {
    try {
      const data: any = await api.quotes.get(id, "");
      setQuote(data);
      if (data.is_accepted) setAccepted(true);
    } catch (e: any) {
      setError(e.message || "Failed to load quote");
    } finally {
      setLoading(false);
    }
  };

  const handleAccept = async (tier: QuoteTier) => {
    setSelectedTier(tier);
    setSubmitting(true);
    try {
      await api.quotes.accept(id, "");
      setAccepted(true);
    } catch (e: any) {
      console.error(e);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDecline = async () => {
    setSubmitting(true);
    try {
      await api.quotes.accept(id, "");
      setDeclined(true);
    } catch (e: any) {
      console.error(e);
    } finally {
      setSubmitting(false);
    }
  };

  const tiers = quote?.tiers || (quote ? generateTiersFromFlatQuote(quote) : []);
  const quoteUrl = typeof window !== "undefined" ? window.location.href : "";

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error || !quote) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="max-w-md w-full">
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">{error || "Quote not found"}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (accepted && selectedTier) {
    return <ThankYouScreen quote={quote} selectedTier={selectedTier} />;
  }

  if (declined) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background px-6">
        <Card className="max-w-lg w-full animate-slide-up">
          <CardContent className="py-12 px-8 text-center space-y-4">
            <div className="flex justify-center">
              <div className="flex h-20 w-20 items-center justify-center rounded-full bg-muted">
                <X className="h-10 w-10 text-muted-foreground" />
              </div>
            </div>
            <h1 className="text-2xl font-bold">Quote Declined</h1>
            <p className="text-muted-foreground">
              No worries. If you have any questions or would like to discuss alternatives, please get in touch.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-center">
          <span className="text-xl font-bold gradient-text">VoiceField</span>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-10">
        <div className="text-center mb-10 animate-fade-in">
          <h1 className="text-4xl font-extrabold tracking-tight mb-2">
            {quote.title || "Your Quote"}
          </h1>
          <p className="text-muted-foreground text-lg">
            Hi <span className="text-foreground font-medium">{quote.customer_name}</span>, here are your options:
          </p>
          {quote.valid_until && (
            <p className="text-sm text-muted-foreground mt-2">
              This quote is valid until {formatDateTime(quote.valid_until)}
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8">
          {tiers.map((tier, i) => (
            <TierCard
              key={tier.id}
              tier={tier}
              index={i}
              disabled={submitting}
              onSelect={() => handleAccept(tier)}
            />
          ))}
        </div>

        <div className="mt-8 max-w-2xl mx-auto space-y-4 animate-fade-in">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <MessageSquare className="h-4 w-4" />
            <span>Add a note (optional)</span>
          </div>
          <Textarea
            placeholder="Any questions or special requirements? Let us know..."
            value={customerNotes}
            onChange={(e) => setCustomerNotes(e.target.value)}
            rows={3}
            className="bg-card/50"
          />
        </div>

        <div className="mt-6 text-center animate-fade-in">
          <Button
            variant="ghost"
            className="text-muted-foreground hover:text-destructive"
            disabled={submitting}
            onClick={() => setShowDecline(true)}
          >
            Decline this quote
          </Button>
        </div>

        <div className="mt-6 flex justify-center animate-fade-in">
          <div className="flex items-center gap-4 rounded-2xl border border-border/50 bg-card/50 px-5 py-4">
            {quoteUrl ? (
              <div className="rounded-lg bg-white p-2 shrink-0">
                <QRCodeSVG value={quoteUrl} size={96} />
              </div>
            ) : null}
            <div className="text-left">
              <p className="text-sm font-medium">Scan to open this quote</p>
              <p className="text-xs text-muted-foreground">
                Show this code to the customer to open this page on their phone.
              </p>
            </div>
          </div>
        </div>

        {showDecline && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <Card className="max-w-sm w-full mx-4 animate-slide-up">
              <CardContent className="p-6 space-y-4">
                <h3 className="text-lg font-semibold">Decline Quote?</h3>
                <p className="text-sm text-muted-foreground">
                  Are you sure you want to decline this quote? You can always request a new one later.
                </p>
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" size="sm" onClick={() => setShowDecline(false)}>
                    Keep Quote
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={submitting}
                    onClick={handleDecline}
                  >
                    {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "Yes, Decline"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </main>

      <footer className="border-t border-border/50 py-6 text-center text-xs text-muted-foreground">
        Powered by VoiceField — AI-Powered Field Service Management
      </footer>
    </div>
  );
}
