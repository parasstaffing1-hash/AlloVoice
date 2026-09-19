"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  Crown, Users, Calendar, DollarSign, Plus, X, RefreshCw,
} from "lucide-react";

interface Plan {
  id: string;
  name: string;
  description: string;
  price_monthly: number;
  price_yearly: number;
  features: string[];
  job_priority: boolean;
  discount_percent: number;
  max_emergency_calls: number;
}

interface Overview {
  total_members: number;
  mrr: number;
  plans_breakdown: { plan: string; count: number; revenue: number }[];
}

export default function MembershipsDashboardPage() {
  const { token } = useAuth();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCreatePlan, setShowCreatePlan] = useState(false);
  const [newPlan, setNewPlan] = useState({
    name: "", description: "", price_monthly: 0, price_yearly: 0,
    features: "", job_priority: false, discount_percent: 0, max_emergency_calls: 0,
  });
  const [scheduling, setScheduling] = useState(false);

  const loadData = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [plansRes, overviewRes] = await Promise.all([
        api.memberships.listPlans(token),
        api.memberships.businessOverview(token),
      ]);
      setPlans(plansRes);
      setOverview(overviewRes);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { loadData(); }, [token]);

  const handleCreatePlan = async () => {
    if (!token) return;
    try {
      await api.memberships.createPlan({
        name: newPlan.name,
        description: newPlan.description,
        price_monthly: newPlan.price_monthly,
        price_yearly: newPlan.price_yearly,
        features: newPlan.features.split(",").map((f) => f.trim()).filter(Boolean),
        job_priority: newPlan.job_priority,
        discount_percent: newPlan.discount_percent,
        max_emergency_calls: newPlan.max_emergency_calls,
      }, token);
      setShowCreatePlan(false);
      setNewPlan({ name: "", description: "", price_monthly: 0, price_yearly: 0, features: "", job_priority: false, discount_percent: 0, max_emergency_calls: 0 });
      loadData();
    } catch {}
  };

  const handleScheduleRecurring = async () => {
    if (!token) return;
    setScheduling(true);
    try {
      await api.memberships.scheduleRecurring(token);
      loadData();
    } catch {}
    setScheduling(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Memberships</h1>
        <div className="flex gap-2">
          <Button variant="outline" className="gap-2" onClick={handleScheduleRecurring} disabled={scheduling}>
            <RefreshCw className={`h-4 w-4 ${scheduling ? "animate-spin" : ""}`} />
            Schedule Recurring
          </Button>
          <Button className="gap-2" onClick={() => setShowCreatePlan(true)}>
            <Plus className="h-4 w-4" />New Plan
          </Button>
        </div>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card>
              <CardContent className="py-6">
                <div className="flex items-center gap-3">
                  <div className="p-3 bg-green-500/10 rounded-lg">
                    <DollarSign className="h-6 w-6 text-green-500" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Monthly Recurring Revenue</p>
                    <p className="text-2xl font-bold">£{overview?.mrr.toFixed(2) || "0.00"}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="py-6">
                <div className="flex items-center gap-3">
                  <div className="p-3 bg-blue-500/10 rounded-lg">
                    <Users className="h-6 w-6 text-blue-500" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Active Members</p>
                    <p className="text-2xl font-bold">{overview?.total_members || 0}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="py-6">
                <div className="flex items-center gap-3">
                  <div className="p-3 bg-purple-500/10 rounded-lg">
                    <Crown className="h-6 w-6 text-purple-500" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Active Plans</p>
                    <p className="text-2xl font-bold">{plans.length}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          <h2 className="text-xl font-semibold mt-8">Plans</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {plans.map((plan) => {
              const breakdown = overview?.plans_breakdown.find((b) => b.plan === plan.name);
              return (
                <Card key={plan.id}>
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                      <span>{plan.name}</span>
                      <Badge variant="secondary">
                        {breakdown?.count || 0} members
                      </Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <p className="text-sm text-muted-foreground">{plan.description}</p>
                    <div className="flex items-baseline gap-1">
                      <span className="text-2xl font-bold">£{plan.price_monthly}</span>
                      <span className="text-sm text-muted-foreground">/mo</span>
                      <span className="text-sm text-muted-foreground ml-2">
                        (£{plan.price_yearly}/yr)
                      </span>
                    </div>
                    <div className="space-y-1">
                      {plan.features.map((f, i) => (
                        <p key={i} className="text-xs text-muted-foreground flex items-center gap-1">
                          <span className="text-green-500">✓</span> {f}
                        </p>
                      ))}
                    </div>
                    {breakdown && (
                      <p className="text-sm text-green-500 font-medium">
                        £{breakdown.revenue.toFixed(2)}/mo revenue
                      </p>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>

          <h2 className="text-xl font-semibold mt-8">Members by Plan</h2>
          {overview && overview.plans_breakdown.length > 0 ? (
            <div className="space-y-3">
              {overview.plans_breakdown.map((b) => (
                <Card key={b.plan}>
                  <CardContent className="py-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="p-2 bg-primary/10 rounded-lg">
                        <Crown className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <p className="font-medium">{b.plan}</p>
                        <p className="text-sm text-muted-foreground">
                          {b.count} active member{b.count !== 1 ? "s" : ""}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-medium">£{b.revenue.toFixed(2)}/mo</p>
                      <p className="text-xs text-muted-foreground">
                        £{(b.revenue * 12).toFixed(2)}/yr projected
                      </p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <Users className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
                <p className="text-muted-foreground">No active members yet</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Share your public membership page to start enrolling customers
                </p>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {showCreatePlan && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="w-full max-w-lg">
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                Create Membership Plan
                <Button variant="ghost" size="sm" onClick={() => setShowCreatePlan(false)}>
                  <X className="h-4 w-4" />
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium">Plan Name</label>
                <input
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={newPlan.name}
                  onChange={(e) => setNewPlan({ ...newPlan, name: e.target.value })}
                  placeholder="e.g. Gold Plan"
                />
              </div>
              <div>
                <label className="text-sm font-medium">Description</label>
                <input
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={newPlan.description}
                  onChange={(e) => setNewPlan({ ...newPlan, description: e.target.value })}
                  placeholder="What's included"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">Monthly Price (£)</label>
                  <input
                    type="number"
                    className="w-full mt-1 p-2 border rounded-md bg-background"
                    value={newPlan.price_monthly}
                    onChange={(e) => setNewPlan({ ...newPlan, price_monthly: parseFloat(e.target.value) || 0 })}
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">Yearly Price (£)</label>
                  <input
                    type="number"
                    className="w-full mt-1 p-2 border rounded-md bg-background"
                    value={newPlan.price_yearly}
                    onChange={(e) => setNewPlan({ ...newPlan, price_yearly: parseFloat(e.target.value) || 0 })}
                  />
                </div>
              </div>
              <div>
                <label className="text-sm font-medium">Features (comma-separated)</label>
                <input
                  className="w-full mt-1 p-2 border rounded-md bg-background"
                  value={newPlan.features}
                  onChange={(e) => setNewPlan({ ...newPlan, features: e.target.value })}
                  placeholder="Annual service, Priority booking, Discount"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">Discount %</label>
                  <input
                    type="number"
                    className="w-full mt-1 p-2 border rounded-md bg-background"
                    value={newPlan.discount_percent}
                    onChange={(e) => setNewPlan({ ...newPlan, discount_percent: parseInt(e.target.value) || 0 })}
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">Emergency Calls/Year</label>
                  <input
                    type="number"
                    className="w-full mt-1 p-2 border rounded-md bg-background"
                    value={newPlan.max_emergency_calls}
                    onChange={(e) => setNewPlan({ ...newPlan, max_emergency_calls: parseInt(e.target.value) || 0 })}
                  />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="priority"
                  checked={newPlan.job_priority}
                  onChange={(e) => setNewPlan({ ...newPlan, job_priority: e.target.checked })}
                />
                <label htmlFor="priority" className="text-sm">Priority job booking</label>
              </div>
              <Button className="w-full" onClick={handleCreatePlan}>Create Plan</Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
