"use client";

import { useEffect, useState } from "react";
import "driver.js/dist/driver.css";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { getStatusColor, getStatusLabel } from "@/lib/utils";
import { formatMoney, resolveCurrency } from "@/lib/money";
import {
  Briefcase,
  Users,
  PoundSterling,
  Star,
  TrendingUp,
  Clock,
  CheckCircle2,
  FileText,
  ArrowUpRight,
  Sparkles,
} from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import dynamic from "next/dynamic";

const DispatchMap = dynamic(() => import("@/components/dispatch-map"), { ssr: false });

export default function DashboardPage() {
  const { token } = useAuth();
  const [stats, setStats] = useState<any>(null);
  const [recentJobs, setRecentJobs] = useState<any[]>([]);
  const [currency, setCurrency] = useState("GBP");

  const startTour = async () => {
    if (typeof window === "undefined") return;
    const { driver } = await import("driver.js");
    const driverObj = driver({
      showProgress: true,
      steps: [
        {
          element: '[data-tour="stats"]',
          popover: {
            title: "Business stats",
            description: "Track revenue, active jobs, customers and reviews at a glance.",
          },
        },
        {
          element: '[data-tour="dispatch-map"]',
          popover: {
            title: "Dispatch map",
            description: "See live job locations and plan technician dispatch.",
          },
        },
        {
          element: '[data-tour="quick-actions"]',
          popover: {
            title: "Quick actions",
            description: "Create quotes, customers and invoices in one click.",
          },
        },
        {
          element: '[data-tour="recent-jobs"]',
          popover: {
            title: "Recent jobs",
            description: "Your latest jobs and their live status.",
          },
        },
        {
          element: '[data-tour="ai-quote-cta"]',
          popover: {
            title: "AI quote",
            description: "Generate a voice-powered AI quote to get started fast.",
          },
        },
      ],
      onDestroyed: () => {
        try {
          window.localStorage.setItem("vf_tour_seen", "1");
        } catch {
          /* storage unavailable */
        }
      },
    });
    driverObj.drive();
  };

  useEffect(() => {
    if (!token) return;
    const load = async () => {
      try {
        const s: any = await api.dashboard.stats(token);
        setStats(s);
        const j: any = await api.jobs.list(token);
        setRecentJobs(j.slice(0, 5));
      } catch (e) {
        console.error(e);
      }
    };
    load();
    api.auth.getBusiness(token).then((r: any) => setCurrency(resolveCurrency(r))).catch(() => setCurrency(resolveCurrency(null)));
  }, [token]);

  if (!stats) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-muted-foreground">Loading dashboard...</div>
      </div>
    );
  }

  const statCards = [
    {
      title: "Total Revenue",
      value: formatMoney(stats.total_revenue, currency),
      icon: PoundSterling,
      change: `+${formatMoney(stats.revenue_this_month, currency)} this month`,
      color: "text-green-400",
    },
    {
      title: "Active Jobs",
      value: stats.active_jobs,
      icon: Briefcase,
      change: `${stats.total_jobs} total jobs`,
      color: "text-blue-400",
    },
    {
      title: "Customers",
      value: stats.total_customers,
      icon: Users,
      change: `${stats.pending_quotes} pending quotes`,
      color: "text-purple-400",
    },
    {
      title: "Reviews",
      value: stats.average_rating.toFixed(1),
      icon: Star,
      change: `${stats.reviews_count} total reviews`,
      color: "text-yellow-400",
    },
  ];

  const chartData = [
    { name: "Jan", revenue: 42000, jobs: 12 },
    { name: "Feb", revenue: 58000, jobs: 18 },
    { name: "Mar", revenue: 71000, jobs: 22 },
    { name: "Apr", revenue: 65000, jobs: 20 },
    { name: "May", revenue: 89000, jobs: 28 },
    { name: "Jun", revenue: 95000, jobs: 31 },
  ];

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground">Welcome back. Here's your business overview.</p>
        </div>
        <Button variant="outline" size="sm" onClick={startTour} className="gap-2 shrink-0">
          <Sparkles className="h-4 w-4" /> Take a tour
        </Button>
      </div>

      {/* Stat Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4" data-tour="stats">
        {statCards.map((stat) => (
          <Card key={stat.title}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {stat.title}
              </CardTitle>
              <stat.icon className={`h-4 w-4 ${stat.color}`} />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              <p className="text-xs text-muted-foreground mt-1">{stat.change}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Chart + Recent Jobs */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Revenue Trend</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e1e2e" />
                <XAxis dataKey="name" stroke="#888" fontSize={12} />
                <YAxis stroke="#888" fontSize={12} />
                <Tooltip
                  contentStyle={{ background: "#1a1a2e", border: "1px solid #333", borderRadius: 8 }}
                  labelStyle={{ color: "#fff" }}
                />
                <Area type="monotone" dataKey="revenue" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.2} />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card data-tour="recent-jobs">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent Jobs</CardTitle>
            <a href="/jobs" className="text-sm text-primary hover:underline flex items-center gap-1">
              View all <ArrowUpRight className="h-3 w-3" />
            </a>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {recentJobs.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">No jobs yet</p>
              ) : (
                recentJobs.map((job: any) => (
                  <div key={job.id} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
                        <Briefcase className="h-4 w-4 text-primary" />
                      </div>
                      <div>
                        <p className="text-sm font-medium">{job.title}</p>
                        <p className="text-xs text-muted-foreground">
                          {new Date(job.created_at).toLocaleDateString("en-IN")}
                        </p>
                      </div>
                    </div>
                    <Badge className={getStatusColor(job.status)}>
                      {getStatusLabel(job.status)}
                    </Badge>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Dispatch Map */}
      <Card data-tour="dispatch-map">
        <CardHeader>
          <CardTitle>Dispatch Map</CardTitle>
        </CardHeader>
        <CardContent>
          <DispatchMap
            markers={recentJobs.map((job: any) => ({
              id: job.id,
              latitude: 51.5074 + (Math.random() - 0.5) * 0.1,
              longitude: -0.1276 + (Math.random() - 0.5) * 0.1,
              label: job.title,
              status: job.status,
              type: "job" as const,
            }))}
            height="400px"
          />
        </CardContent>
      </Card>

      {/* Quick Actions */}
      <Card data-tour="quick-actions">
        <CardHeader>
          <CardTitle>Quick Actions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-4">
            <a href="/quote" data-tour="ai-quote-cta" className="flex items-center gap-3 rounded-xl border border-border/50 bg-background/50 p-4 hover:border-primary/50 transition-all">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Briefcase className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium">New AI Quote</p>
                <p className="text-xs text-muted-foreground">Voice-powered</p>
              </div>
            </a>
            <a href="/customers" className="flex items-center gap-3 rounded-xl border border-border/50 bg-background/50 p-4 hover:border-primary/50 transition-all">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-500/10 text-blue-400">
                <Users className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium">Add Customer</p>
                <p className="text-xs text-muted-foreground">CRM entry</p>
              </div>
            </a>
            <a href="/invoices" className="flex items-center gap-3 rounded-xl border border-border/50 bg-background/50 p-4 hover:border-primary/50 transition-all">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-500/10 text-green-400">
                <FileText className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium">Create Invoice</p>
                <p className="text-xs text-muted-foreground">Bill customer</p>
              </div>
            </a>
            <a href="/jobs" className="flex items-center gap-3 rounded-xl border border-border/50 bg-background/50 p-4 hover:border-primary/50 transition-all">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-orange-500/10 text-orange-400">
                <Clock className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium">Dispatch Board</p>
                <p className="text-xs text-muted-foreground">Manage jobs</p>
              </div>
            </a>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
