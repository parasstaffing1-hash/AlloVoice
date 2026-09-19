"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { Trophy, Star, TrendingUp, Users, PoundSterling } from "lucide-react";

const fmtGBP = (n: number) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(Number(n ?? 0));

const fmtDate = (d: string) => {
  try {
    return new Date(d).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return d;
  }
};

function Stars({ value }: { value: number }) {
  const full = Math.round(Number(value ?? 0));
  return (
    <span className="text-yellow-400 text-sm">
      {"★".repeat(Math.min(5, Math.max(0, full)))}
      <span className="text-muted-foreground">{"★".repeat(5 - Math.min(5, Math.max(0, full)))}</span>
    </span>
  );
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, Number(score ?? 0)));
  const color = pct >= 80 ? "bg-green-500" : pct >= 60 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

type Tab = "scorecards" | "leaderboard" | "profitability" | "value";

export default function ScorecardsPage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<Tab>("scorecards");
  const [loading, setLoading] = useState(true);

  // Scorecards
  const [period, setPeriod] = useState("last_30_days");
  const [cards, setCards] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Leaderboard
  const [board, setBoard] = useState<any[]>([]);

  // Profitability
  const [groupBy, setGroupBy] = useState("job_type");
  const [groups, setGroups] = useState<any[]>([]);

  // CLV
  const [clv, setClv] = useState<any[]>([]);

  const loadScorecards = () => {
    if (!token) return;
    setLoading(true);
    api.performance
      .scorecards(period, token)
      .then((r: any) => setCards(Array.isArray(r) ? r : (r?.scorecards ?? r?.data ?? [])))
      .catch(() => setCards([]))
      .finally(() => setLoading(false));
  };

  const loadLeaderboard = () => {
    if (!token) return;
    setLoading(true);
    api.performance
      .leaderboard(token)
      .then((r: any) => setBoard(Array.isArray(r) ? r : (r?.leaderboard ?? r?.data ?? [])))
      .catch(() => setBoard([]))
      .finally(() => setLoading(false));
  };

  const loadProfitability = () => {
    if (!token) return;
    setLoading(true);
    api.performance
      .profitability(groupBy, token)
      .then((r: any) => setGroups(Array.isArray(r) ? r : (r?.groups ?? r?.data ?? [])))
      .catch(() => setGroups([]))
      .finally(() => setLoading(false));
  };

  const loadClv = () => {
    if (!token) return;
    setLoading(true);
    api.performance
      .clv(token)
      .then((r: any) => {
        const rows = Array.isArray(r) ? r : (r?.customers ?? r?.data ?? []);
        setClv([...rows].sort((a: any, b: any) => Number(b.total_spend ?? 0) - Number(a.total_spend ?? 0)));
      })
      .catch(() => setClv([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!token) return;
    if (tab === "scorecards") loadScorecards();
    if (tab === "leaderboard") loadLeaderboard();
    if (tab === "profitability") loadProfitability();
    if (tab === "value") loadClv();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, tab, period, groupBy]);

  const openDetail = (tech: any) => {
    const id = tech.technician_id ?? tech.id;
    if (!id || !token) return;
    setSelectedId(id);
    setDetailLoading(true);
    setDetail(null);
    api.performance
      .scorecard(String(id), token)
      .then((r: any) => setDetail(r))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  };

  const totals = groups.reduce(
    (acc: any, g: any) => ({
      jobs: acc.jobs + Number(g.jobs ?? 0),
      revenue: acc.revenue + Number(g.revenue ?? 0),
      cost: acc.cost + Number(g.cost ?? 0),
      profit: acc.profit + Number(g.profit ?? 0),
    }),
    { jobs: 0, revenue: 0, cost: 0, profit: 0 }
  );
  const totalMargin = totals.revenue > 0 ? (totals.profit / totals.revenue) * 100 : 0;

  const tabs: { id: Tab; label: string; icon: any }[] = [
    { id: "scorecards", label: "Scorecards", icon: Star },
    { id: "leaderboard", label: "Leaderboard", icon: Trophy },
    { id: "profitability", label: "Profitability", icon: TrendingUp },
    { id: "value", label: "Customer Value", icon: Users },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <Trophy className="h-7 w-7 text-yellow-400" /> Technician Scorecards
        </h1>
        <p className="text-muted-foreground">Performance, profitability and customer value.</p>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        {tabs.map((t) => (
          <Button
            key={t.id}
            size="sm"
            variant={tab === t.id ? "default" : "outline"}
            onClick={() => {
              setTab(t.id);
              setSelectedId(null);
              setDetail(null);
            }}
          >
            <t.icon className="h-4 w-4 mr-2" />
            {t.label}
          </Button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-[40vh]">
          <div className="text-muted-foreground">Loading...</div>
        </div>
      ) : (
        <>
          {/* SCORECARDS */}
          {tab === "scorecards" && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Period:</span>
                <select
                  className="flex h-9 rounded-lg border border-input bg-background px-3 text-sm"
                  value={period}
                  onChange={(e) => setPeriod(e.target.value)}
                >
                  <option value="last_30_days">Last 30 days</option>
                  <option value="last_90_days">Last 90 days</option>
                  <option value="all">All time</option>
                </select>
              </div>

              {cards.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">No scorecards yet</p>
              ) : (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {cards.map((tech: any, i: number) => {
                    const id = tech.technician_id ?? tech.id ?? String(i);
                    const score = Number(tech.composite_score ?? tech.score ?? 0);
                    return (
                      <Card
                        key={id}
                        className={`cursor-pointer transition-all hover:border-primary/50 ${selectedId === String(id) ? "border-primary" : ""}`}
                        onClick={() => openDetail(tech)}
                      >
                        <CardHeader className="pb-2">
                          <CardTitle className="text-base flex items-center justify-between">
                            <span>{tech.name ?? tech.technician_name ?? "Technician"}</span>
                            <Badge variant="secondary">{score.toFixed(0)}</Badge>
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3">
                          <ScoreBar score={score} />
                          <div className="grid grid-cols-2 gap-2 text-sm">
                            <div>
                              <p className="text-xs text-muted-foreground">Jobs completed</p>
                              <p className="font-semibold">{tech.jobs_completed ?? 0}</p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground">Revenue</p>
                              <p className="font-semibold flex items-center gap-1">
                                <PoundSterling className="h-3 w-3 text-green-400" />
                                {fmtGBP(tech.revenue ?? 0).replace("£", "")}
                              </p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground">Completion</p>
                              <p className="font-semibold">{Number(tech.completion_rate ?? 0).toFixed(0)}%</p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground">First-time fix</p>
                              <p className="font-semibold">{Number(tech.first_time_fix_rate ?? 0).toFixed(0)}%</p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground">On-time</p>
                              <p className="font-semibold">{Number(tech.on_time_rate ?? 0).toFixed(0)}%</p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground">Rating</p>
                              <Stars value={tech.avg_rating ?? 0} />
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}

              {/* Detail panel */}
              {selectedId && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Technician detail</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {detailLoading ? (
                      <p className="text-sm text-muted-foreground">Loading detail...</p>
                    ) : !detail ? (
                      <p className="text-sm text-muted-foreground">No detail available</p>
                    ) : (
                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                          <p className="text-sm font-medium">Recent jobs</p>
                          {(detail.recent_jobs ?? []).length === 0 ? (
                            <p className="text-sm text-muted-foreground">No recent jobs</p>
                          ) : (
                            (detail.recent_jobs ?? []).slice(0, 8).map((j: any, i: number) => (
                              <div
                                key={j.id ?? i}
                                className="flex items-center justify-between rounded-lg border border-border/50 px-3 py-2 text-sm"
                              >
                                <div>
                                  <p className="font-medium">{j.title ?? j.job_type ?? `Job ${i + 1}`}</p>
                                  <p className="text-xs text-muted-foreground">
                                    {j.created_at ? fmtDate(j.created_at) : j.date ?? ""}
                                  </p>
                                </div>
                                <Badge variant="secondary">{j.status ?? fmtGBP(j.revenue ?? j.total ?? 0)}</Badge>
                              </div>
                            ))
                          )}
                        </div>
                        <div className="space-y-2">
                          <p className="text-sm font-medium">Rating breakdown</p>
                          {detail.rating_breakdown ? (
                            Object.entries(detail.rating_breakdown).map(([k, v]: [string, any]) => (
                              <div key={k} className="flex items-center justify-between text-sm">
                                <span className="text-muted-foreground">{k} ★</span>
                                <span className="font-semibold">{String(v)}</span>
                              </div>
                            ))
                          ) : (
                            <p className="text-sm text-muted-foreground">
                              Avg rating: {Number(detail.avg_rating ?? 0).toFixed(1)} (
                              {detail.total_ratings ?? detail.reviews_count ?? 0} reviews)
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* LEADERBOARD */}
          {tab === "leaderboard" && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Trophy className="h-5 w-5 text-yellow-400" /> Leaderboard
                </CardTitle>
              </CardHeader>
              <CardContent>
                {board.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-8">No rankings yet</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-left text-muted-foreground">
                          <th className="py-2 pr-4">Rank</th>
                          <th className="py-2 pr-4">Technician</th>
                          <th className="py-2 pr-4 text-right">Score</th>
                          <th className="py-2 pr-4 text-right">Revenue</th>
                          <th className="py-2 text-right">Rating</th>
                        </tr>
                      </thead>
                      <tbody>
                        {board.map((row: any, i: number) => {
                          const rank = row.rank ?? i + 1;
                          return (
                            <tr key={row.technician_id ?? row.id ?? i} className="border-b border-border/40">
                              <td className="py-2 pr-4">
                                <span className="flex items-center gap-2 font-semibold">
                                  {rank === 1 ? (
                                    <Trophy className="h-4 w-4 text-yellow-400" />
                                  ) : (
                                    <span className="text-muted-foreground">#{rank}</span>
                                  )}
                                  {rank === 1 && <Badge className="bg-yellow-500/15 text-yellow-400 border-yellow-500/30">#1</Badge>}
                                </span>
                              </td>
                              <td className="py-2 pr-4 font-medium">
                                {row.name ?? row.technician_name ?? "Technician"}
                              </td>
                              <td className="py-2 pr-4 text-right">
                                {Number(row.composite_score ?? row.score ?? 0).toFixed(0)}
                              </td>
                              <td className="py-2 pr-4 text-right">{fmtGBP(row.revenue ?? 0)}</td>
                              <td className="py-2 text-right">
                                <Stars value={row.avg_rating ?? row.rating ?? 0} />
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* PROFITABILITY */}
          {tab === "profitability" && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Group by:</span>
                <select
                  className="flex h-9 rounded-lg border border-input bg-background px-3 text-sm"
                  value={groupBy}
                  onChange={(e) => setGroupBy(e.target.value)}
                >
                  <option value="job_type">Job type</option>
                  <option value="technician">Technician</option>
                  <option value="month">Month</option>
                </select>
              </div>

              <div className="grid gap-4 md:grid-cols-4">
                {[
                  { label: "Revenue", value: fmtGBP(totals.revenue), color: "text-green-400" },
                  { label: "Cost", value: fmtGBP(totals.cost), color: "text-red-400" },
                  { label: "Profit", value: fmtGBP(totals.profit), color: "" },
                  { label: "Margin", value: `${totalMargin.toFixed(1)}%`, color: "text-blue-400" },
                ].map((s) => (
                  <Card key={s.label}>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-medium text-muted-foreground">{s.label}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
                      <p className="text-xs text-muted-foreground mt-1">{totals.jobs} jobs total</p>
                    </CardContent>
                  </Card>
                ))}
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="h-5 w-5 text-green-400" /> Profitability by {groupBy.replace("_", " ")}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {groups.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-8">No data yet</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border text-left text-muted-foreground">
                            <th className="py-2 pr-4">Group</th>
                            <th className="py-2 pr-4 text-right">Jobs</th>
                            <th className="py-2 pr-4 text-right">Revenue</th>
                            <th className="py-2 pr-4 text-right">Cost</th>
                            <th className="py-2 pr-4 text-right">Profit</th>
                            <th className="py-2 text-right">Margin</th>
                          </tr>
                        </thead>
                        <tbody>
                          {groups.map((g: any, i: number) => (
                            <tr key={g.key ?? g.group ?? i} className="border-b border-border/40">
                              <td className="py-2 pr-4 font-medium">{g.key ?? g.group ?? g.name ?? `Group ${i + 1}`}</td>
                              <td className="py-2 pr-4 text-right">{g.jobs ?? 0}</td>
                              <td className="py-2 pr-4 text-right">{fmtGBP(g.revenue ?? 0)}</td>
                              <td className="py-2 pr-4 text-right">{fmtGBP(g.cost ?? 0)}</td>
                              <td className="py-2 pr-4 text-right font-semibold">{fmtGBP(g.profit ?? 0)}</td>
                              <td className="py-2 text-right">
                                <Badge variant="secondary">{Number(g.margin_pct ?? g.margin ?? 0).toFixed(1)}%</Badge>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}

          {/* CUSTOMER VALUE */}
          {tab === "value" && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5 text-purple-400" /> Customer Lifetime Value
                </CardTitle>
              </CardHeader>
              <CardContent>
                {clv.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-8">No customer value data yet</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-left text-muted-foreground">
                          <th className="py-2 pr-4">Customer</th>
                          <th className="py-2 pr-4 text-right">Jobs</th>
                          <th className="py-2 pr-4 text-right">Total spend</th>
                          <th className="py-2 pr-4 text-right">Avg job value</th>
                          <th className="py-2 text-right">Predicted annual</th>
                        </tr>
                      </thead>
                      <tbody>
                        {clv.map((c: any, i: number) => (
                          <tr key={c.customer_id ?? c.id ?? i} className="border-b border-border/40">
                            <td className="py-2 pr-4 font-medium">{c.name ?? c.customer_name ?? "Customer"}</td>
                            <td className="py-2 pr-4 text-right">{c.jobs ?? c.job_count ?? 0}</td>
                            <td className="py-2 pr-4 text-right font-semibold">{fmtGBP(c.total_spend ?? 0)}</td>
                            <td className="py-2 pr-4 text-right">{fmtGBP(c.avg_job_value ?? 0)}</td>
                            <td className="py-2 text-right text-green-400">
                              {fmtGBP(c.predicted_annual_value ?? 0)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
