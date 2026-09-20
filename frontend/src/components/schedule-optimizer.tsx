"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/lib/store";
import { api, apiRequest } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface Job {
  id: string;
  title: string;
  status: string;
  scheduled_at: string | null;
  postcode?: string;
}

interface Technician {
  id: string;
  user_id: string;
  full_name: string;
  skills: string | null;
  current_latitude: number | null;
  current_longitude: number | null;
  is_available: boolean;
}

interface Assignment {
  technician_id: string;
  technician_name: string;
  estimated_travel_minutes: number;
  departure_time: string;
}

export function ScheduleOptimizer() {
  const { token } = useAuth();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [technicians, setTechnicians] = useState<Technician[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [autoResult, setAutoResult] = useState<{
    assigned: { job_id: string; technician_id: string }[];
    unassigned: string[];
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [selectedTech, setSelectedTech] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!token) return;
    try {
      const [jobsRes, techsRes]: any[] = await Promise.all([
        api.jobs.list(token, "scheduled"),
        api.realtime.dispatchBoard(token),
      ]);
      setJobs(Array.isArray(jobsRes) ? jobsRes : []);
      // dispatchBoard may return { technicians: [...] } or array directly
      const techList = Array.isArray(techsRes)
        ? techsRes
        : techsRes?.technicians || [];
      setTechnicians(techList);
    } catch (e) {
      console.error("Failed to load scheduling data", e);
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAutoAssign = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res: any = await apiRequest("/api/scheduling/auto-assign", {
        method: "POST",
        token,
      });
      setAutoResult(res);
      loadData();
    } catch (e) {
      console.error("Auto-assign failed", e);
    } finally {
      setLoading(false);
    }
  };

  const handleOptimize = async () => {
    if (!token || !selectedJob) return;
    setLoading(true);
    try {
      const res: any = await apiRequest("/api/scheduling/optimize", {
        method: "POST",
        body: JSON.stringify({
          job_id: selectedJob,
          technician_ids: technicians.map((t) => t.id),
        }),
        token,
      });
      setAssignments(res.assignments || []);
    } catch (e) {
      console.error("Optimization failed", e);
    } finally {
      setLoading(false);
    }
  };

  const handleManualAssign = async () => {
    if (!token || !selectedJob || !selectedTech) return;
    setLoading(true);
    try {
      await api.jobs.assign(selectedJob, selectedTech, token);
      setSelectedJob(null);
      setSelectedTech(null);
      setAssignments([]);
      loadData();
    } catch (e) {
      console.error("Manual assign failed", e);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (d: string | null) => {
    if (!d) return "—";
    return new Date(d).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Schedule Optimizer</h1>
        <Button onClick={handleAutoAssign} disabled={loading}>
          {loading ? "Assigning..." : "Auto-Assign All"}
        </Button>
      </div>

      {/* Auto-assign results */}
      {autoResult && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Auto-Assign Results</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-4 mb-3">
              <Badge variant="default">{autoResult.assigned.length} assigned</Badge>
              <Badge variant="destructive">{autoResult.unassigned.length} unassigned</Badge>
            </div>
            {autoResult.assigned.length > 0 && (
              <ul className="text-sm space-y-1">
                {autoResult.assigned.map((a) => (
                  <li key={a.job_id} className="text-muted-foreground">
                    Job <span className="font-mono">{a.job_id.slice(0, 8)}</span> → Tech{" "}
                    <span className="font-mono">{a.technician_id.slice(0, 8)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Unassigned Jobs */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Unassigned Jobs</CardTitle>
          </CardHeader>
          <CardContent>
            {jobs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No unassigned jobs today.</p>
            ) : (
              <ul className="space-y-2">
                {jobs.map((job) => (
                  <li
                    key={job.id}
                    onClick={() => setSelectedJob(job.id)}
                    className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                      selectedJob === job.id
                        ? "border-primary bg-primary/5"
                        : "hover:bg-muted"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-sm">{job.title}</span>
                      <Badge variant="outline">{job.status}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {formatDate(job.scheduled_at)}
                      {job.postcode && ` • ${job.postcode}`}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Technicians */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Available Technicians</CardTitle>
          </CardHeader>
          <CardContent>
            {technicians.length === 0 ? (
              <p className="text-sm text-muted-foreground">No technicians available.</p>
            ) : (
              <ul className="space-y-2">
                {technicians.map((tech) => (
                  <li
                    key={tech.id}
                    onClick={() => setSelectedTech(tech.id)}
                    className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                      selectedTech === tech.id
                        ? "border-primary bg-primary/5"
                        : "hover:bg-muted"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-sm">{tech.full_name}</span>
                      {tech.is_available ? (
                        <Badge variant="default">Available</Badge>
                      ) : (
                        <Badge variant="secondary">Busy</Badge>
                      )}
                    </div>
                    {tech.skills && (
                      <p className="text-xs text-muted-foreground mt-1">
                        Skills: {tech.skills}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Manual Assignment + Optimization */}
      <div className="flex gap-4">
        <Button
          onClick={handleOptimize}
          disabled={!selectedJob || loading}
          variant="outline"
        >
          Optimize for Job
        </Button>
        <Button
          onClick={handleManualAssign}
          disabled={!selectedJob || !selectedTech || loading}
          variant="secondary"
        >
          Assign Selected
        </Button>
        {selectedJob && selectedTech && (
          <Button onClick={() => { setSelectedJob(null); setSelectedTech(null); setAssignments([]); }} variant="ghost" size="sm">
            Clear Selection
          </Button>
        )}
      </div>

      {/* Optimization Results */}
      {assignments.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Optimization Results</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {assignments.map((a, i) => (
                <li
                  key={a.technician_id}
                  className="flex items-center justify-between p-3 rounded-lg border"
                >
                  <div>
                    <span className="font-medium text-sm">
                      {i + 1}. {a.technician_name}
                    </span>
                    <p className="text-xs text-muted-foreground">
                      Departs {formatDate(a.departure_time)}
                    </p>
                  </div>
                  <Badge variant={i === 0 ? "default" : "secondary"}>
                    ~{a.estimated_travel_minutes} min travel
                  </Badge>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
