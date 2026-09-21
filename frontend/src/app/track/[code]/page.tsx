"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { QRCodeSVG } from "qrcode.react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  MapPin, Clock, User, Share2, CheckCircle2, Circle,
  Truck, Home, Wrench, ArrowRight, Copy, Link2,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface TrackingData {
  job_title: string;
  status: string;
  technician_name: string | null;
  technician_photo_url: string | null;
  estimated_arrival_minutes: number | null;
  distance_miles: number | null;
  scheduled_at: string | null;
  technician_location: { lat: number; lng: number } | null;
  job_location: { lat: number; lng: number } | null;
  timeline: Array<{
    action: string;
    description: string;
    created_at: string;
  }>;
}

const STATUS_CONFIG: Record<
  string,
  { label: string; color: string; bg: string; icon: typeof Clock }
> = {
  quote_requested: { label: "Requested", color: "text-yellow-400", bg: "bg-yellow-400/10", icon: Clock },
  quote_sent: { label: "Quote Sent", color: "text-blue-400", bg: "bg-blue-400/10", icon: Clock },
  quote_approved: { label: "Approved", color: "text-green-400", bg: "bg-green-400/10", icon: CheckCircle2 },
  scheduled: { label: "Booked", color: "text-purple-400", bg: "bg-purple-400/10", icon: Calendar },
  in_progress: { label: "In Progress", color: "text-orange-400", bg: "bg-orange-400/10", icon: Wrench },
  completed: { label: "Completed", color: "text-green-400", bg: "bg-green-400/10", icon: CheckCircle2 },
  invoiced: { label: "Invoiced", color: "text-blue-400", bg: "bg-blue-400/10", icon: CheckCircle2 },
  paid: { label: "Paid", color: "text-green-400", bg: "bg-green-400/10", icon: CheckCircle2 },
  cancelled: { label: "Cancelled", color: "text-red-400", bg: "bg-red-400/10", icon: Circle },
};

const TIMELINE_STEPS = [
  { key: "scheduled", label: "Booked", icon: Home },
  { key: "technician_assigned", label: "Engineer Assigned", icon: User },
  { key: "en_route", label: "En Route", icon: Truck },
  { key: "in_progress", label: "Arrived", icon: Wrench },
  { key: "completed", label: "Completed", icon: CheckCircle2 },
];

function Calendar(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M8 2v4" /><path d="M16 2v4" /><rect width="18" height="18" x="3" y="4" rx="2" /><path d="M3 10h18" />
    </svg>
  );
}

export default function TrackingPage() {
  const params = useParams();
  const code = params.code as string;
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const techMarker = useRef<maplibregl.Marker | null>(null);
  const jobMarker = useRef<maplibregl.Marker | null>(null);

  const [data, setData] = useState<TrackingData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchTracking = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/tracking/share/${code}`);
      if (!res.ok) throw new Error("Invalid tracking link");
      const json = await res.json();
      setData(json);
      if (json.estimated_arrival_minutes) {
        setCountdown(json.estimated_arrival_minutes);
      }
      setError(null);
    } catch (e: any) {
      setError(e.message || "Failed to load tracking");
    } finally {
      setLoading(false);
    }
  }, [code]);

  useEffect(() => {
    fetchTracking();
    const interval = setInterval(fetchTracking, 15000);
    return () => clearInterval(interval);
  }, [fetchTracking]);

  // Countdown timer
  useEffect(() => {
    if (countdown === null || countdown <= 0) return;
    const timer = setInterval(() => {
      setCountdown((prev) => (prev !== null && prev > 0 ? prev - 1 : 0));
    }, 60000);
    return () => clearInterval(timer);
  }, [countdown]);

  // Map initialization
  useEffect(() => {
    if (!mapContainer.current || !data?.technician_location || !data?.job_location) return;

    if (map.current) {
      // Update existing map
      if (techMarker.current) {
        techMarker.current.setLngLat([
          data.technician_location.lng,
          data.technician_location.lat,
        ]);
      }
      if (jobMarker.current) {
        map.current.fitBounds(
          new maplibregl.LngLatBounds()
            .extend([data.technician_location.lng, data.technician_location.lat])
            .extend([data.job_location.lng, data.job_location.lat]),
          { padding: 80 }
        );
      }
      return;
    }

    const techLng = data.technician_location.lng;
    const techLat = data.technician_location.lat;
    const jobLng = data.job_location.lng;
    const jobLat = data.job_location.lat;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [(techLng + jobLng) / 2, (techLat + jobLat) / 2],
      zoom: 12,
      attributionControl: false,
    });

    map.current.addControl(new maplibregl.NavigationControl(), "top-right");

    // Technician marker - pulsing dot
    const techEl = document.createElement("div");
    techEl.innerHTML = `
      <div style="position:relative;width:48px;height:48px;">
        <div style="position:absolute;inset:0;border-radius:50%;background:rgba(249,115,22,0.2);animation:pulse-ring 2s ease-out infinite;"></div>
        <div style="position:absolute;inset:8px;border-radius:50%;background:#f97316;border:3px solid white;box-shadow:0 2px 12px rgba(249,115,22,0.5);display:flex;align-items:center;justify-content:center;">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.5 2.8C1.4 11.3 1 12.2 1 13v3c0 .6.4 1 1 1h2"/>
            <circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/>
          </svg>
        </div>
      </div>
    `;
    techEl.style.cssText = "cursor:pointer;";

    techMarker.current = new maplibregl.Marker({ element: techEl })
      .setLngLat([techLng, techLat])
      .setPopup(
        new maplibregl.Popup({ offset: 30 }).setHTML(
          `<div style="padding:8px 12px;font-size:13px;font-weight:500;">${data.technician_name || "Engineer"}</div>`
        )
      )
      .addTo(map.current);

    // Job marker
    const jobEl = document.createElement("div");
    jobEl.innerHTML = `
      <div style="width:40px;height:40px;border-radius:50%;background:#a855f7;border:3px solid white;box-shadow:0 2px 12px rgba(168,85,247,0.5);display:flex;align-items:center;justify-content:center;">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>
        </svg>
      </div>
    `;
    jobEl.style.cssText = "cursor:pointer;";

    jobMarker.current = new maplibregl.Marker({ element: jobEl })
      .setLngLat([jobLng, jobLat])
      .setPopup(
        new maplibregl.Popup({ offset: 30 }).setHTML(
          `<div style="padding:8px 12px;font-size:13px;font-weight:500;">Your Location</div>`
        )
      )
      .addTo(map.current);

    // Fit bounds
    map.current.fitBounds(
      new maplibregl.LngLatBounds()
        .extend([techLng, techLat])
        .extend([jobLng, jobLat]),
      { padding: 80 }
    );

    return () => {
      map.current?.remove();
      map.current = null;
    };
  }, [data]);

  const copyLink = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const pageUrl = typeof window !== "undefined" ? window.location.href : "";

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#09090b]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-purple-500/30 border-t-purple-500 rounded-full animate-spin" />
          <p className="text-sm text-muted-foreground">Loading tracking...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#09090b]">
        <Card className="w-full max-w-md mx-4">
          <CardContent className="py-12 text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center mx-auto">
              <Circle className="h-8 w-8 text-red-400" />
            </div>
            <h1 className="text-xl font-semibold">Link Expired</h1>
            <p className="text-sm text-muted-foreground">
              {error || "This tracking link is no longer valid."}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const statusInfo = STATUS_CONFIG[data.status] || STATUS_CONFIG.scheduled;
  const StatusIcon = statusInfo.icon;
  const isEnRoute = data.status === "in_progress" && data.estimated_arrival_minutes !== null;
  const activeStepIndex = TIMELINE_STEPS.findIndex((s) => {
    if (data.status === "completed") return s.key === "completed";
    if (data.status === "in_progress") return s.key === "in_progress";
    if (data.status === "scheduled") return s.key === "scheduled";
    return false;
  });

  return (
    <>
      <style>{`
        @keyframes pulse-ring {
          0% { transform: scale(0.8); opacity: 1; }
          100% { transform: scale(2.2); opacity: 0; }
        }
        @keyframes float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-6px); }
        }
        .animate-float { animation: float 3s ease-in-out infinite; }
        @keyframes gradient-shift {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }
        .animate-gradient {
          background-size: 200% 200%;
          animation: gradient-shift 3s ease infinite;
        }
      `}</style>

      <div className="min-h-screen bg-[#09090b]">
        {/* Header */}
        <header className="sticky top-0 z-50 border-b border-white/5 bg-[#09090b]/80 backdrop-blur-xl">
          <div className="max-w-2xl mx-auto px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
                <Wrench className="h-4 w-4 text-white" />
              </div>
              <span className="text-sm font-semibold tracking-tight">Allo</span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={copyLink}
              className="gap-2 text-muted-foreground hover:text-foreground"
            >
              {copied ? (
                <CheckCircle2 className="h-4 w-4 text-green-400" />
              ) : (
                <Share2 className="h-4 w-4" />
              )}
              {copied ? "Copied" : "Share"}
            </Button>
          </div>
        </header>

        <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
          {/* Status Card */}
          <div className="animate-fade-in">
            <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-white/[0.07] to-white/[0.02] border border-white/10 p-6">
              <div className="absolute -top-20 -right-20 w-40 h-40 bg-purple-500/10 rounded-full blur-3xl" />
              <div className="relative space-y-4">
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                      Tracking Job
                    </p>
                    <h1 className="text-xl font-bold tracking-tight">{data.job_title}</h1>
                  </div>
                  <Badge
                    className={`${statusInfo.bg} ${statusInfo.color} border-0 text-xs font-semibold px-3 py-1`}
                  >
                    <StatusIcon className="h-3 w-3 mr-1" />
                    {statusInfo.label}
                  </Badge>
                </div>

                {data.scheduled_at && (
                  <p className="text-sm text-muted-foreground flex items-center gap-1.5">
                    <Calendar className="h-3.5 w-3.5" />
                    Scheduled:{" "}
                    {new Date(data.scheduled_at).toLocaleDateString("en-GB", {
                      weekday: "short",
                      day: "numeric",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* ETA Card */}
          {isEnRoute && countdown !== null && countdown > 0 && (
            <div className="animate-slide-up">
              <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-orange-500/20 via-orange-500/5 to-transparent border border-orange-500/20 p-6">
                <div className="absolute -bottom-10 -left-10 w-32 h-32 bg-orange-500/10 rounded-full blur-2xl" />
                <div className="relative flex items-center gap-6">
                  <div className="animate-float">
                    <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-orange-500 to-red-500 flex items-center justify-center shadow-lg shadow-orange-500/20">
                      <Truck className="h-10 w-10 text-white" />
                    </div>
                  </div>
                  <div className="flex-1 space-y-1">
                    <p className="text-xs font-medium uppercase tracking-wider text-orange-300/70">
                      Engineer En Route
                    </p>
                    <div className="flex items-baseline gap-2">
                      <span className="text-4xl font-bold tabular-nums text-white">
                        {countdown}
                      </span>
                      <span className="text-sm text-orange-300/70 font-medium">
                        min away
                      </span>
                    </div>
                    {data.distance_miles && (
                      <p className="text-xs text-muted-foreground">
                        {data.distance_miles} miles away
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Map */}
          {data.technician_location && data.job_location && (
            <div className="animate-slide-up-delay">
              <div
                ref={mapContainer}
                className="w-full h-[300px] rounded-2xl border border-white/10 overflow-hidden"
              />
            </div>
          )}

          {/* Technician Card */}
          {data.technician_name && (
            <div className="animate-slide-up-delay-2">
              <Card>
                <CardContent className="py-4 flex items-center gap-4">
                  <div className="w-12 h-12 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white font-bold text-lg shrink-0">
                    {data.technician_name.charAt(0)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold truncate">{data.technician_name}</p>
                    <p className="text-xs text-muted-foreground">Your Engineer</p>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-green-400">
                    <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                    Active
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Status Timeline */}
          <div className="animate-slide-up-delay-3">
            <Card>
              <CardContent className="py-6">
                <h3 className="text-sm font-semibold mb-6 text-muted-foreground uppercase tracking-wider">
                  Progress
                </h3>
                <div className="relative">
                  {TIMELINE_STEPS.map((step, i) => {
                    const isCompleted =
                      data.status === "completed" ||
                      (activeStepIndex >= 0 && i <= activeStepIndex);
                    const isCurrent =
                      activeStepIndex >= 0 && i === activeStepIndex;
                    const StepIcon = step.icon;

                    return (
                      <div key={step.key} className="flex gap-4 pb-8 last:pb-0">
                        {/* Vertical line + dot */}
                        <div className="flex flex-col items-center">
                          <div
                            className={`
                              w-10 h-10 rounded-full flex items-center justify-center shrink-0
                              transition-all duration-500
                              ${
                                isCurrent
                                  ? "bg-gradient-to-br from-purple-500 to-pink-500 shadow-lg shadow-purple-500/25"
                                  : isCompleted
                                  ? "bg-green-500/20 border border-green-500/30"
                                  : "bg-white/5 border border-white/10"
                              }
                            `}
                          >
                            <StepIcon
                              className={`h-4 w-4 ${
                                isCurrent
                                  ? "text-white"
                                  : isCompleted
                                  ? "text-green-400"
                                  : "text-muted-foreground"
                              }`}
                            />
                          </div>
                          {i < TIMELINE_STEPS.length - 1 && (
                            <div
                              className={`w-0.5 flex-1 mt-2 rounded-full transition-all duration-500 ${
                                isCompleted && i < activeStepIndex
                                  ? "bg-green-500/40"
                                  : isCurrent
                                  ? "bg-gradient-to-b from-purple-500/40 to-white/5"
                                  : "bg-white/5"
                              }`}
                            />
                          )}
                        </div>
                        {/* Label */}
                        <div className="pt-2">
                          <p
                            className={`text-sm font-medium ${
                              isCurrent
                                ? "text-white"
                                : isCompleted
                                ? "text-green-400"
                                : "text-muted-foreground"
                            }`}
                          >
                            {step.label}
                          </p>
                          {isCurrent && (
                            <p className="text-xs text-muted-foreground mt-0.5">
                              Current status
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Share / scan */}
          <div className="animate-fade-in-up pb-8">
            <Card>
              <CardContent className="py-6 flex flex-col items-center gap-4 text-center">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                  Share / scan
                </h3>
                {pageUrl ? (
                  <div className="rounded-xl bg-white p-3">
                    <QRCodeSVG value={pageUrl} size={160} />
                  </div>
                ) : null}
                <Button
                  onClick={copyLink}
                  variant="outline"
                  className="w-full h-12 rounded-xl border-white/10 bg-white/5 hover:bg-white/10 gap-2"
                >
                  {copied ? (
                    <>
                      <CheckCircle2 className="h-4 w-4 text-green-400" />
                      Link Copied!
                    </>
                  ) : (
                    <>
                      <Link2 className="h-4 w-4" />
                      Share Tracking Link
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
