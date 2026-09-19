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
  const [overview, setOverview] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    api.reports.overview(token)
      .then(setOverview)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  const stats = [
    { label: "Total Revenue", value: `£${(overview?.revenue?.total || 0).toFixed(2)}`, icon: Banknote, color: "text-green-400" },
    { label: "Revenue (MTD)", value: `£${(overview?.revenue?.this_month || 0).toFixed(2)}`, icon: TrendingUp, color: "text-blue-400" },
    { label: "Total Customers", value: overview?.customers?.total || 0, icon: Users, color: "text-purple-400" },
    { label: "Jobs Completed", value: overview?.jobs?.completed || 0, icon: Briefcase, color: "text-yellow-400" },
    { label: "Completion Rate", value: `${(overview?.jobs?.completion_rate || 0).toFixed(0)}%`, icon: BarChart3, color: "text-emerald-400" },
    { label: "Avg Revenue/Customer", value: `£${(overview?.revenue?.avg_per_customer || 0).toFixed(2)}`, icon: Calendar, color: "text-orange-400" },
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
                {overview?.technician_performance?.length > 0 ? (
                  <div className="space-y-3">
                    {overview.technician_performance.map((t: any) => (
                      <div key={t.name} className="flex items-center justify-between text-sm">
                        <span>{t.name}</span>
                        <span className="text-muted-foreground">{t.jobs_completed} jobs · £{t.revenue.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No technician data yet</p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Top Services</CardTitle></CardHeader>
              <CardContent>
                {overview?.top_services?.length > 0 ? (
                  <div className="space-y-3">
                    {overview.top_services.map((s: any) => (
                      <div key={s.title} className="flex items-center justify-between text-sm">
                        <span>{s.title}</span>
                        <span className="text-muted-foreground">{s.count} jobs · £{s.revenue.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No service data yet</p>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
