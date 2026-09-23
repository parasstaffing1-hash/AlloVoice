"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  BarChart3, Download, TrendingUp, Users, Banknote, Calendar, Briefcase,
} from "lucide-react";

export default function ReportsPage() {
  const { token } = useAuth();
  const [revenue, setRevenue] = useState<any>(null);
  const [techPerf, setTechPerf] = useState<any[]>([]);
  const [satisfaction, setSatisfaction] = useState<any>(null);
  const [utilization, setUtilization] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    // Real backend routes: /revenue, /technician-performance,
    // /customer-satisfaction, /job-utilization.
    Promise.allSettled([
      api.reports.revenue("period=monthly", token).then(setRevenue),
      api.reports.technicianPerformance(token).then((r: any) => setTechPerf(r?.data || [])),
      api.reports.customerSatisfaction(token).then(setSatisfaction),
      api.reports.jobUtilization(token).then(setUtilization),
    ]).finally(() => setLoading(false));
  }, [token]);

  const revenueRows = Array.isArray(revenue?.data) ? revenue.data : [];
  const totalRevenue = revenueRows.reduce((sum: number, r: any) => sum + (Number(r.revenue) || 0), 0);

  const stats = [
    { label: "Total Revenue", value: `£${totalRevenue.toFixed(2)}`, icon: Banknote, color: "text-green-400" },
    { label: "Jobs Completed", value: utilization?.completed ?? 0, icon: Briefcase, color: "text-yellow-400" },
    { label: "Completion Rate", value: `${(Number(utilization?.completion_rate) || 0).toFixed(0)}%`, icon: BarChart3, color: "text-emerald-400" },
    { label: "Avg Rating", value: (Number(satisfaction?.average_rating) || 0).toFixed(1), icon: Users, color: "text-purple-400" },
    { label: "Total Reviews", value: satisfaction?.total_reviews ?? 0, icon: TrendingUp, color: "text-blue-400" },
    { label: "NPS", value: (Number(satisfaction?.nps) || 0).toFixed(1), icon: Calendar, color: "text-orange-400" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Reports</h1>
        <Button variant="outline" className="gap-2"><Download className="h-4 w-4" />Export CSV</Button>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            {stats.map((s) => (
              <Card key={s.label}>
                <CardContent className="py-4 flex items-center gap-4">
                  <s.icon className={`h-8 w-8 ${s.color}`} />
                  <div>
                    <p className="text-2xl font-bold">{s.value}</p>
                    <p className="text-xs text-muted-foreground">{s.label}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>Technician Performance</CardTitle></CardHeader>
              <CardContent>
                {techPerf.length > 0 ? (
                  <div className="space-y-3">
                    {techPerf.map((t: any) => (
                      <div key={t.technician_id} className="flex items-center justify-between text-sm">
                        <span>{String(t.technician_id).slice(0, 8)}…</span>
                        <span className="text-muted-foreground">{t.jobs_completed} jobs · ★{(Number(t.average_rating) || 0).toFixed(1)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No technician data yet</p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Job Utilization</CardTitle></CardHeader>
              <CardContent>
                {utilization ? (
                  <div className="space-y-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span>Total jobs</span>
                      <span className="text-muted-foreground">{utilization.total_jobs ?? 0}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Completed</span>
                      <span className="text-muted-foreground">{utilization.completed ?? 0}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Cancelled</span>
                      <span className="text-muted-foreground">{utilization.cancelled ?? 0}</span>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No utilization data yet</p>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
