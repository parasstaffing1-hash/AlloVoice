"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Crown, Star, Shield, Check, Users, Calendar, ArrowRight,
} from "lucide-react";
import { api } from "@/lib/api";

const FALLBACK_PLANS = [
  {
    id: "basic",
    name: "Basic",
    icon: Shield,
    price_monthly: 29.99,
    price_yearly: 299.99,
    description: "Essential maintenance coverage for homeowners",
    color: "text-blue-500",
    bgColor: "bg-blue-500/10",
    borderColor: "border-blue-500/20",
    features: [
      { text: "Annual boiler service", included: true },
      { text: "Priority booking", included: true },
      { text: "10% discount on repairs", included: true },
      { text: "1 emergency call/year", included: true },
      { text: "Gas safety check", included: false },
      { text: "Boiler replacement guarantee", included: false },
    ],
  },
  {
    id: "standard",
    name: "Standard",
    icon: Star,
    price_monthly: 59.99,
    price_yearly: 599.99,
    description: "Comprehensive coverage for families",
    color: "text-amber-500",
    bgColor: "bg-amber-500/10",
    borderColor: "border-amber-500/20",
    popular: true,
    features: [
      { text: "Bi-annual boiler service", included: true },
      { text: "Priority booking", included: true },
      { text: "15% discount on repairs", included: true },
      { text: "3 emergency calls/year", included: true },
      { text: "Free annual gas safety check", included: true },
      { text: "Boiler replacement guarantee", included: false },
    ],
  },
  {
    id: "premium",
    name: "Premium",
    icon: Crown,
    price_monthly: 99.99,
    price_yearly: 999.99,
    description: "Complete peace of mind with unlimited support",
    color: "text-purple-500",
    bgColor: "bg-purple-500/10",
    borderColor: "border-purple-500/20",
    features: [
      { text: "Quarterly boiler service", included: true },
      { text: "VIP priority booking", included: true },
      { text: "25% discount on repairs", included: true },
      { text: "Unlimited emergency calls", included: true },
      { text: "Free annual gas safety check", included: true },
      { text: "Free boiler replacement after 10 years", included: true },
    ],
  },
];

export default function PublicMembershipsPage() {
  const [billingCycle, setBillingCycle] = useState<"monthly" | "yearly">("monthly");
  const [enrolling, setEnrolling] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [plans, setPlans] = useState<any[]>(FALLBACK_PLANS);
  const [plansLive, setPlansLive] = useState(false);
  const [plansLoading, setPlansLoading] = useState(true);
  const [formData, setFormData] = useState({
    full_name: "",
    email: "",
    phone: "",
    address: "",
  });
  const [submitted, setSubmitted] = useState(false);

  const handleJoin = (planId: string) => {
    setEnrolling(planId);
    setShowForm(true);
  };

  // Live plans: GET /api/billing/plans (public) → { plans: [{ id, name,
  // monthly_gbp, yearly_gbp, features: string[], most_popular }] }.
  // Falls back to the hardcoded demo tiers when the backend is unreachable.
  useEffect(() => {
    api.billing
      .plans()
      .then((r: any) => {
        const raw = Array.isArray((r as any)?.plans)
          ? (r as any).plans
          : Array.isArray(r)
            ? r
            : [];
        if (raw.length === 0) {
          setPlansLive(false);
          return;
        }
        const icons = [Shield, Star, Crown];
        const styles = [
          { color: "text-blue-500", bgColor: "bg-blue-500/10", borderColor: "border-blue-500/20" },
          { color: "text-amber-500", bgColor: "bg-amber-500/10", borderColor: "border-amber-500/20" },
          { color: "text-purple-500", bgColor: "bg-purple-500/10", borderColor: "border-purple-500/20" },
        ];
        const mapped = raw.map((p: any, i: number) => {
          const style = styles[i % styles.length];
          const feats = Array.isArray(p?.features) ? p.features : [];
          return {
            id: String(p?.id ?? `plan-${i}`),
            name: String(p?.name ?? `Plan ${i + 1}`),
            icon: icons[i % icons.length],
            price_monthly: Number(p?.monthly_gbp ?? p?.price_monthly ?? 0),
            price_yearly: Number(p?.yearly_gbp ?? p?.price_yearly ?? 0),
            description: String(p?.description ?? ""),
            ...style,
            popular: Boolean(p?.most_popular ?? p?.popular ?? false),
            features: feats.map((f: any) => ({
              text: typeof f === "string" ? f : String(f?.text ?? f),
              included: typeof f === "string" ? true : Boolean(f?.included ?? true),
            })),
          };
        });
        setPlans(mapped);
        setPlansLive(true);
      })
      .catch(() => setPlansLive(false))
      .finally(() => setPlansLoading(false));
  }, []);

  // NOTE (honest enrollment): api.memberships.enroll(data, token) requires
  // { customer_id: UUID, plan_id, billing_cycle } + a signed-in business token,
  // so this public name/email/phone form cannot complete it directly. We keep
  // the modal as a contact request and never fake an "active membership".
  const handleSubmit = () => {
    setSubmitted(true);
    setShowForm(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-background to-muted/30">
      <div className="max-w-6xl mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <Badge variant="secondary" className="mb-4 gap-1">
            <Users className="h-3 w-3" /> Membership Plans
          </Badge>
          <h1 className="text-4xl font-bold mb-4">
            Protect Your Home with a <span className="text-primary">Allo</span> Plan
          </h1>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            Join thousands of homeowners who trust Allo for reliable, ongoing property maintenance.
            Save money and never miss essential servicing.
          </p>
          <p className="text-xs text-muted-foreground mt-3">
            {plansLoading
              ? "Loading live plans…"
              : plansLive
                ? "Live plans from the API."
                : "Demo plans shown — backend unreachable, connect the API for live pricing."}
          </p>

          <div className="flex items-center justify-center gap-2 mt-8">
            <Button
              variant={billingCycle === "monthly" ? "default" : "outline"}
              size="sm"
              onClick={() => setBillingCycle("monthly")}
            >
              Monthly
            </Button>
            <Button
              variant={billingCycle === "yearly" ? "default" : "outline"}
              size="sm"
              onClick={() => setBillingCycle("yearly")}
            >
              Yearly
              <Badge variant="secondary" className="ml-2 text-green-500">Save 17%</Badge>
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {plans.map((plan) => {
            const Icon = plan.icon;
            const price = billingCycle === "monthly" ? plan.price_monthly : plan.price_yearly;
            const period = billingCycle === "monthly" ? "/mo" : "/yr";

            return (
              <Card
                key={plan.id}
                className={`relative ${plan.popular ? `border-2 ${plan.borderColor}` : ""}`}
              >
                {plan.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <Badge className="bg-amber-500 text-white px-3">Most Popular</Badge>
                  </div>
                )}
                <CardHeader className="text-center pt-8">
                  <div className={`mx-auto p-3 ${plan.bgColor} rounded-xl w-fit mb-4`}>
                    <Icon className={`h-8 w-8 ${plan.color}`} />
                  </div>
                  <CardTitle className="text-xl">{plan.name}</CardTitle>
                  <p className="text-sm text-muted-foreground">{plan.description}</p>
                  <div className="mt-4">
                    <span className="text-4xl font-bold">£{price.toFixed(2)}</span>
                    <span className="text-muted-foreground">{period}</span>
                  </div>
                  {billingCycle === "yearly" && (
                    <p className="text-xs text-green-500">
                      Save £{((plan.price_monthly * 12) - plan.price_yearly).toFixed(2)} per year
                    </p>
                  )}
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-3">
                    {plan.features.map((f: any, i: number) => (
                      <div key={i} className="flex items-center gap-2">
                        <Check
                          className={`h-4 w-4 flex-shrink-0 ${
                            f.included ? "text-green-500" : "text-muted-foreground/30"
                          }`}
                        />
                        <span className={`text-sm ${f.included ? "" : "text-muted-foreground/50 line-through"}`}>
                          {f.text}
                        </span>
                      </div>
                    ))}
                  </div>
                  <Button
                    className={`w-full ${plan.popular ? "" : "variant-outline"}`}
                    variant={plan.popular ? "default" : "outline"}
                    onClick={() => handleJoin(plan.id)}
                  >
                    Join Now <ArrowRight className="h-4 w-4 ml-1" />
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>

        <div className="mt-16 text-center">
          <h2 className="text-2xl font-bold mb-4">Why Join an Allo Membership?</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8 max-w-4xl mx-auto">
            <div className="text-center">
              <div className="p-3 bg-green-500/10 rounded-xl w-fit mx-auto mb-3">
                <Calendar className="h-6 w-6 text-green-500" />
              </div>
              <h3 className="font-medium mb-1">Never Miss a Service</h3>
              <p className="text-sm text-muted-foreground">
                Automated scheduling ensures your property is always maintained on time.
              </p>
            </div>
            <div className="text-center">
              <div className="p-3 bg-blue-500/10 rounded-xl w-fit mx-auto mb-3">
                <Shield className="h-6 w-6 text-blue-500" />
              </div>
              <h3 className="font-medium mb-1">Priority Support</h3>
              <p className="text-sm text-muted-foreground">
                Members get priority booking and faster response times for all service calls.
              </p>
            </div>
            <div className="text-center">
              <div className="p-3 bg-purple-500/10 rounded-xl w-fit mx-auto mb-3">
                <Crown className="h-6 w-6 text-purple-500" />
              </div>
              <h3 className="font-medium mb-1">Save Money</h3>
              <p className="text-sm text-muted-foreground">
                Exclusive member discounts on repairs and emergency callouts.
              </p>
            </div>
          </div>
        </div>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md mx-4">
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>Join {plans.find((p) => p.id === enrolling)?.name} Plan</span>
                <Button variant="ghost" size="sm" onClick={() => setShowForm(false)}>
                  ×
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium">Full Name</label>
                <input
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={formData.full_name}
                  onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                  placeholder="John Smith"
                />
              </div>
              <div>
                <label className="text-sm font-medium">Email</label>
                <input
                  type="email"
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="john@example.com"
                />
              </div>
              <div>
                <label className="text-sm font-medium">Phone</label>
                <input
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  placeholder="07700 900000"
                />
              </div>
              <div>
                <label className="text-sm font-medium">Property Address</label>
                <input
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={formData.address}
                  onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                  placeholder="123 Main Street, London"
                />
              </div>
              <Button className="w-full" onClick={handleSubmit}>
                Complete Enrollment
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                Demo request only — online enrollment via api.memberships.enroll needs an
                account (customer_id) and sign-in, so nothing is billed here. By joining
                you agree to our terms of service. You can cancel anytime.
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {submitted && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-md mx-4">
            <CardContent className="py-12 text-center">
              <div className="p-4 bg-green-500/10 rounded-full w-fit mx-auto mb-4">
                <Check className="h-10 w-10 text-green-500" />
              </div>
              <h2 className="text-xl font-bold mb-2">Thanks — request received!</h2>
              <p className="text-muted-foreground mb-6">
                Your interest in the {plans.find((p) => p.id === enrolling)?.name} plan
                has been noted. This demo does not activate billing — we&apos;ll be in
                touch to complete enrollment and schedule your first service.
              </p>
              <Button onClick={() => setSubmitted(false)}>Done</Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
