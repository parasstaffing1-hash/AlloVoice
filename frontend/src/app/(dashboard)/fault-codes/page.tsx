"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  Search, AlertTriangle, Wrench, Banknote, FileText, CheckCircle2, XCircle,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const BRANDS = ["Worcester", "Vaillant", "Ideal", "Baxi", "Viessmann"];

const dangerStyle: Record<string, string> = {
  safe: "bg-green-500/20 text-green-400",
  caution: "bg-yellow-500/20 text-yellow-400",
  gas_safe_only: "bg-red-500/20 text-red-400",
};
const dangerLabel: Record<string, string> = {
  safe: "Safe checks OK",
  caution: "Caution",
  gas_safe_only: "GAS SAFE ONLY",
};

export default function FaultCodesPage() {
  const { token } = useAuth();
  const [brand, setBrand] = useState("");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [quote, setQuote] = useState<any>(null);
  const [creating, setCreating] = useState(false);

  const search = async () => {
    if (!token || !code.trim()) return;
    setLoading(true); setError(""); setResult(null); setQuote(null);
    try {
      const res = await fetch(
        `${API}/api/fault-codes/lookup?code=${encodeURIComponent(code.trim())}&brand=${encodeURIComponent(brand)}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Lookup failed");
      setResult(data);
    } catch (e: any) {
      setError(e.message || "Lookup failed");
    } finally {
      setLoading(false);
    }
  };

  const buildQuote = async () => {
    if (!token || !result?.entry) return;
    setCreating(true);
    try {
      const res = await fetch(`${API}/api/fault-codes/to-quote`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ brand, code: code.trim() }),
      });
      const q = await res.json();
      if (!res.ok) throw new Error(q.detail || "Quote build failed");
      setQuote(q);
    } catch (e: any) {
      setError(e.message || "Quote build failed");
    } finally {
      setCreating(false);
    }
  };

  const createQuoteRecord = async () => {
    if (!token || !quote) return;
    try {
      await api.quotes.create({
        title: quote.title,
        items: quote.lines.map((l: any) => ({
          description: l.description, quantity: l.quantity, unit_price: l.unit_price,
        })),
      }, token);
      setError("");
      alert("Quote created — find it under Quotes.");
    } catch (e: any) {
      setError(e.message || "Could not create quote");
    }
  };

  const entry = result?.entry;

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div>
        <h1 className="text-3xl font-bold">Fault-Code Doctor</h1>
        <p className="text-muted-foreground">Type a boiler fault code. Get diagnosis, parts and a quote.</p>
      </div>

      <Card>
        <CardContent className="pt-6 space-y-4">
          <div className="flex gap-2 flex-wrap">
            {BRANDS.map((b) => (
              <Button
                key={b}
                variant={brand === b ? "default" : "outline"}
                size="lg"
                className="min-h-14 flex-1"
                onClick={() => setBrand(brand === b ? "" : b)}
              >
                {b}
              </Button>
            ))}
          </div>
          <div className="flex gap-2">
            <Input
              className="min-h-14 text-xl font-mono uppercase"
              placeholder="e.g. EA, F.22, E133"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && search()}
            />
            <Button size="lg" className="min-h-14 min-w-14" onClick={search} disabled={loading}>
              <Search className="h-6 w-6" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {loading && <p className="text-muted-foreground text-center">Diagnosing…</p>}
      {error && (
        <Card className="border-red-500/50">
          <CardContent className="py-4 flex items-center gap-2 text-red-400">
            <XCircle className="h-5 w-5" />{error}
          </CardContent>
        </Card>
      )}

      {entry && (
        <Card className="border-primary/30">
          <CardHeader>
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <CardTitle className="text-2xl">{entry.brand} {entry.code} — {entry.title}</CardTitle>
              <Badge className={dangerStyle[entry.danger_level] || dangerStyle.caution}>
                {entry.danger_level === "gas_safe_only" && <AlertTriangle className="h-3.5 w-3.5 mr-1" />}
                {dangerLabel[entry.danger_level] || entry.danger_level}
              </Badge>
            </div>
            <p className="text-muted-foreground">{entry.meaning}</p>
          </CardHeader>
          <CardContent className="space-y-5">
            <div>
              <h3 className="font-semibold mb-2 flex items-center gap-2"><Wrench className="h-4 w-4" />Likely causes</h3>
              <ul className="space-y-1.5">
                {(entry.likely_causes || []).map((c: string, i: number) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <CheckCircle2 className="h-4 w-4 mt-0.5 text-primary shrink-0" />{c}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="font-semibold mb-2">Safe checks</h3>
              <ul className="space-y-1.5">
                {(entry.safe_checks || []).map((c: string, i: number) => (
                  <li key={i} className="text-sm text-muted-foreground">• {c}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="font-semibold mb-2 flex items-center gap-2"><Banknote className="h-4 w-4" />Likely parts</h3>
              <div className="space-y-1.5">
                {(entry.parts || []).map((p: any, i: number) => (
                  <div key={i} className="flex justify-between text-sm py-1.5 border-b last:border-0">
                    <span>{p.name}</span>
                    <span className="font-medium">£{Number(p.typical_price_gbp).toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
            {entry.related_quote_hint && (
              <p className="text-sm bg-primary/5 border border-primary/20 rounded-lg p-3">
                <FileText className="h-4 w-4 inline mr-1" />{entry.related_quote_hint}
              </p>
            )}
            <Button size="lg" className="w-full min-h-14 text-base" onClick={buildQuote} disabled={creating}>
              {creating ? "Building…" : "Build quote from this fault"}
            </Button>
          </CardContent>
        </Card>
      )}

      {result?.match_type === "suggestions" && (
        <Card>
          <CardHeader><CardTitle className="text-lg">Did you mean…</CardTitle></CardHeader>
          <CardContent className="flex gap-2 flex-wrap">
            {(result.suggestions || []).map((s: any) => (
              <Button key={`${s.brand}-${s.code}`} variant="outline" size="lg" className="min-h-12"
                onClick={() => { setBrand(s.brand); setCode(s.code); }}>
                {s.brand} {s.code}
              </Button>
            ))}
            {(!result.suggestions || result.suggestions.length === 0) && (
              <p className="text-sm text-muted-foreground">No close matches — check the code and brand.</p>
            )}
          </CardContent>
        </Card>
      )}

      {quote && (
        <Card className="border-green-500/40">
          <CardHeader><CardTitle>Draft quote — £{quote.total.toFixed(2)} inc. VAT</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {quote.lines.map((l: any, i: number) => (
              <div key={i} className="flex justify-between text-sm">
                <span>{l.description} × {l.quantity}</span>
                <span>£{(l.quantity * l.unit_price).toFixed(2)}</span>
              </div>
            ))}
            <div className="flex justify-between text-sm text-muted-foreground pt-1">
              <span>Subtotal</span><span>£{quote.subtotal.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>VAT 20%</span><span>£{quote.vat.toFixed(2)}</span>
            </div>
            <Button size="lg" className="w-full min-h-14 mt-2" onClick={createQuoteRecord}>
              Create this quote
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
