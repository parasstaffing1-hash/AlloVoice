"use client";

import { useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/store";
import { formatCurrency } from "@/lib/utils";
import {
  Sparkles,
  Clock,
  Pound,
  Plus,
  Check,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Lightbulb,
} from "lucide-react";

interface LineItem {
  description: string;
  quantity: number;
  unit_price: number;
  total: number;
  type: "material" | "labour" | "other";
}

interface GeneratedQuote {
  job_type: string;
  estimated_duration_minutes: number;
  line_items: LineItem[];
  subtotal: number;
  vat: number;
  total: number;
  confidence: number;
  suggested_services: string[];
}

interface UpsellSuggestion {
  title: string;
  description: string;
  price: number;
  reason: string;
  priority: "high" | "medium" | "low";
}

interface AiQuoteBuilderProps {
  onUseQuote?: (quote: GeneratedQuote) => void;
  propertyType?: "domestic" | "commercial";
  propertyAge?: string;
  hasGas?: boolean;
  hasElectric?: boolean;
}

const JOB_TYPE_LABELS: Record<string, string> = {
  boiler_repair: "Boiler Repair",
  boiler_service: "Boiler Service",
  boiler_install: "Boiler Installation",
  leak_repair: "Leak Repair",
  radiator_repair: "Radiator Repair",
  radiator_install: "Radiator Installation",
  electrical_repair: "Electrical Repair",
  gas_safety: "Gas Safety Check",
  drain_unblock: "Drain Unblocking",
  bathroom_refit: "Bathroom Refit",
  kitchen_refit: "Kitchen Refit",
  roofing_repair: "Roofing Repair",
  window_repair: "Window Repair",
  door_repair: "Door Repair",
  plastering: "Plastering",
  painting: "Painting & Decorating",
  carpentry: "Carpentry",
  appliance_repair: "Appliance Repair",
  general_repair: "General Repair",
};

const CONFIDENCE_COLORS: Record<number, string> = {
  0: "bg-red-500/20 text-red-400",
  1: "bg-yellow-500/20 text-yellow-400",
  2: "bg-green-500/20 text-green-400",
};

function getConfidenceBadge(confidence: number) {
  if (confidence >= 0.8) return { label: "High confidence", colorClass: "bg-emerald-500/20 text-emerald-400" };
  if (confidence >= 0.5) return { label: "Medium confidence", colorClass: "bg-yellow-500/20 text-yellow-400" };
  return { label: "Low confidence", colorClass: "bg-orange-500/20 text-orange-400" };
}

export default function AiQuoteBuilder({
  onUseQuote,
  propertyType = "domestic",
  propertyAge,
  hasGas,
  hasElectric,
}: AiQuoteBuilderProps) {
  const { token } = useAuth();
  const [description, setDescription] = useState("");
  const [urgency, setUrgency] = useState<"standard" | "urgent" | "emergency">("standard");
  const [quote, setQuote] = useState<GeneratedQuote | null>(null);
  const [upsells, setUpsells] = useState<UpsellSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingUpsells, setLoadingUpsells] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showLineItems, setShowLineItems] = useState(true);

  const generateQuote = useCallback(async () => {
    if (!description.trim() || !token) return;

    setLoading(true);
    setError(null);
    setQuote(null);
    setUpsells([]);

    try {
      const result: GeneratedQuote = await api.aiQuote.generate(
        {
          description: description.trim(),
          property_type: propertyType,
          urgency,
          property_details: {
            property_age: propertyAge,
            has_gas: hasGas,
            has_electric: hasElectric,
          },
        },
        token
      );
      setQuote(result);

      setLoadingUpsells(true);
      try {
        const upsellResult: UpsellResponse = await api.aiQuote.upsell(
          { job_type: result.job_type, customer_history: false, property_age: propertyAge || "" },
          token
        );
        setUpsells(upsellResult.suggestions);
      } catch {
        // upsells are non-critical
      } finally {
        setLoadingUpsells(false);
      }
    } catch (e: any) {
      setError(e.message || "Failed to generate quote");
    } finally {
      setLoading(false);
    }
  }, [description, urgency, propertyType, propertyAge, hasGas, hasElectric, token]);

  const handleUseQuote = () => {
    if (quote && onUseQuote) {
      onUseQuote(quote);
    }
  };

  const priorityBadge = (priority: string) => {
    const map: Record<string, string> = {
      high: "bg-emerald-500/20 text-emerald-400",
      medium: "bg-blue-500/20 text-blue-400",
      low: "bg-gray-500/20 text-gray-400",
    };
    return map[priority] || map.medium;
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Sparkles className="h-5 w-5 text-primary" />
            AI Quote Builder
          </CardTitle>
          <CardDescription>
            Describe the job in plain English and get an instant AI-generated quote
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            placeholder="Describe the job in plain English... e.g. 'Broken boiler, no heating, it's an emergency'"
            className="min-h-[100px] text-sm"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={loading}
          />

          <div className="flex flex-wrap gap-2">
            <span className="text-xs text-muted-foreground mr-1 self-center">Urgency:</span>
            {(["standard", "urgent", "emergency"] as const).map((u) => (
              <Button
                key={u}
                variant={urgency === u ? "default" : "outline"}
                size="sm"
                onClick={() => setUrgency(u)}
                disabled={loading}
                className="text-xs"
              >
                {u.charAt(0).toUpperCase() + u.slice(1)}
              </Button>
            ))}
          </div>

          <Button
            onClick={generateQuote}
            disabled={!description.trim() || loading}
            className="w-full gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating quote...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                Generate Quote
              </>
            )}
          </Button>

          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}
        </CardContent>
      </Card>

      {quote && (
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-lg">
                  {JOB_TYPE_LABELS[quote.job_type] || quote.job_type}
                </CardTitle>
                <div className="flex items-center gap-2 mt-1">
                  <Badge variant="secondary" className={getConfidenceBadge(quote.confidence).colorClass}>
                    {getConfidenceBadge(quote.confidence).label}
                  </Badge>
                  <Badge variant="secondary" className="bg-primary/10 text-primary">
                    {urgency.charAt(0).toUpperCase() + urgency.slice(1)}
                  </Badge>
                </div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-primary">{formatCurrency(quote.total)}</div>
                <div className="text-xs text-muted-foreground">inc. VAT</div>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" />
              Estimated duration: {Math.floor(quote.estimated_duration_minutes / 60)}h{" "}
              {quote.estimated_duration_minutes % 60 > 0
                ? `${quote.estimated_duration_minutes % 60}m`
                : ""}
            </div>

            <div>
              <button
                onClick={() => setShowLineItems(!showLineItems)}
                className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                {showLineItems ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
                Line Items ({quote.line_items.length})
              </button>

              {showLineItems && (
                <div className="mt-2 rounded-lg border overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-muted/50">
                        <th className="px-3 py-2 text-left font-medium">Item</th>
                        <th className="px-3 py-2 text-center font-medium">Qty</th>
                        <th className="px-3 py-2 text-right font-medium">Unit Price</th>
                        <th className="px-3 py-2 text-right font-medium">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {quote.line_items.map((item, idx) => (
                        <tr key={idx} className="border-b last:border-0">
                          <td className="px-3 py-2">
                            <div className="flex items-center gap-2">
                              <Badge
                                variant="secondary"
                                className={
                                  item.type === "labour"
                                    ? "bg-blue-500/20 text-blue-400 text-[10px]"
                                    : "bg-emerald-500/20 text-emerald-400 text-[10px]"
                                }
                              >
                                {item.type}
                              </Badge>
                              {item.description}
                            </div>
                          </td>
                          <td className="px-3 py-2 text-center">{item.quantity}</td>
                          <td className="px-3 py-2 text-right">{formatCurrency(item.unit_price)}</td>
                          <td className="px-3 py-2 text-right font-medium">{formatCurrency(item.total)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="rounded-lg border bg-muted/30 p-3 space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Subtotal</span>
                <span>{formatCurrency(quote.subtotal)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">VAT (20%)</span>
                <span>{formatCurrency(quote.vat)}</span>
              </div>
              <div className="flex justify-between border-t pt-1 font-semibold text-base">
                <span>Total</span>
                <span className="text-primary">{formatCurrency(quote.total)}</span>
              </div>
            </div>

            {onUseQuote && (
              <Button onClick={handleUseQuote} className="w-full gap-2">
                <Check className="h-4 w-4" />
                Use This Quote
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {quote && upsells.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Lightbulb className="h-5 w-5 text-yellow-400" />
              Smart Upsell Suggestions
            </CardTitle>
            <CardDescription>Recommended services to increase job value</CardDescription>
          </CardHeader>
          <CardContent>
            {loadingUpsells ? (
              <div className="flex items-center justify-center py-6 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Loading suggestions...
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {upsells.map((s, idx) => (
                  <div
                    key={idx}
                    className="rounded-lg border p-3 hover:border-primary/30 transition-all cursor-pointer group"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="space-y-1 flex-1">
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-medium">{s.title}</h4>
                          <Badge variant="secondary" className={`text-[10px] ${priorityBadge(s.priority)}`}>
                            {s.priority}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">{s.description}</p>
                        <p className="text-[11px] text-muted-foreground italic">{s.reason}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-sm font-semibold text-primary">{formatCurrency(s.price)}</div>
                        <Plus className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity mt-1 ml-auto" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
