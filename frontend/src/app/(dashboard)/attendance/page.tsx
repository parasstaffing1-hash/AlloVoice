"use client";

import { useState, useEffect, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { Clock, Play, Square, Coffee, Users, CalendarDays, Timer } from "lucide-react";

type Tab = "me" | "team" | "clock";

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function fmtDate(value: any): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function fmtTime(value: any): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function fmtHours(h: any): string {
  const n = Number(h);
  if (Number.isNaN(n)) return "—";
  return `${n.toFixed(2)}h`;
}

function shiftDurationHours(s: any): number {
  if (typeof s?.duration_hours === "number") return s.duration_hours;
  if (typeof s?.hours === "number") return s.hours;
  if (typeof s?.duration === "number") return s.duration;
  const start = s?.clock_in || s?.start_time || s?.start || s?.date;
  const end = s?.clock_out || s?.end_time || s?.end;
  if (start && end) {
    const ms = new Date(end).getTime() - new Date(start).getTime();
    if (!Number.isNaN(ms) && ms >= 0) return ms / 3600000;
  }
  return 0;
}

function shiftOvertimeHours(s: any): number {
  if (typeof s?.overtime_hours === "number") return s.overtime_hours;
  if (typeof s?.overtime === "number") return s.overtime;
  return 0;
}

function shiftBreaksLabel(s: any): string {
  if (Array.isArray(s?.breaks)) {
    if (s.breaks.length === 0) return "—";
    return `${s.breaks.length} break${s.breaks.length !== 1 ? "s" : ""}`;
  }
  if (typeof s?.break_minutes === "number") return `${s.break_minutes}m`;
  if (typeof s?.breaks_taken === "number") return `${s.breaks_taken}`;
  return "—";
}

function formatElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  if (h > 0) return `${h}:${mm}:${ss}`;
  return `${mm}:${ss}`;
}

function getCoords(): Promise<{ latitude?: number; longitude?: number }> {
  return new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      resolve({});
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
      () => resolve({}),
      { timeout: 8000 }
    );
  });
}

export default function AttendancePage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<Tab>("clock");

  // Date range (shared, default last 30d)
  const [startDate, setStartDate] = useState(() => toISODate(new Date(Date.now() - 30 * 86400000)));
  const [endDate, setEndDate] = useState(() => toISODate(new Date()));

  // Clock status
  const [status, setStatus] = useState<any>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [clockNote, setClockNote] = useState("");
  const [clockBusy, setClockBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // My time
  const [myShifts, setMyShifts] = useState<any[]>([]);
  const [myTotals, setMyTotals] = useState<any>(null);
  const [myLoading, setMyLoading] = useState(false);

  // Team
  const [teamRows, setTeamRows] = useState<any[]>([]);
  const [teamLoading, setTeamLoading] = useState(false);

  const fetchStatus = () => {
    if (!token) return;
    setStatusLoading(true);
    api.attendance
      .status(token)
      .then((r: any) => {
        setStatus(r?.data || r);
      })
      .catch(() => {})
      .finally(() => setStatusLoading(false));
  };

  const fetchMe = () => {
    if (!token) return;
    setMyLoading(true);
    api.attendance
      .me(token, startDate || undefined, endDate || undefined)
      .then((r: any) => {
        const shifts = r?.shifts || r?.records || r?.data || (Array.isArray(r) ? r : []);
        setMyShifts(Array.isArray(shifts) ? shifts : []);
        setMyTotals(r?.totals || r?.summary || null);
      })
      .catch((e: any) => setError(e?.message || "Failed to load shifts"))
      .finally(() => setMyLoading(false));
  };

  const fetchTeam = () => {
    if (!token) return;
    setTeamLoading(true);
    api.attendance
      .team(token, startDate || undefined, endDate || undefined)
      .then((r: any) => {
        const rows =
          r?.team || r?.members || r?.shifts || r?.records || r?.data || (Array.isArray(r) ? r : []);
        setTeamRows(Array.isArray(rows) ? rows : []);
      })
      .catch((e: any) => setError(e?.message || "Failed to load team attendance"))
      .finally(() => setTeamLoading(false));
  };

  useEffect(() => {
    if (!token) return;
    fetchStatus();
    fetchMe();
    fetchTeam();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Live ticking clock
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const clockedIn = Boolean(status?.clocked_in ?? status?.is_clocked_in ?? status?.shift);
  const activeShift = status?.shift || status?.active_shift || null;
  const todayHours = status?.today_hours ?? status?.todayHours ?? status?.hours_today ?? 0;

  const shiftStartMs = useMemo(() => {
    const raw = activeShift?.clock_in || activeShift?.start_time || activeShift?.start || status?.clock_in_at;
    if (!raw) return null;
    const ms = new Date(raw).getTime();
    return Number.isNaN(ms) ? null : ms;
  }, [activeShift, status]);

  const elapsedSecs = shiftStartMs != null ? (now - shiftStartMs) / 1000 : 0;

  const onBreak =
    Boolean(activeShift?.on_break) ||
    (Array.isArray(activeShift?.breaks) &&
      activeShift.breaks.length > 0 &&
      !activeShift.breaks[activeShift.breaks.length - 1]?.end);

  const handleClockIn = async () => {
    if (!token) return;
    setClockBusy(true);
    setMessage(null);
    setError(null);
    const coords = await getCoords();
    api.attendance
      .clockIn({ latitude: coords.latitude, longitude: coords.longitude, notes: clockNote.trim() || undefined }, token)
      .then((r: any) => {
        setMessage("Clocked in");
        setClockNote("");
        fetchStatus();
      })
      .catch((e: any) => setError(e?.message || "Clock in failed"))
      .finally(() => setClockBusy(false));
  };

  const handleClockOut = async () => {
    if (!token) return;
    setClockBusy(true);
    setMessage(null);
    setError(null);
    const coords = await getCoords();
    api.attendance
      .clockOut({ latitude: coords.latitude, longitude: coords.longitude, notes: clockNote.trim() || undefined }, token)
      .then((r: any) => {
        setMessage("Clocked out");
        setClockNote("");
        fetchStatus();
        fetchMe();
      })
      .catch((e: any) => setError(e?.message || "Clock out failed"))
      .finally(() => setClockBusy(false));
  };

  const handleBreakStart = () => {
    if (!token) return;
    setClockBusy(true);
    setError(null);
    setMessage(null);
    api.attendance
      .breakStart(token)
      .then((r: any) => {
        setMessage("Break started");
        fetchStatus();
      })
      .catch((e: any) => setError(e?.message || "Break start failed"))
      .finally(() => setClockBusy(false));
  };

  const handleBreakEnd = () => {
    if (!token) return;
    setClockBusy(true);
    setError(null);
    setMessage(null);
    api.attendance
      .breakEnd(token)
      .then((r: any) => {
        setMessage("Break ended");
        fetchStatus();
      })
      .catch((e: any) => setError(e?.message || "Break end failed"))
      .finally(() => setClockBusy(false));
  };

  const computedMyTotals = useMemo(() => {
    if (myTotals) {
      return {
        shifts: myTotals.shifts ?? myTotals.total_shifts ?? myShifts.length,
        hours: myTotals.hours ?? myTotals.total_hours ?? myShifts.reduce((a, s) => a + shiftDurationHours(s), 0),
        overtime: myTotals.overtime_hours ?? myTotals.overtime ?? myShifts.reduce((a, s) => a + shiftOvertimeHours(s), 0),
      };
    }
    return {
      shifts: myShifts.length,
      hours: myShifts.reduce((a, s) => a + shiftDurationHours(s), 0),
      overtime: myShifts.reduce((a, s) => a + shiftOvertimeHours(s), 0),
    };
  }, [myShifts, myTotals]);

  // Team grouping: rows may already be per-user summaries or flat per-shift rows
  const teamGrouped = useMemo(() => {
    if (teamRows.length === 0) return [];
    const looksGrouped = teamRows.some((r: any) => typeof r?.shifts === "number" || Array.isArray(r?.shifts));
    if (looksGrouped) {
      return teamRows.map((r: any) => ({
        key: r.user_id || r.user_name || r.name || r.email || Math.random().toString(),
        user_name: r.user_name || r.name || r.full_name || r.email || "Unknown",
        shifts: typeof r.shifts === "number" ? r.shifts : Array.isArray(r.shifts) ? r.shifts.length : 0,
        hours: Number(r.hours ?? r.total_hours ?? 0) || 0,
        overtime: Number(r.overtime ?? r.overtime_hours ?? 0) || 0,
        detail: Array.isArray(r.shifts) ? r.shifts : [],
      }));
    }
    const map = new Map<string, { user_name: string; shifts: any[] }>();
    for (const s of teamRows) {
      const key = String(s.user_id || s.user_name || s.user_email || "unknown");
      const label = s.user_name || s.full_name || s.user_email || s.email || "Unknown";
      if (!map.has(key)) map.set(key, { user_name: label, shifts: [] });
      map.get(key)!.shifts.push(s);
    }
    return Array.from(map.entries()).map(([key, v]) => ({
      key,
      user_name: v.user_name,
      shifts: v.shifts.length,
      hours: v.shifts.reduce((a, s) => a + shiftDurationHours(s), 0),
      overtime: v.shifts.reduce((a, s) => a + shiftOvertimeHours(s), 0),
      detail: v.shifts,
    }));
  }, [teamRows]);

  const tabs: { key: Tab; label: string }[] = [
    { key: "me", label: "My Time" },
    { key: "team", label: "Team" },
    { key: "clock", label: "Clock" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Clock className="h-7 w-7" /> Time & Attendance
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Clock in, track shifts and review team hours</p>
        </div>
      </div>

      <div className="flex gap-2 border-b border-zinc-800 pb-2">
        {tabs.map((t) => (
          <Button
            key={t.key}
            variant={tab === t.key ? "default" : "ghost"}
            size="sm"
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </Button>
        ))}
      </div>

      {message && (
        <Card className="border-green-500/40 bg-green-500/10">
          <CardContent className="py-3 text-sm text-green-300">{message}</CardContent>
        </Card>
      )}
      {error && (
        <Card className="border-red-500/40 bg-red-500/10">
          <CardContent className="py-3 text-sm text-red-300">{error}</CardContent>
        </Card>
      )}

      {tab === "clock" && (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className={`lg:col-span-2 ${clockedIn ? "border-green-500/40" : "border-zinc-800"}`}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Timer className="h-6 w-6" />
                {statusLoading ? "Checking status…" : clockedIn ? "You are clocked in" : "You are clocked out"}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center gap-4">
                <span
                  className={`inline-flex h-3 w-3 rounded-full ${clockedIn ? "bg-green-400 animate-pulse" : "bg-zinc-600"}`}
                />
                {clockedIn ? (
                  <Badge className="bg-green-500/20 text-green-400 border-green-500/30">On shift</Badge>
                ) : (
                  <Badge variant="secondary">Off shift</Badge>
                )}
                {onBreak && <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30 gap-1"><Coffee className="h-3 w-3" /> On break</Badge>}
              </div>

              <div className="text-center py-4">
                <p className="text-6xl font-mono font-bold tracking-tight">
                  {clockedIn && shiftStartMs != null ? formatElapsed(elapsedSecs) : "00:00"}
                </p>
                <p className="text-sm text-muted-foreground mt-2">
                  {clockedIn && activeShift
                    ? `Shift started ${fmtTime(activeShift.clock_in || activeShift.start_time)} • ${fmtDate(activeShift.clock_in || activeShift.start_time || new Date())}`
                    : "Press Clock In to start your shift"}
                </p>
                <p className="text-sm text-muted-foreground mt-1">Today: {fmtHours(todayHours)}</p>
              </div>

              <div>
                <label className="text-xs text-muted-foreground">Note (optional)</label>
                <Input
                  className="mt-1"
                  placeholder="e.g. Starting at client site in Leeds"
                  value={clockNote}
                  onChange={(e) => setClockNote(e.target.value)}
                />
                <p className="text-xs text-muted-foreground mt-1">Location is captured automatically if permitted.</p>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {!clockedIn ? (
                  <Button onClick={handleClockIn} disabled={clockBusy} className="gap-2">
                    <Play className="h-4 w-4" /> Clock In
                  </Button>
                ) : (
                  <Button onClick={handleClockOut} disabled={clockBusy} variant="destructive" className="gap-2">
                    <Square className="h-4 w-4" /> Clock Out
                  </Button>
                )}
                <Button onClick={handleBreakStart} disabled={clockBusy || !clockedIn || onBreak} variant="outline" className="gap-2">
                  <Coffee className="h-4 w-4" /> Break Start
                </Button>
                <Button onClick={handleBreakEnd} disabled={clockBusy || !clockedIn || !onBreak} variant="outline" className="gap-2">
                  <Coffee className="h-4 w-4" /> Break End
                </Button>
                <Button
                  variant="ghost"
                  className="gap-2"
                  onClick={() => {
                    setError(null);
                    fetchStatus();
                  }}
                >
                  <Timer className="h-4 w-4" /> Refresh
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Shift details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {!activeShift ? (
                <p className="text-muted-foreground">No active shift.</p>
              ) : (
                <>
                  <div className="flex justify-between"><span className="text-muted-foreground">Clock in</span><span>{fmtTime(activeShift.clock_in || activeShift.start_time)} {fmtDate(activeShift.clock_in || activeShift.start_time)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Location</span><span>{activeShift.latitude ? `${Number(activeShift.latitude).toFixed(4)}, ${Number(activeShift.longitude).toFixed(4)}` : "—"}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Notes</span><span className="text-right max-w-[60%] truncate">{activeShift.notes || "—"}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Breaks</span><span>{shiftBreaksLabel(activeShift)}</span></div>
                  <div className="flex justify-between"><span className="text-muted-foreground">Today&apos;s hours</span><span className="font-medium">{fmtHours(todayHours)}</span></div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {tab === "me" && (
        <div className="space-y-4">
          <Card>
            <CardContent className="pt-6 flex flex-wrap items-end gap-3">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <CalendarDays className="h-4 w-4" /> Date range
              </div>
              <div>
                <label className="text-xs text-muted-foreground">From</label>
                <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="mt-1" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">To</label>
                <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="mt-1" />
              </div>
              <Button
                size="sm"
                onClick={() => {
                  setError(null);
                  fetchMe();
                }}
              >
                Apply
              </Button>
            </CardContent>
          </Card>

          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">Shifts</p>
                <p className="text-3xl font-bold">{computedMyTotals.shifts}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">Hours</p>
                <p className="text-3xl font-bold">{fmtHours(computedMyTotals.hours)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">Overtime</p>
                <p className="text-3xl font-bold">{fmtHours(computedMyTotals.overtime)}</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">My shifts</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {myLoading ? (
                <p className="p-6 text-sm text-muted-foreground">Loading shifts…</p>
              ) : myShifts.length === 0 ? (
                <div className="py-12 text-center">
                  <Clock className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
                  <p className="font-medium">No shifts in range</p>
                  <p className="text-sm text-muted-foreground">Try widening the date range</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="p-3 font-medium">Date</th>
                      <th className="p-3 font-medium">Clock in</th>
                      <th className="p-3 font-medium">Clock out</th>
                      <th className="p-3 font-medium">Duration</th>
                      <th className="p-3 font-medium">Overtime</th>
                      <th className="p-3 font-medium">Breaks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {myShifts.map((s: any, i: number) => (
                      <tr key={s.id || `${s.clock_in || s.date}-${i}`} className="border-b last:border-0">
                        <td className="p-3">{fmtDate(s.date || s.clock_in || s.start_time)}</td>
                        <td className="p-3">{fmtTime(s.clock_in || s.start_time)}</td>
                        <td className="p-3">{s.clock_out || s.end_time ? fmtTime(s.clock_out || s.end_time) : <Badge variant="secondary">Open</Badge>}</td>
                        <td className="p-3 font-medium">{fmtHours(shiftDurationHours(s))}</td>
                        <td className="p-3">{fmtHours(shiftOvertimeHours(s))}</td>
                        <td className="p-3 text-muted-foreground">{shiftBreaksLabel(s)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {tab === "team" && (
        <div className="space-y-4">
          <Card>
            <CardContent className="pt-6 flex flex-wrap items-end gap-3">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Users className="h-4 w-4" /> Team date range
              </div>
              <div>
                <label className="text-xs text-muted-foreground">From</label>
                <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="mt-1" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">To</label>
                <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="mt-1" />
              </div>
              <Button
                size="sm"
                onClick={() => {
                  setError(null);
                  fetchTeam();
                }}
              >
                Apply
              </Button>
            </CardContent>
          </Card>

          {teamLoading ? (
            <p className="text-muted-foreground">Loading team…</p>
          ) : teamGrouped.length === 0 ? (
            <Card>
              <CardContent className="py-16 text-center">
                <Users className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="text-lg font-medium">No team records</h3>
                <p className="text-sm text-muted-foreground mt-1">No shifts found for this period</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {teamGrouped.map((m: any) => (
                <Card key={m.key}>
                  <CardHeader>
                    <CardTitle className="text-base flex flex-wrap items-center gap-2">
                      <Users className="h-4 w-4" /> {m.user_name}
                      <Badge variant="secondary">{m.shifts} shift{m.shifts !== 1 ? "s" : ""}</Badge>
                      <Badge className="bg-green-500/20 text-green-400">{fmtHours(m.hours)}</Badge>
                      {Number(m.overtime) > 0 && (
                        <Badge className="bg-amber-500/20 text-amber-400">+{fmtHours(m.overtime)} OT</Badge>
                      )}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    {m.detail.length === 0 ? (
                      <p className="px-6 pb-6 text-sm text-muted-foreground">Summary only — no per-shift rows.</p>
                    ) : (
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b text-left text-muted-foreground">
                            <th className="p-3 font-medium">Date</th>
                            <th className="p-3 font-medium">Clock in</th>
                            <th className="p-3 font-medium">Clock out</th>
                            <th className="p-3 font-medium">Duration</th>
                            <th className="p-3 font-medium">Overtime</th>
                          </tr>
                        </thead>
                        <tbody>
                          {m.detail.map((s: any, i: number) => (
                            <tr key={s.id || `${s.clock_in || s.date}-${i}`} className="border-b last:border-0">
                              <td className="p-3">{fmtDate(s.date || s.clock_in || s.start_time)}</td>
                              <td className="p-3">{fmtTime(s.clock_in || s.start_time)}</td>
                              <td className="p-3">{s.clock_out || s.end_time ? fmtTime(s.clock_out || s.end_time) : "—"}</td>
                              <td className="p-3">{fmtHours(shiftDurationHours(s))}</td>
                              <td className="p-3">{fmtHours(shiftOvertimeHours(s))}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
