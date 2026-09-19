"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import AiQuoteBuilder from "@/components/ai-quote-builder";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/store";
import { formatCurrency } from "@/lib/utils";
import {
  Sparkles,
  PenLine,
  ArrowLeft,
  Loader2,
  Check,
  Briefcase,
} from "lucide-react";

interface GeneratedQuote {
  job_type: string;
  estimated_duration_minutes: number;
  line_items: Array<{
    description: string;
    quantity: number;
    unit_price: number;
    total: number;
    type: string;
  }>;
  subtotal: number;
  vat: number;
  total: number;
  confidence: number;
  suggested_services: string[];
}

export default function NewJobPage() {
  const router = useRouter();
  const { token, user } = useAuth();
  const [mode, setMode] = useState<"ai" | "manual" | null>(null);
  const [customers, setCustomers] = useState<any[]>([]);
  const [properties, setProperties] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    title: "",
    description: "",
    customer_id: "",
    property_id: "",
    priority: "normal",
    scheduled_at: "",
  });

  const [aiQuote, setAiQuote] = useState<GeneratedQuote | null>(null);
  const [aiDescription, setAiDescription] = useState("");
  const [aiPropertyType, setAiPropertyType] = useState<"domestic" | "commercial">("domestic");

  useEffect(() => {
    if (!token) return;
    loadCustomers();
  }, [token]);

  useEffect(() => {
    if (form.customer_id && token) {
      loadProperties(form.customer_id);
    } else {
      setProperties([]);
      setForm((f) => ({ ...f, property_id: "" }));
    }
  }, [form.customer_id, token]);

  const loadCustomers = async () => {
    try {
      const data: any = await api.customers.list(token!);
      setCustomers(data);
    } catch (e) {
      console.error(e);
    }
  };

  const loadProperties = async (customerId: string) => {
    try {
      const data: any = await api.customers.properties(customerId, token!);
      setProperties(data);
    } catch (e) {
      console.error(e);
    }
  };

  const handleUseAiQuote = (quote: GeneratedQuote) => {
    setAiQuote(quote);
    setForm((f) => ({
      ...f,
      title: `${quote.job_type.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}`,
      description: aiDescription,
    }));
  };

  const handleSubmit = async () => {
    if (!token || !form.title.trim()) return;

    setSubmitting(true);
    setError(null);

    try {
      const jobData: any = {
        title: form.title,
        description: form.description || aiDescription,
        priority: form.priority,
      };

      if (form.customer_id) jobData.customer_id = form.customer_id;
      if (form.property_id) jobData.property_id = form.property_id;
      if (form.scheduled_at) jobData.scheduled_at = new Date(form.scheduled_at).toISOString();
      if (aiQuote) jobData.estimated_cost = aiQuote.total;

      await api.jobs.create(jobData, token);

      if (aiQuote) {
        try {
          const customer = customers.find((c) => c.id === form.customer_id);
          if (customer) {
            await api.quotes.create(
              {
                job_id: "", // will be set by backend after job creation
                customer_id: form.customer_id,
                title: form.title,
                subtotal: aiQuote.subtotal,
                tax_rate: 20,
                tax_amount: aiQuote.vat,
                total: aiQuote.total,
                notes: `AI-generated quote for ${aiQuote.job_type.replace(/_/g, " ")}`,
                valid_days: 30,
                items: aiQuote.line_items.map((item, idx) => ({
                  description: item.description,
                  quantity: item.quantity,
                  unit_price: item.unit_price,
                })),
              },
              token
            );
          }
        } catch {
          // quote creation is best-effort
        }
      }

      router.push("/jobs");
    } catch (e: any) {
      setError(e.message || "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  };

  if (mode === null) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => router.back()}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">New Job</h1>
            <p className="text-muted-foreground">Choose how you'd like to create this job</p>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Card
            className="hover:border-primary/50 transition-all cursor-pointer group"
            onClick={() => setMode("ai")}
          >
            <CardContent className="p-6 text-center space-y-3">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-xl bg-primary/10 group-hover:bg-primary/20 transition-colors">
                <Sparkles className="h-7 w-7 text-primary" />
              </div>
              <div>
                <h3 className="font-semibold text-lg">Describe the job</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Use AI to generate a quote from a plain English description
                </p>
              </div>
              <Badge variant="secondary" className="bg-primary/10 text-primary">
                AI-Powered
              </Badge>
            </CardContent>
          </Card>

          <Card
            className="hover:border-primary/50 transition-all cursor-pointer group"
            onClick={() => setMode("manual")}
          >
            <CardContent className="p-6 text-center space-y-3">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-xl bg-secondary/50 group-hover:bg-secondary transition-colors">
                <PenLine className="h-7 w-7 text-muted-foreground" />
              </div>
              <div>
                <h3 className="font-semibold text-lg">Manual entry</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Fill in the job details yourself with full control
                </p>
              </div>
              <Badge variant="secondary">Traditional</Badge>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => setMode(null)}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1">
          <h1 className="text-3xl font-bold">
            {mode === "ai" ? "AI Job Creator" : "New Job"}
          </h1>
          <p className="text-muted-foreground">
            {mode === "ai"
              ? "Describe the job and let AI build the quote"
              : "Fill in the job details manually"}
          </p>
        </div>
        {mode === "ai" && (
          <Button variant="outline" size="sm" onClick={() => setMode("manual")}>
            <PenLine className="h-4 w-4 mr-1" />
            Switch to Manual
          </Button>
        )}
      </div>

      {mode === "ai" && (
        <AiQuoteBuilder
          onUseQuote={handleUseAiQuote}
          propertyType={aiPropertyType}
        />
      )}

      {mode === "manual" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Briefcase className="h-5 w-5 text-primary" />
              Job Details
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Job Title *</label>
              <Input
                placeholder="e.g. Boiler repair, Gas safety check"
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Description</label>
              <Textarea
                placeholder="Describe the job in detail..."
                className="min-h-[80px]"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              />
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Assignment & Scheduling</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium">Customer</label>
              <select
                className="flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={form.customer_id}
                onChange={(e) => setForm((f) => ({ ...f, customer_id: e.target.value }))}
              >
                <option value="">Select customer...</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.full_name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Property</label>
              <select
                className="flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                value={form.property_id}
                onChange={(e) => setForm((f) => ({ ...f, property_id: e.target.value }))}
                disabled={!form.customer_id}
              >
                <option value="">Select property...</option>
                {properties.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.address_line1 || p.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium">Priority</label>
              <select
                className="flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={form.priority}
                onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}
              >
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Scheduled Date</label>
              <Input
                type="datetime-local"
                value={form.scheduled_at}
                onChange={(e) => setForm((f) => ({ ...f, scheduled_at: e.target.value }))}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {mode === "ai" && aiQuote && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Generated Quote Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Job Type</span>
              <Badge variant="secondary">
                {aiQuote.job_type.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Estimated Duration</span>
              <span className="text-sm">
                {Math.floor(aiQuote.estimated_duration_minutes / 60)}h{" "}
                {aiQuote.estimated_duration_minutes % 60 > 0
                  ? `${aiQuote.estimated_duration_minutes % 60}m`
                  : ""}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Confidence</span>
              <Badge
                variant="secondary"
                className={
                  aiQuote.confidence >= 0.8
                    ? "bg-emerald-500/20 text-emerald-400"
                    : aiQuote.confidence >= 0.5
                    ? "bg-yellow-500/20 text-yellow-400"
                    : "bg-orange-500/20 text-orange-400"
                }
              >
                {Math.round(aiQuote.confidence * 100)}%
              </Badge>
            </div>
            <div className="flex items-center justify-between border-t pt-3">
              <span className="font-medium">Estimated Total</span>
              <span className="text-lg font-bold text-primary">{formatCurrency(aiQuote.total)}</span>
            </div>
          </CardContent>
        </Card>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={() => router.back()}>
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={!form.title.trim() || submitting}
          className="gap-2 min-w-[140px]"
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Creating...
            </>
          ) : (
            <>
              <Check className="h-4 w-4" />
              Create Job
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
