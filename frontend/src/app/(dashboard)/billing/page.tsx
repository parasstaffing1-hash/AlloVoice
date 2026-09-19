"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { CreditCard, Check, Crown, AlertTriangle } from "lucide-react";

interface Plan {
  id: string;
  name: string;
  monthly_gbp: number;
  yearly_gbp: number;
  seats_included: number;
  most_popular?: boolean;
  features: string[];
  stripe_price_id_monthly?: string | null;
}

interface Subscription {
  status: string;
  plan_id: string | null;
  seats: number;
  billing_cycle?: string;
  current_period_end: string | null;
  trial_ends: string | null;
}

function BillingContent() {
  const { token } = useAuth();
  const searchParams = useSearchParams();
  const success = searchParams.get("success") === "1";
  const cancelled = searchParams.get("cancelled") === "1";

  const [plans, setPlans] = useState<Plan[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [yearly, setYearly] = useState(false);
  const [seats, setSeats] = useState(1);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    const load = async () => {
      setLoading(true);
      try {
        const [plansRes, subRes] = await Promise.all([
          api.billing.plans(token) as Promise<{ plans: Plan[] }>,
          api.billing.subscription(token) as Promise<Subscription>,
        ]);
        setPlans(plansRes.plans || []);
        setSubscription(subRes);
      } catch (e: any) {
        setNotice(e?.message || "Failed to load billing info");
      }
      setLoading(false);
    };
    load();
  }, [token]);

  const trialDaysLeft = () => {
    if (!subscription?.trial_ends) return null;
    const diff = Math.ceil(
      (new Date(subscription.trial_ends).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    );
    return diff > 0 ? diff : 0;
  };

  const handleCheckout = async (planId: string) => {
    if (!token) return;
    setBusy(planId);
    setNotice(null);
    try {
      const res = (await api.billing.checkout(
        { plan_id: planId, billing_cycle: yearly ? "yearly" : "monthly", seats },
        token
      )) as { checkout_url?: string | null; mode?: string; message?: string };
      if (res.checkout_url) {
        window.location.href = res.checkout_url;
      } else {
        setNotice(res.message || "Stripe is not configured — your request was recorded for manual activation.");
      }
    } catch (e: any) {
      setNotice(e?.message || "Checkout failed");
    }
    setBusy(null);
  };

  const handleManage = async () => {
    if (!token) return;
    setBusy("portal");
    setNotice(null);
    try {
      const res = (await api.billing.portal(token)) as {
        portal_url?: string | null;
        mode?: string;
        message?: string;
      };
      if (res.portal_url) {
        window.location.href = res.portal_url;
      } else {
        setNotice(res.message || "Billing portal unavailable — contact support.");
      }
    } catch (e: any) {
      setNotice(e?.message || "Portal unavailable");
    }
    setBusy(null);
  };

  const statusVariant = (s?: string) =>
    s === "active" ? "default" : s === "trialing" ? "secondary" : s === "past_due" ? "destructive" : "outline";

  const priceFor = (p: Plan) => (yearly ? p.yearly_gbp : p.monthly_gbp);

  if (loading) return <div className="p-6">Loading billing…</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <CreditCard className="h-7 w-7" /> Billing
        </h1>
        <Button variant="outline" onClick={handleManage} disabled={busy === "portal"}>
          Manage subscription
        </Button>
      </div>

      {success && (
        <Card className="border-green-500">
          <CardContent className="p-4 flex items-center gap-2">
            <Check className="h-5 w-5 text-green-600" />
            <span>Payment successful — your subscription is activating.</span>
          </CardContent>
        </Card>
      )}
      {cancelled && (
        <Card className="border-yellow-500">
          <CardContent className="p-4 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-yellow-600" />
            <span>Checkout was cancelled — no charge was made.</span>
          </CardContent>
        </Card>
      )}
      {notice && (
        <Card className="border-blue-500">
          <CardContent className="p-4 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            <span>{notice}</span>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Current subscription
            {subscription && <Badge variant={statusVariant(subscription.status)}>{subscription.status}</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-6 items-center">
          <div>
            <div className="text-sm text-muted-foreground">Plan</div>
            <div className="font-semibold">{subscription?.plan_id || "— (trial)"}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Seats</div>
            <div className="font-semibold">{subscription?.seats ?? 1}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Period end</div>
            <div className="font-semibold">{subscription?.current_period_end || "—"}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Trial</div>
            <div className="font-semibold">
              {trialDaysLeft() !== null ? `${trialDaysLeft()} days left` : "—"}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <span className={!yearly ? "font-semibold" : "text-muted-foreground"}>Monthly</span>
        <Button variant="outline" size="sm" onClick={() => setYearly(!yearly)}>
          {yearly ? "Switch to monthly" : "Switch to yearly (2 months free)"}
        </Button>
        <span className={yearly ? "font-semibold" : "text-muted-foreground"}>Yearly</span>
        <label className="ml-4 text-sm flex items-center gap-2">
          Seats:
          <input
            type="number"
            min={1}
            max={1000}
            value={seats}
            onChange={(e) => setSeats(Math.max(1, parseInt(e.target.value || "1", 10)))}
            className="w-20 border rounded px-2 py-1"
          />
        </label>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {plans.map((p) => (
          <Card key={p.id} className={p.most_popular ? "border-primary" : ""}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {p.id === "growth" && <Crown className="h-5 w-5" />}
                {p.name}
                {p.most_popular && <Badge>Most popular</Badge>}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-3xl font-bold">
                £{priceFor(p)}
                <span className="text-sm font-normal text-muted-foreground">
                  {" "}/ user / {yearly ? "yr" : "mo"}
                </span>
              </div>
              <div className="text-sm text-muted-foreground">
                {p.seats_included} seat{p.seats_included === 1 ? "" : "s"} included, then per-seat
              </div>
              <ul className="space-y-1 text-sm">
                {p.features.map((f) => (
                  <li key={f} className="flex items-start gap-2">
                    <Check className="h-4 w-4 mt-0.5 text-green-600" /> {f}
                  </li>
                ))}
              </ul>
              <Button
                className="w-full"
                variant={p.most_popular ? "default" : "outline"}
                disabled={busy === p.id}
                onClick={() => handleCheckout(p.id)}
              >
                {busy === p.id ? "Redirecting…" : `Choose ${p.name}`}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default function BillingPage() {
  return (
    <Suspense fallback={<div className="p-6">Loading billing…</div>}>
      <BillingContent />
    </Suspense>
  );
}
