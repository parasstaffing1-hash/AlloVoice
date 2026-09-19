"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  ShieldCheck,
  Siren,
  MapPin,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Phone,
  Settings2,
} from "lucide-react";

type Tab = "status" | "checkin" | "alerts" | "settings";

interface EmergencyContact {
  name: string;
  phone: string;
  relation: string;
}

export default function SafetyPage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<Tab>("status");

  // ---- Status ----
  const [status, setStatus] = useState<any>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState("");
  const [countdown, setCountdown] = useState("");

  // ---- Panic (two-step confirm) ----
  const [panicArmed, setPanicArmed] = useState(false);
  const [panicLoading, setPanicLoading] = useState(false);
  const [panicResult, setPanicResult] = useState<any>(null);
  const [panicError, setPanicError] = useState("");

  // ---- Check in ----
  const [jobId, setJobId] = useState("");
  const [note, setNote] = useState("");
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [locLoading, setLocLoading] = useState(false);
  const [checkInLoading, setCheckInLoading] = useState(false);
  const [checkInResult, setCheckInResult] = useState("");
  const [checkInError, setCheckInError] = useState("");

  // ---- Alerts ----
  const [alerts, setAlerts] = useState<any[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [alertFilter, setAlertFilter] = useState<string>("");
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [resolutionNote, setResolutionNote] = useState("");
  const [alertsError, setAlertsError] = useState("");

  // ---- Settings ----
  const [checkInInterval, setCheckInInterval] = useState("60");
  const [escalateAfterMissed, setEscalateAfterMissed] = useState("2");
  const [contacts, setContacts] = useState<EmergencyContact[]>([
    { name: "", phone: "", relation: "" },
  ]);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsMsg, setSettingsMsg] = useState("");
  const [settingsError, setSettingsError] = useState("");

  const loadStatus = useCallback(() => {
    if (!token) return;
    setStatusLoading(true);
    setStatusError("");
    api.safety
      .status(token)
      .then((r: any) => setStatus(r))
      .catch((e: any) => setStatusError(e?.message || "Failed to load safety status"))
      .finally(() => setStatusLoading(false));
  }, [token]);

  const loadAlerts = useCallback(() => {
    if (!token) return;
    setAlertsLoading(true);
    setAlertsError("");
    api.safety
      .alerts(token, alertFilter || undefined)
      .then((r: any) => setAlerts(r.alerts || r || []))
      .catch((e: any) => setAlertsError(e?.message || "Failed to load alerts"))
      .finally(() => setAlertsLoading(false));
  }, [token, alertFilter]);

  const loadSettings = useCallback(() => {
    if (!token) return;
    setSettingsLoading(true);
    setSettingsError("");
    api.safety
      .getSettings(token)
      .then((r: any) => {
        const s = r.settings || r;
        if (s.check_in_interval_minutes != null)
          setCheckInInterval(String(s.check_in_interval_minutes));
        if (s.escalate_after_missed != null)
          setEscalateAfterMissed(String(s.escalate_after_missed));
        if (Array.isArray(s.emergency_contacts) && s.emergency_contacts.length > 0)
          setContacts(s.emergency_contacts);
      })
      .catch((e: any) => setSettingsError(e?.message || "Failed to load settings"))
      .finally(() => setSettingsLoading(false));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    loadStatus();
  }, [token, loadStatus]);

  useEffect(() => {
    if (!token || tab !== "alerts") return;
    loadAlerts();
  }, [token, tab, loadAlerts]);

  useEffect(() => {
    if (!token || tab !== "settings") return;
    loadSettings();
  }, [token, tab, loadSettings]);

  // Countdown to next_due
  useEffect(() => {
    if (!status?.next_due) {
      setCountdown("");
      return;
    }
    const tick = () => {
      const due = new Date(status.next_due).getTime();
      const diff = due - Date.now();
      if (diff <= 0) {
        setCountdown("OVERDUE");
        return;
      }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setCountdown(
        `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [status?.next_due]);

  // Disarm panic button after 10s
  useEffect(() => {
    if (!panicArmed) return;
    const id = setTimeout(() => setPanicArmed(false), 10000);
    return () => clearTimeout(id);
  }, [panicArmed]);

  const getCoords = (): Promise<{ latitude?: number; longitude?: number }> =>
    new Promise((resolve) => {
      if (!("geolocation" in navigator)) return resolve({});
      navigator.geolocation.getCurrentPosition(
        (pos) =>
          resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
        () => resolve({}),
        { timeout: 8000 }
      );
    });

  const handlePanic = async () => {
    if (!token) return;
    if (!panicArmed) {
      setPanicArmed(true);
      return;
    }
    setPanicLoading(true);
    setPanicError("");
    const coords = await getCoords();
    api.safety
      .panic({ latitude: coords.latitude, longitude: coords.longitude }, token)
      .then((r: any) => {
        setPanicResult(r);
        setPanicArmed(false);
        loadStatus();
      })
      .catch((e: any) => setPanicError(e?.message || "Failed to raise panic alert"))
      .finally(() => setPanicLoading(false));
  };

  const handleUseLocation = () => {
    if (!("geolocation" in navigator)) {
      setCheckInError("Geolocation is not supported by this browser.");
      return;
    }
    setLocLoading(true);
    setCheckInError("");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(String(pos.coords.latitude));
        setLng(String(pos.coords.longitude));
        setLocLoading(false);
      },
      () => {
        setCheckInError("Could not get your location. Check browser permissions.");
        setLocLoading(false);
      },
      { timeout: 8000 }
    );
  };

  const handleCheckIn = () => {
    if (!token) return;
    setCheckInLoading(true);
    setCheckInError("");
    setCheckInResult("");
    const data: any = {};
    if (jobId.trim()) data.job_id = jobId.trim();
    if (note.trim()) data.note = note.trim();
    if (lat) data.latitude = Number(lat);
    if (lng) data.longitude = Number(lng);
    api.safety
      .checkIn(data, token)
      .then((r: any) => {
        setCheckInResult(
          r.next_check_in_due
            ? `Checked in. Next check-in due: ${new Date(r.next_check_in_due).toLocaleString("en-GB")}`
            : "Checked in successfully."
        );
        setNote("");
        loadStatus();
      })
      .catch((e: any) => setCheckInError(e?.message || "Check-in failed"))
      .finally(() => setCheckInLoading(false));
  };

  const handleResolve = (id: string) => {
    if (!token) return;
    if (!resolutionNote.trim()) {
      setAlertsError("Enter a resolution note first.");
      return;
    }
    setResolvingId(id);
    setAlertsError("");
    api.safety
      .resolveAlert(id, resolutionNote.trim(), token)
      .then((_r: any) => {
        setResolutionNote("");
        setResolvingId(null);
        loadAlerts();
        loadStatus();
      })
      .catch((e: any) => {
        setAlertsError(e?.message || "Failed to resolve alert");
        setResolvingId(null);
      });
  };

  const updateContact = (i: number, field: keyof EmergencyContact, value: string) => {
    setContacts((prev) => prev.map((c, idx) => (idx === i ? { ...c, [field]: value } : c)));
  };

  const addContact = () =>
    setContacts((prev) => [...prev, { name: "", phone: "", relation: "" }]);

  const removeContact = (i: number) =>
    setContacts((prev) => (prev.length <= 1 ? prev : prev.filter((_, idx) => idx !== i)));

  const handleSaveSettings = () => {
    if (!token) return;
    setSettingsSaving(true);
    setSettingsMsg("");
    setSettingsError("");
    api.safety
      .updateSettings(
        {
          check_in_interval_minutes: Number(checkInInterval),
          escalate_after_missed: Number(escalateAfterMissed),
          emergency_contacts: contacts.filter((c) => c.name.trim() || c.phone.trim()),
        },
        token
      )
      .then((_r: any) => setSettingsMsg("Safety settings saved."))
      .catch((e: any) => setSettingsError(e?.message || "Failed to save settings"))
      .finally(() => setSettingsSaving(false));
  };

  const hasActiveAlert = Boolean(status?.active_alert);
  const isOverdue = Boolean(status?.overdue) || countdown === "OVERDUE";

  const statusCardStyle = hasActiveAlert
    ? "border-red-500 bg-red-950/60 animate-pulse"
    : isOverdue
      ? "border-red-500/60 bg-red-950/40"
      : "border-green-500/40 bg-green-950/30";

  const tabs: { id: Tab; label: string }[] = [
    { id: "status", label: "Status" },
    { id: "checkin", label: "Check In" },
    { id: "alerts", label: "Alerts" },
    { id: "settings", label: "Settings" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <ShieldCheck className="h-8 w-8 text-green-400" />
            Lone Worker Safety
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Check-ins, panic alerts and escalation settings for field staff
          </p>
        </div>
        {status && (
          <Badge
            className={
              hasActiveAlert || isOverdue
                ? "bg-red-500/20 text-red-400"
                : "bg-green-500/20 text-green-400"
            }
          >
            {hasActiveAlert ? "PANIC ACTIVE" : isOverdue ? "OVERDUE" : "SAFE"}
          </Badge>
        )}
      </div>

      <div className="flex gap-2 border-b border-zinc-800 pb-2">
        {tabs.map((t) => (
          <Button
            key={t.id}
            variant={tab === t.id ? "default" : "ghost"}
            size="sm"
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </Button>
        ))}
      </div>

      {tab === "status" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card className={statusCardStyle}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {hasActiveAlert ? (
                  <Siren className="h-5 w-5 text-red-400" />
                ) : isOverdue ? (
                  <AlertTriangle className="h-5 w-5 text-red-400" />
                ) : (
                  <ShieldCheck className="h-5 w-5 text-green-400" />
                )}
                {hasActiveAlert
                  ? "Panic Alert Active"
                  : isOverdue
                    ? "Check-In Overdue"
                    : "You Are Safe"}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {statusLoading ? (
                <p className="text-sm text-muted-foreground">Loading status…</p>
              ) : statusError ? (
                <div className="space-y-2">
                  <p className="text-sm text-red-400">{statusError}</p>
                  <Button size="sm" variant="outline" onClick={loadStatus}>
                    Retry
                  </Button>
                </div>
              ) : (
                <>
                  <div className="flex items-center gap-2 text-sm">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">Last check-in:</span>
                    <span className="font-medium">
                      {status?.last_check_in
                        ? new Date(status.last_check_in).toLocaleString("en-GB")
                        : "Never"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">Next due:</span>
                    <span className="font-medium">
                      {status?.next_due
                        ? new Date(status.next_due).toLocaleString("en-GB")
                        : "—"}
                    </span>
                  </div>
                  {status?.next_due && (
                    <p
                      className={`text-4xl font-mono font-bold ${isOverdue ? "text-red-400" : "text-green-300"}`}
                    >
                      {countdown || "—"}
                    </p>
                  )}
                  {status?.active_alert && (
                    <div className="rounded-lg border border-red-500/50 bg-red-950/50 p-3 text-sm">
                      <p className="font-medium text-red-300">
                        Active alert: {status.active_alert.id || status.active_alert.type}
                      </p>
                      <p className="text-xs text-red-200/70 mt-1">
                        {status.active_alert.timestamp
                          ? new Date(status.active_alert.timestamp).toLocaleString("en-GB")
                          : ""}
                        {status.active_alert.location
                          ? ` · ${status.active_alert.location}`
                          : ""}
                      </p>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          <Card className="border-red-900 bg-zinc-950">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-red-400">
                <Siren className="h-5 w-5" />
                Emergency Panic Button
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {panicArmed
                  ? "Armed — press again within 10 seconds to confirm and notify your emergency contacts."
                  : "Press once to arm, press again to confirm. Your GPS location will be sent to your emergency contacts."}
              </p>
              <Button
                variant="destructive"
                size="lg"
                className={`w-full h-20 text-xl font-bold ${panicArmed ? "animate-pulse" : ""}`}
                onClick={handlePanic}
                disabled={panicLoading}
              >
                <Siren className="h-6 w-6 mr-2" />
                {panicLoading ? "SENDING…" : panicArmed ? "CONFIRM PANIC" : "PANIC"}
              </Button>
              {panicArmed && !panicLoading && (
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => setPanicArmed(false)}
                >
                  Cancel
                </Button>
              )}
              {panicError && <p className="text-sm text-red-400">{panicError}</p>}
              {panicResult && (
                <div className="rounded-lg border border-red-500/40 bg-red-950/40 p-3 text-sm space-y-1">
                  <p className="flex items-center gap-1 font-medium text-red-300">
                    <CheckCircle2 className="h-4 w-4" /> Panic alert raised
                  </p>
                  <p className="text-muted-foreground">
                    Alert ID:{" "}
                    <span className="font-mono text-foreground">
                      {panicResult.alert_id || panicResult.id || "—"}
                    </span>
                  </p>
                  {Array.isArray(panicResult.notified) && panicResult.notified.length > 0 && (
                    <div>
                      <p className="text-muted-foreground">Notified:</p>
                      <ul className="list-disc list-inside text-foreground">
                        {panicResult.notified.map((n: any, i: number) => (
                          <li key={i}>{typeof n === "string" ? n : n.name || n.phone || JSON.stringify(n)}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {tab === "checkin" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-400" />
              Check In
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 max-w-lg">
            <div>
              <label className="text-sm font-medium">Job ID (optional)</label>
              <Input
                className="mt-1"
                placeholder="e.g. job_123"
                value={jobId}
                onChange={(e) => setJobId(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium">Note</label>
              <Input
                className="mt-1"
                placeholder="On site, all well…"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-sm font-medium">Latitude</label>
                <Input
                  className="mt-1"
                  placeholder="51.5072"
                  value={lat}
                  onChange={(e) => setLat(e.target.value)}
                />
              </div>
              <div>
                <label className="text-sm font-medium">Longitude</label>
                <Input
                  className="mt-1"
                  placeholder="-0.1276"
                  value={lng}
                  onChange={(e) => setLng(e.target.value)}
                />
              </div>
            </div>
            <Button
              variant="outline"
              className="gap-2"
              onClick={handleUseLocation}
              disabled={locLoading}
            >
              <MapPin className="h-4 w-4" />
              {locLoading ? "Locating…" : "Use my location"}
            </Button>
            {checkInError && <p className="text-sm text-red-400">{checkInError}</p>}
            {checkInResult && (
              <p className="text-sm text-green-400 flex items-center gap-1">
                <CheckCircle2 className="h-4 w-4" /> {checkInResult}
              </p>
            )}
            <Button onClick={handleCheckIn} disabled={checkInLoading} className="w-full">
              {checkInLoading ? "Checking in…" : "Check In Now"}
            </Button>
          </CardContent>
        </Card>
      )}

      {tab === "alerts" && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-yellow-400" />
                Safety Alerts
              </CardTitle>
              <div className="flex gap-2">
                {["", "active", "resolved"].map((s) => (
                  <Button
                    key={s || "all"}
                    size="sm"
                    variant={alertFilter === s ? "default" : "outline"}
                    onClick={() => setAlertFilter(s)}
                  >
                    {s === "" ? "All" : s === "active" ? "Active" : "Resolved"}
                  </Button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {alertsError && <p className="text-sm text-red-400">{alertsError}</p>}
            {alertsLoading ? (
              <p className="text-sm text-muted-foreground">Loading alerts…</p>
            ) : alerts.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                No alerts{alertFilter ? ` with status "${alertFilter}"` : ""}.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-800 text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Type</th>
                      <th className="py-2 pr-4 font-medium">User</th>
                      <th className="py-2 pr-4 font-medium">Timestamp</th>
                      <th className="py-2 pr-4 font-medium">Location</th>
                      <th className="py-2 pr-4 font-medium">Status</th>
                      <th className="py-2 font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.map((a: any) => {
                      const resolved =
                        a.status === "resolved" || a.resolved === true;
                      return (
                        <tr key={a.id} className="border-b border-zinc-900">
                          <td className="py-2 pr-4 font-medium">
                            {a.type || a.alert_type || "—"}
                          </td>
                          <td className="py-2 pr-4 text-muted-foreground">
                            {a.user_name || a.user || a.user_id || "—"}
                          </td>
                          <td className="py-2 pr-4 text-muted-foreground">
                            {a.timestamp || a.created_at
                              ? new Date(a.timestamp || a.created_at).toLocaleString("en-GB")
                              : "—"}
                          </td>
                          <td className="py-2 pr-4 text-muted-foreground">
                            {a.location ||
                              (a.latitude != null && a.longitude != null
                                ? `${a.latitude}, ${a.longitude}`
                                : "—")}
                          </td>
                          <td className="py-2 pr-4">
                            <Badge
                              className={
                                resolved
                                  ? "bg-green-500/20 text-green-400"
                                  : "bg-red-500/20 text-red-400"
                              }
                            >
                              {resolved ? "resolved" : "active"}
                            </Badge>
                          </td>
                          <td className="py-2">
                            {!resolved && (
                              <div className="flex gap-2 items-center">
                                <Input
                                  className="h-8 w-44"
                                  placeholder="Resolution note…"
                                  value={resolvingId === a.id ? resolutionNote : ""}
                                  onChange={(e) => {
                                    setResolvingId(a.id);
                                    setResolutionNote(e.target.value);
                                  }}
                                />
                                <Button
                                  size="sm"
                                  onClick={() => handleResolve(a.id)}
                                  disabled={resolvingId === a.id && !resolutionNote.trim()}
                                >
                                  Resolve
                                </Button>
                              </div>
                            )}
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

      {tab === "settings" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings2 className="h-5 w-5" />
              Safety Settings
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-5 max-w-xl">
            {settingsLoading ? (
              <p className="text-sm text-muted-foreground">Loading settings…</p>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-medium">
                      Check-in interval (minutes)
                    </label>
                    <Input
                      className="mt-1"
                      type="number"
                      min="5"
                      value={checkInInterval}
                      onChange={(e) => setCheckInInterval(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Escalate after missed</label>
                    <Input
                      className="mt-1"
                      type="number"
                      min="1"
                      value={escalateAfterMissed}
                      onChange={(e) => setEscalateAfterMissed(e.target.value)}
                    />
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium flex items-center gap-1">
                      <Phone className="h-4 w-4" /> Emergency contacts
                    </label>
                    <Button size="sm" variant="outline" onClick={addContact}>
                      Add contact
                    </Button>
                  </div>
                  {contacts.map((c, i) => (
                    <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2">
                      <Input
                        placeholder="Name"
                        value={c.name}
                        onChange={(e) => updateContact(i, "name", e.target.value)}
                      />
                      <Input
                        placeholder="Phone"
                        value={c.phone}
                        onChange={(e) => updateContact(i, "phone", e.target.value)}
                      />
                      <Input
                        placeholder="Relation"
                        value={c.relation}
                        onChange={(e) => updateContact(i, "relation", e.target.value)}
                      />
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => removeContact(i)}
                        disabled={contacts.length <= 1}
                      >
                        ✕
                      </Button>
                    </div>
                  ))}
                </div>

                {settingsMsg && (
                  <p className="text-sm text-green-400 flex items-center gap-1">
                    <CheckCircle2 className="h-4 w-4" /> {settingsMsg}
                  </p>
                )}
                {settingsError && <p className="text-sm text-red-400">{settingsError}</p>}
                <Button onClick={handleSaveSettings} disabled={settingsSaving}>
                  {settingsSaving ? "Saving…" : "Save Settings"}
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
