"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  Calendar,
  RefreshCw,
  CheckCircle2,
  ExternalLink,
  Globe,
} from "lucide-react";

const FullCalendar = dynamic(() => import("@fullcalendar/react"), { ssr: false });

interface CalendarStatus {
  google: boolean;
  outlook: boolean;
  last_synced: string | null;
}

interface Job {
  id: string;
  title: string;
  date: string;
  customer: string;
  status: string;
}

const statusColors: Record<string, string> = {
  scheduled: "bg-blue-500/20 text-blue-400",
  confirmed: "bg-green-500/20 text-green-400",
  in_progress: "bg-yellow-500/20 text-yellow-400",
  completed: "bg-zinc-500/20 text-zinc-400",
};

function ProviderCard({
  name,
  icon,
  connected,
  onConnect,
  onDisconnect,
  loading,
}: {
  name: string;
  icon: React.ReactNode;
  connected: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-lg font-medium">{name}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-2">
          {connected ? (
            <CheckCircle2 className="h-4 w-4 text-green-400" />
          ) : (
            <Globe className="h-4 w-4 text-muted-foreground" />
          )}
          <span className="text-sm text-muted-foreground">
            {connected ? "Connected" : "Not connected"}
          </span>
        </div>
        {connected ? (
          <Button
            variant="destructive"
            size="sm"
            onClick={onDisconnect}
            disabled={loading}
          >
            Disconnect
          </Button>
        ) : (
          <Button size="sm" onClick={onConnect} disabled={loading} className="gap-2">
            <ExternalLink className="h-3 w-3" />
            Connect
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function ToggleRow({
  label,
  description,
  enabled,
  onToggle,
}: {
  label: string;
  description: string;
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="flex items-center justify-between py-2">
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <button
        onClick={onToggle}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
          enabled ? "bg-primary" : "bg-zinc-600"
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            enabled ? "translate-x-6" : "translate-x-1"
          }`}
        />
      </button>
    </div>
  );
}

export default function CalendarPage() {
  const { token } = useAuth();
  const router = useRouter();
  const [view, setView] = useState<"diary" | "sync">("diary");
  const [status, setStatus] = useState<CalendarStatus>({
    google: false,
    outlook: false,
    last_synced: null,
  });
  const [jobs, setJobs] = useState<Job[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [providerLoading, setProviderLoading] = useState<string | null>(null);
  const [syncedCount, setSyncedCount] = useState<number | null>(null);

  const [autoSync, setAutoSync] = useState(true);
  const [includeQuotes, setIncludeQuotes] = useState(false);
  const [includeBreaks, setIncludeBreaks] = useState(false);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      api.calendar.status(token).catch(() => ({
        google: false,
        outlook: false,
        last_synced: null,
      })),
      api.jobs.list(token).catch(() => ({ jobs: [] })),
    ]).then(([statusRes, jobsRes]: any) => {
      setStatus(statusRes as CalendarStatus);
      const raw: any = jobsRes as any;
      setJobs(Array.isArray(raw) ? raw : raw?.jobs || []);
    });
  }, [token]);

  const handleConnect = async (provider: "google" | "outlook") => {
    if (!token) return;
    setProviderLoading(provider);
    try {
      const res: any = await api.calendar[`${provider}Auth`](token);
      if (res.auth_url) {
        window.open(res.auth_url, "_blank");
      }
    } catch {
    } finally {
      setProviderLoading(null);
    }
  };

  const handleDisconnect = (provider: "google" | "outlook") => {
    setStatus((prev) => ({ ...prev, [provider]: false }));
  };

  const handleSync = async (provider: "google" | "outlook") => {
    if (!token) return;
    setSyncing(true);
    setSyncedCount(null);
    try {
      const res: any = await api.calendar.sync(provider, token);
      setSyncedCount(res.synced);
      setStatus((prev) => ({
        ...prev,
        last_synced: new Date().toISOString(),
      }));
    } catch {
    } finally {
      setSyncing(false);
    }
  };

  const formatTime = (iso: string | null) => {
    if (!iso) return "Never";
    const d = new Date(iso);
    return d.toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const connectedProvider = status.google
    ? "google"
    : status.outlook
      ? "outlook"
      : null;

  const eventStatusColor = (s: string) => {
    switch ((s || "").toLowerCase()) {
      case "confirmed":
        return "#22c55e";
      case "in_progress":
        return "#eab308";
      case "completed":
        return "#71717a";
      case "cancelled":
        return "#ef4444";
      default:
        return "#3b82f6";
    }
  };

  const events = useMemo(
    () =>
      (jobs as any[])
        .map((j: any) => {
          const date =
            j?.date || j?.scheduled_date || j?.scheduled_at || j?.start || j?.created_at;
          if (!date) return null;
          const color = eventStatusColor(j?.status || "");
          return {
            id: String(j.id),
            title: j?.title || j?.name || "Job",
            date,
            backgroundColor: color,
            borderColor: color,
          };
        })
        .filter(Boolean),
    [jobs]
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Calendar Sync</h1>
      </div>

      <div className="flex gap-2 border-b border-zinc-800 pb-2">
        <Button
          variant={view === "diary" ? "default" : "ghost"}
          size="sm"
          onClick={() => setView("diary")}
        >
          Diary
        </Button>
        <Button
          variant={view === "sync" ? "default" : "ghost"}
          size="sm"
          onClick={() => setView("sync")}
        >
          Sync & Settings
        </Button>
      </div>

      {view === "diary" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Diary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4 text-zinc-100 [&_.fc]:text-zinc-100 [&_.fc-theme-standard_td]:border-zinc-800 [&_.fc-theme-standard_th]:border-zinc-800 [&_.fc-scrollgrid]:border-zinc-800 [&_.fc-button]:bg-zinc-800 [&_.fc-button]:border-zinc-700 [&_.fc-button-primary:not(:disabled).fc-button-active]:bg-primary">
              <FullCalendar
                plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
                initialView="dayGridMonth"
                headerToolbar={{
                  left: "prev,next today",
                  center: "title",
                  right: "dayGridMonth,timeGridWeek",
                }}
                events={events as any}
                eventClick={(info: any) => router.push(`/jobs/${info.event.id}`)}
                height="auto"
              />
            </div>
          </CardContent>
        </Card>
      )}

      {view === "sync" && (
        <>
      <div className="grid gap-4 md:grid-cols-2">
        <ProviderCard
          name="Google Calendar"
          icon={<Calendar className="h-5 w-5 text-muted-foreground" />}
          connected={status.google}
          onConnect={() => handleConnect("google")}
          onDisconnect={() => handleDisconnect("google")}
          loading={providerLoading === "google"}
        />
        <ProviderCard
          name="Microsoft Outlook"
          icon={<Calendar className="h-5 w-5 text-muted-foreground" />}
          connected={status.outlook}
          onConnect={() => handleConnect("outlook")}
          onDisconnect={() => handleDisconnect("outlook")}
          loading={providerLoading === "outlook"}
        />
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-lg">Sync Controls</CardTitle>
          <RefreshCw
            className={`h-4 w-4 text-muted-foreground ${syncing ? "animate-spin" : ""}`}
          />
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Last synced</p>
              <p className="text-xs text-muted-foreground">
                {formatTime(status.last_synced)}
              </p>
            </div>
            {syncedCount !== null && (
              <Badge variant="secondary">{syncedCount} synced</Badge>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={!connectedProvider || syncing}
              onClick={() => connectedProvider && handleSync(connectedProvider)}
              className="gap-2"
            >
              <RefreshCw
                className={`h-3 w-3 ${syncing ? "animate-spin" : ""}`}
              />
              {syncing ? "Syncing..." : "Sync Now"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Upcoming Jobs</CardTitle>
          </CardHeader>
          <CardContent>
            {jobs.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                No upcoming jobs
              </p>
            ) : (
              <div className="space-y-3">
                {jobs.slice(0, 8).map((job) => (
                  <div
                    key={job.id}
                    className="flex items-center justify-between rounded-lg border p-3"
                  >
                    <div className="space-y-1">
                      <p className="text-sm font-medium">{job.title}</p>
                      <p className="text-xs text-muted-foreground">
                        {job.customer}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {new Date(job.date).toLocaleDateString("en-GB", {
                          day: "2-digit",
                          month: "short",
                        })}
                      </span>
                      <Badge
                        className={
                          statusColors[job.status] ||
                          "bg-zinc-500/20 text-zinc-400"
                        }
                      >
                        {job.status}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Sync Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            <ToggleRow
              label="Auto-sync"
              description="Automatically sync new jobs to your calendar"
              enabled={autoSync}
              onToggle={() => setAutoSync(!autoSync)}
            />
            <ToggleRow
              label="Include quotes"
              description="Sync scheduled quotes as calendar events"
              enabled={includeQuotes}
              onToggle={() => setIncludeQuotes(!includeQuotes)}
            />
            <ToggleRow
              label="Include breaks"
              description="Sync lunch breaks and rest periods"
              enabled={includeBreaks}
              onToggle={() => setIncludeBreaks(!includeBreaks)}
            />
          </CardContent>
        </Card>
      </div>
        </>
      )}
    </div>
  );
}
