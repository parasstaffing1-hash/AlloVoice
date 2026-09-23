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
  const [allJobs, setAllJobs] = useState<any[]>([]);
  const [currency, setCurrency] = useState("GBP");
  const [revenueReport, setRevenueReport] = useState<any[] | null>(null);
  const [chartLoading, setChartLoading] = useState(true);
  const [mapMarkers, setMapMarkers] = useState<any[]>([]);
  const [mapNote, setMapNote] = useState("");
  const [fleetVehicles, setFleetVehicles] = useState<any[]>([]);
  const [techPositions, setTechPositions] = useState<any[]>([]);

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
    setChartLoading(true);
    api.dashboard
      .stats(token)
      .then((r: any) => setStats(r))
      .catch((e: any) => console.error(e));
    api.jobs
      .list(token)
      .then((r: any) => {
        const jobs = Array.isArray(r) ? r : [];
        setAllJobs(jobs);
        setRecentJobs(jobs.slice(0, 5));
      })
      .catch((e: any) => console.error(e));
    // Live monthly revenue report (GET /api/reports/revenue?period=monthly).
    // Falls back to a jobs-derived trend when unavailable (offline/demo).
    api.reports
      .revenue("period=monthly", token)
      .then((r: any) => {
        const rows = Array.isArray(r?.data) ? r.data : Array.isArray(r) ? r : [];
        setRevenueReport(rows);
      })
      .catch(() => setRevenueReport(null))
      .finally(() => setChartLoading(false));
    // Real fleet GPS positions + vehicle registry. Vehicles list has no coords;
    // technician GPS lives at GET /api/fleet/positions (not in api.ts wrapper,
    // so use api.request directly). Jobs provide the address side.
    api.fleet
      .list(token)
      .then((r: any) => setFleetVehicles(Array.isArray(r) ? r : []))
      .catch(() => setFleetVehicles([]));
    api
      .request<any>("/api/fleet/positions", { token })
      .then((r: any) => setTechPositions(Array.isArray(r) ? r : []))
      .catch(() => setTechPositions([]));
    api.auth.getBusiness(token).then((r: any) => setCurrency(resolveCurrency(r))).catch(() => setCurrency(resolveCurrency(null)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const getJobCoords = (job: any): { lat: number; lng: number } | null => {
    const candidates: Array<[any, any]> = [
      [job?.latitude, job?.longitude],
      [job?.lat, job?.lng],
      [job?.lat, job?.lon],
      [job?.current_latitude, job?.current_longitude],
      [job?.property?.latitude, job?.property?.longitude],
      [job?.property?.lat, job?.property?.lng],
      [job?.location?.latitude, job?.location?.longitude],
      [job?.location?.lat, job?.location?.lng],
      [job?.address?.latitude, job?.address?.longitude],
    ];
    for (const [la, ln] of candidates) {
      const lat = Number(la);
      const lng = Number(ln);
      if (Number.isFinite(lat) && Number.isFinite(lng) && (lat !== 0 || lng !== 0)) {
        return { lat, lng };
      }
    }
    return null;
  };

  const buildMapMarkers = (vehicles: any[], positions: any[], jobs: any[]) => {
    const markers: any[] = [];
    // Vehicle GPS side: join fleet registry to live technician positions.
    // positions: [{ technician_id, latitude, longitude }]; vehicles:
    // [{ id, registration, assigned_technician_id }]. No coords on vehicles
    // themselves, so only positions with real lat/lng become pins.
    const vehicleByTech = new Map<string, any>();
    vehicles.forEach((v: any) => {
      if (v?.assigned_technician_id) vehicleByTech.set(String(v.assigned_technician_id), v);
    });
    positions.forEach((p: any) => {
      const lat = Number(p?.latitude ?? p?.lat ?? p?.current_latitude);
      const lng = Number(p?.longitude ?? p?.lng ?? p?.lon ?? p?.current_longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lng) || (lat === 0 && lng === 0)) return;
      const vehicle = vehicleByTech.get(String(p?.technician_id ?? p?.id ?? ""));
      markers.push({
        id: `vehicle-${p?.technician_id ?? p?.id ?? `${lat},${lng}`}`,
        latitude: lat,
        longitude: lng,
        label: vehicle?.registration ? `${vehicle.registration} (GPS)` : "Vehicle GPS",
        status: "technician",
        type: "technician" as const,
      });
    });
    // Job address side: only jobs carrying real coordinates are plotted.
    // api.jobs.list (JobResponse) carries no lat/lng fields, so in practice
    // this is empty until the backend includes property/postcode coords.
    // Pins without coords are SKIPPED — never randomised.
    const today = new Date().toISOString().split("T")[0];
    const todaysJobs = jobs.filter((j: any) =>
      typeof j?.scheduled_at === "string" && j.scheduled_at.startsWith(today)
    );
    const pool = todaysJobs.length > 0 ? todaysJobs : jobs;
    pool.forEach((job: any) => {
      const coords = getJobCoords(job);
      if (!coords) return;
      markers.push({
        id: `job-${job.id}`,
        latitude: coords.lat,
        longitude: coords.lng,
        label: job.title || "Job",
        status: job.status || "scheduled",
        type: "job" as const,
      });
    });
    setMapMarkers(markers);
    const gpsCount = markers.filter((m) => m.type === "technician").length;
    const jobCount = markers.filter((m) => m.type === "job").length;
    if (markers.length === 0) {
      setMapNote(
        "No live locations yet — fleet GPS and job coordinates are unavailable. Pins appear here only when the API returns real coordinates."
      );
    } else {
      setMapNote(
        `Live pins: ${gpsCount} vehicle GPS · ${jobCount} job address` +
          (todaysJobs.length > 0 ? " (today's jobs)" : "")
      );
    }
  };

  // Rebuild live pins whenever registry, GPS or jobs arrive (fetches race).
  useEffect(() => {
    buildMapMarkers(fleetVehicles, techPositions, allJobs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fleetVehicles, techPositions, allJobs]);

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

  // Live 6-point revenue trend. Prefer the monthly revenue report
  // (GET /api/reports/revenue?period=monthly → { data: [{ period, revenue, count }] });
  // otherwise derive an estimated trend from stats totals + jobs list dates.
  const buildChartData = () => {
    if (revenueReport && revenueReport.length > 0) {
      const sorted = [...revenueReport].sort((a: any, b: any) =>
        String(a?.period ?? "").localeCompare(String(b?.period ?? ""))
      );
      const last6 = sorted.slice(-6);
      return {
        points: last6.map((row: any) => {
          const period = String(row?.period ?? "");
          let name = period;
          const m = period.match(/^(\d{4})-(\d{1,2})$/);
          if (m) {
            const d = new Date(Number(m[1]), Number(m[2]) - 1, 1);
            name = d.toLocaleDateString("en-GB", { month: "short" });
          }
          return {
            name,
            revenue: Number(row?.revenue ?? 0),
            jobs: Number(row?.count ?? row?.jobs ?? 0),
          };
        }),
        estimated: false,
      };
    }
    if (allJobs.length > 0 || (stats && Number(stats.total_revenue) > 0)) {
      const now = new Date();
      const buckets: Array<{ key: string; name: string; revenue: number; jobs: number }> = [];
      for (let i = 5; i >= 0; i--) {
        const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
        buckets.push({
          key: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
          name: d.toLocaleDateString("en-GB", { month: "short" }),
          revenue: 0,
          jobs: 0,
        });
      }
      const byKey = new Map(buckets.map((b) => [b.key, b]));
      const totalJobs = Number(stats?.total_jobs ?? allJobs.length ?? 0);
      const totalRevenue = Number(stats?.total_revenue ?? 0);
      const avgPerJob = totalJobs > 0 ? totalRevenue / totalJobs : 0;
      allJobs.forEach((j: any) => {
        const raw = j?.created_at ?? j?.scheduled_at ?? j?.completed_at;
        if (!raw) return;
        const d = new Date(raw);
        if (Number.isNaN(d.getTime())) return;
        const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
        const bucket = byKey.get(key);
        if (bucket) bucket.jobs += 1;
      });
      buckets.forEach((b) => {
        b.revenue = Math.round(b.jobs * avgPerJob * 100) / 100;
      });
      return { points: buckets, estimated: true };
    }
    return { points: [], estimated: true };
  };

  const { points: chartData, estimated: chartEstimated } = buildChartData();

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
            {chartLoading ? (
              <p className="text-sm text-muted-foreground text-center py-16">Loading revenue…</p>
            ) : chartData.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-16">
                No revenue data yet — complete a job and mark an invoice paid to see your trend.
              </p>
            ) : (
              <>
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
                <p className="text-xs text-muted-foreground mt-2">
                  {chartEstimated
                    ? "Estimated from live stats + jobs trend (revenue report unavailable offline)."
                    : "Source: live revenue report (paid invoices by month)."}
                </p>
              </>
            )}
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
          <DispatchMap markers={mapMarkers} height="400px" />
          <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-full bg-[#6b7280] border border-white/60" />
              Vehicle GPS ({mapMarkers.filter((m) => m.type === "technician").length})
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-full bg-[#a855f7] border border-white/60" />
              Job address ({mapMarkers.filter((m) => m.type === "job").length})
            </span>
            {mapNote && <span className="w-full sm:w-auto">{mapNote}</span>}
          </div>
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
