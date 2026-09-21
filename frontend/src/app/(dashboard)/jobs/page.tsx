"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { formatCurrency, getStatusColor, getStatusLabel, formatDateTime } from "@/lib/utils";
import { Plus, Search, Briefcase, MapPin, Clock, User } from "lucide-react";

export default function JobsPage() {
  const { token } = useAuth();
  const [jobs, setJobs] = useState<any[]>([]);
  const [filter, setFilter] = useState("");
  const [search, setSearch] = useState("");
  const [lateJobId, setLateJobId] = useState<string | null>(null);
  const [lateMins, setLateMins] = useState("30");
  const [lateStatus, setLateStatus] = useState<
    "idle" | "sending" | "sent" | "error"
  >("idle");
  const [lateMsg, setLateMsg] = useState("");

  useEffect(() => {
    if (!token) return;
    loadJobs();
  }, [token, filter]);

  const loadJobs = async () => {
    try {
      const data: any = await api.jobs.list(token!, filter || undefined);
      setJobs(data);
    } catch (e) {
      console.error(e);
    }
  };

  const updateStatus = async (jobId: string, status: string) => {
    try {
      await api.jobs.updateStatus(jobId, status, token!);
      loadJobs();
    } catch (e) {
      console.error(e);
    }
  };

  const toggleLate = (jobId: string) => {
    if (lateJobId === jobId) {
      setLateJobId(null);
      return;
    }
    setLateJobId(jobId);
    setLateMins("30");
    setLateStatus("idle");
    setLateMsg("");
  };

  const sendRunningLate = (job: any) => {
    if (!token || lateStatus === "sending") return;
    const mins = parseInt(lateMins, 10) || 30;
    setLateStatus("sending");
    setLateMsg("");
    const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
    const eta = new Date(Date.now() + mins * 60000).toLocaleTimeString(
      "en-GB",
      { hour: "2-digit", minute: "2-digit" }
    );
    const buildAndSend = (phone: string, name: string) => {
      const text = `Hi ${name}, your Allo engineer is running ~${mins} late. New ETA ${eta}. Reply to this text if that doesn't work.`;
      fetch(
        `${API}/api/sms/send?to_phone=${encodeURIComponent(
          phone
        )}&message=${encodeURIComponent(text)}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      )
        .then((r: any) => r.json())
        .then((r: any) => {
          if (r && (r.success === true || r.sid)) {
            setLateStatus("sent");
            setLateMsg(`Customer texted — running ${mins} min late, new ETA ${eta}.`);
          } else {
            setLateStatus("error");
            setLateMsg(r?.error || "Text failed to send. Please try again.");
          }
        })
        .catch((e: any) => {
          setLateStatus("error");
          setLateMsg(e?.message || "Text failed to send. Please try again.");
        });
    };
    const directPhone: string | null = job.customer_phone || job.phone || null;
    const directName: string = job.customer_name || "there";
    if (directPhone) {
      buildAndSend(directPhone, directName);
      return;
    }
    if (!job.customer_id) {
      setLateStatus("error");
      setLateMsg("No phone on file for this customer.");
      return;
    }
    api.customers
      .get(job.customer_id, token!)
      .then((r: any) => {
        if (!r?.phone) {
          setLateStatus("error");
          setLateMsg("No phone on file for this customer.");
          return;
        }
        buildAndSend(r.phone, r.full_name || directName);
      })
      .catch((e: any) => {
        console.error(e);
        setLateStatus("error");
        setLateMsg("No phone on file for this customer.");
      });
  };

  const filteredJobs = jobs.filter(
    (j) =>
      j.title.toLowerCase().includes(search.toLowerCase()) ||
      j.description?.toLowerCase().includes(search.toLowerCase())
  );

  const statusFilters = [
    { value: "", label: "All" },
    { value: "scheduled", label: "Scheduled" },
    { value: "in_progress", label: "In Progress" },
    { value: "completed", label: "Completed" },
    { value: "quote_requested", label: "Quote Requested" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Jobs</h1>
          <p className="text-muted-foreground">Manage your field service jobs</p>
        </div>
        <a href="/quote">
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            New Job
          </Button>
        </a>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-4 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search jobs..."
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          {statusFilters.map((sf) => (
            <Button
              key={sf.value}
              variant={filter === sf.value ? "default" : "outline"}
              size="sm"
              onClick={() => setFilter(sf.value)}
            >
              {sf.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Jobs List */}
      <div className="space-y-3">
        {filteredJobs.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              No jobs found. Create your first job with AI Voice Quote.
            </CardContent>
          </Card>
        ) : (
          filteredJobs.map((job: any) => (
            <Card key={job.id} className="hover:border-primary/30 transition-all">
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 shrink-0">
                      <Briefcase className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-lg">{job.title}</h3>
                      {job.description && (
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-1">
                          {job.description}
                        </p>
                      )}
                      <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {formatDateTime(job.created_at)}
                        </span>
                        {job.scheduled_at && (
                          <span className="flex items-center gap-1">
                            <MapPin className="h-3 w-3" />
                            Scheduled: {formatDateTime(job.scheduled_at)}
                          </span>
                        )}
                        {job.estimated_cost && (
                          <span className="font-medium text-foreground">
                            {formatCurrency(job.estimated_cost)}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <Badge className={getStatusColor(job.status)}>
                      {getStatusLabel(job.status)}
                    </Badge>
                    <div className="flex gap-1">
                      {job.status === "scheduled" && (
                        <Button size="sm" variant="outline" onClick={() => updateStatus(job.id, "in_progress")}>
                          Start
                        </Button>
                      )}
                      {job.status === "in_progress" && (
                        <Button size="sm" onClick={() => updateStatus(job.id, "completed")}>
                          Complete
                        </Button>
                      )}
                      <Button size="sm" variant="outline" onClick={() => toggleLate(job.id)} className="gap-1">
                        <Clock className="h-3.5 w-3.5" />
                        Running late
                      </Button>
                    </div>
                  </div>
                </div>
                {lateJobId === job.id && (
                  <div className="mt-3 rounded-lg border bg-muted/30 p-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:flex-wrap">
                    <select
                      value={lateMins}
                      onChange={(e) => setLateMins(e.target.value)}
                      className="rounded-lg border bg-background px-2 py-1.5 text-sm"
                      aria-label="Minutes late"
                    >
                      <option value="15">15 min late</option>
                      <option value="30">30 min late</option>
                      <option value="45">45 min late</option>
                      <option value="60">60 min late</option>
                    </select>
                    <Button
                      size="sm"
                      onClick={() => sendRunningLate(job)}
                      disabled={lateStatus === "sending"}
                    >
                      {lateStatus === "sending" ? "Sending…" : "Send text"}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setLateJobId(null)}
                    >
                      Cancel
                    </Button>
                    {lateStatus === "sent" && (
                      <span className="text-xs text-emerald-500">{lateMsg}</span>
                    )}
                    {lateStatus === "error" && (
                      <span className="text-xs text-destructive">{lateMsg}</span>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
