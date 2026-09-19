"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { formatCurrency, formatDateTime } from "@/lib/utils";
import {
  Check,
  X,
  Crown,
  Star,
  Shield,
  Loader2,
  Printer,
  Share2,
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

function TierCard({
  tier,
  index,
  isPublic,
  onSelect,
}: {
  tier: QuoteTier;
  index: number;
  isPublic?: boolean;
  onSelect?: () => void;
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

        {isPublic && onSelect && (
          <Button
            variant={config.buttonVariant}
            className={`w-full h-11 font-semibold ${
              tier.is_recommended
                ? "bg-gradient-to-r from-primary to-purple-500 hover:from-primary/90 hover:to-purple-500/90 text-white shadow-lg"
                : ""
            }`}
            onClick={onSelect}
          >
            Choose {tier.name}
          </Button>
        )}
      </div>
    </div>
  );
}

export default function QuotePresentPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const [quote, setQuote] = useState<QuoteData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !id) return;
    loadQuote();
  }, [id, token]);

  const loadQuote = async () => {
    try {
      const data: any = await api.quotes.get(id, token!);
      setQuote(data);
    } catch (e: any) {
      setError(e.message || "Failed to load quote");
    } finally {
      setLoading(false);
    }
  };

  const tiers = quote?.tiers || (quote ? generateTiersFromFlatQuote(quote) : []);

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

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold gradient-text">VoiceField</span>
            <span className="text-muted-foreground">|</span>
            <span className="text-sm text-muted-foreground">{quote.quote_number}</span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => window.print()}>
              <Printer className="h-4 w-4" />
              Print
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="gap-1.5"
              onClick={() => {
                navigator.clipboard.writeText(window.location.href);
              }}
            >
              <Share2 className="h-4 w-4" />
              Share
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-10">
        <div className="text-center mb-10 animate-fade-in">
          <h1 className="text-4xl font-extrabold tracking-tight mb-2">
            {quote.title || "Your Quote"}
          </h1>
          <p className="text-muted-foreground text-lg">
            Prepared for <span className="text-foreground font-medium">{quote.customer_name}</span>
          </p>
          {quote.valid_until && (
            <p className="text-sm text-muted-foreground mt-2">
              Valid until {formatDateTime(quote.valid_until)}
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8">
          {tiers.map((tier, i) => (
            <TierCard key={tier.id} tier={tier} index={i} isPublic={false} />
          ))}
        </div>

        {quote.notes && (
          <Card className="mt-10 animate-fade-in">
            <CardContent className="p-6">
              <h3 className="text-sm font-medium text-muted-foreground mb-2">Notes</h3>
              <p className="text-sm">{quote.notes}</p>
            </CardContent>
          </Card>
        )}
      </main>

      <footer className="border-t border-border/50 py-6 text-center text-xs text-muted-foreground">
        Powered by VoiceField — AI-Powered Field Service Management
      </footer>
    </div>
  );
}
