"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { Phone, PhoneOff, ArrowRightLeft, BarChart3, ListChecks } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const OUTCOMES = ["resolved", "callback_requested", "transferred", "no_answer", "follow_up"];

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return String(iso);
  }
}

function sentimentDot(s: string | null | undefined): string {
  if (s === "positive") return "bg-green-500";
  if (s === "negative") return "bg-red-500";
  if (s === "neutral") return "bg-amber-400";
  return "bg-zinc-300";
}

function emotionColor(e: string | null | undefined): string {
  const v = (e || "").toLowerCase();
  if (["happy", "joy", "joyful", "positive", "excited", "satisfied"].includes(v)) return "bg-green-500";
  if (["angry", "anger", "frustrated", "frustration", "annoyed", "furious"].includes(v)) return "bg-red-500";
  if (["sad", "sadness", "disappointed", "upset"].includes(v)) return "bg-blue-500";
  if (["fear", "fearful", "anxious", "anxiety", "worried", "nervous"].includes(v)) return "bg-purple-500";
  if (["surprised", "surprise", "confused", "confusion"].includes(v)) return "bg-amber-500";
  return "bg-zinc-400";
}

function statusVariant(s: string): "default" | "secondary" | "outline" {
  if (s === "live") return "default";
  if (s === "transferred") return "secondary";
  return "outline";
}

export default function CallsPage() {
  const { token } = useAuth();
  const [calls, setCalls] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<any | null>(null);
  const [error, setError] = useState("");

  const [direction, setDirection] = useState("inbound");
  const [channel, setChannel] = useState("demo");
  const [customerId, setCustomerId] = useState("");
  const [jobId, setJobId] = useState("");
  const [starting, setStarting] = useState(false);

  const [speaker, setSpeaker] = useState<"caller" | "agent">("caller");
  const [turnText, setTurnText] = useState("");
  const [turnEmotion, setTurnEmotion] = useState("");
  const [sendingTurn, setSendingTurn] = useState(false);

  const [transferReason, setTransferReason] = useState("");
  const [oncallPhone, setOncallPhone] = useState("");
  const [transferring, setTransferring] = useState(false);

  const [outcome, setOutcome] = useState("resolved");
  const [ending, setEnding] = useState(false);

  const refreshList = useCallback(() => {
    if (!token) return;
    fetch(`${API}/api/calls/`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r: any) => r.json())
      .then((r: any) => setCalls(Array.isArray(r) ? r : r.calls || []))
      .catch(() => {});
  }, [token]);

  const fetchDetail = useCallback(
    (id: string) => {
      if (!token) return;
      fetch(`${API}/api/calls/${id}`, { headers: { Authorization: `Bearer ${token}` } })
        .then((r: any) => r.json())
        .then((r: any) => {
          if (r?.detail && !r?.id) throw new Error(r.detail);
          setDetail(r);
        })
        .catch((e: any) => setError(e?.message || "Failed to load call"));
    },
    [token]
  );

  useEffect(() => {
    refreshList();
  }, [refreshList]);

  const selectCall = (id: string) => {
    setSelectedId(id);
    setDetail(null);
    setError("");
    setTransferReason("");
    fetchDetail(id);
  };

  const startCall = () => {
    if (!token || starting) return;
    setStarting(true);
    setError("");
    fetch(`${API}/api/calls/start`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_id: customerId || undefined,
        job_id: jobId || undefined,
        direction,
        channel,
      }),
    })
      .then((r: any) => r.json())
      .then((r: any) => {
        if (r?.detail) throw new Error(typeof r.detail === "string" ? r.detail : "Start failed");
        setCustomerId("");
        setJobId("");
        refreshList();
        if (r?.id) selectCall(r.id);
      })
      .catch((e: any) => setError(e?.message || "Start failed"))
      .finally(() => setStarting(false));
  };

  const sendTurn = () => {
    if (!token || !selectedId || !turnText.trim() || sendingTurn) return;
    setSendingTurn(true);
    setError("");
    fetch(`${API}/api/calls/${selectedId}/turn`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        speaker,
        text: turnText.trim(),
        emotion: turnEmotion.trim() || undefined,
      }),
    })
      .then((r: any) => r.json())
      .then((r: any) => {
        if (r?.detail) throw new Error(typeof r.detail === "string" ? r.detail : "Turn failed");
        setTurnText("");
        setTurnEmotion("");
        fetchDetail(selectedId);
        refreshList();
      })
      .catch((e: any) => setError(e?.message || "Turn failed"))
      .finally(() => setSendingTurn(false));
  };

  const transferCall = () => {
    if (!token || !selectedId || !transferReason.trim() || transferring) return;
    setTransferring(true);
    setError("");
    fetch(`${API}/api/calls/${selectedId}/transfer`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        reason: transferReason.trim(),
        oncall_phone: oncallPhone.trim() || undefined,
      }),
    })
      .then((r: any) => r.json())
      .then((r: any) => {
        if (r?.detail) throw new Error(typeof r.detail === "string" ? r.detail : "Transfer failed");
        setTransferReason("");
        fetchDetail(selectedId);
        refreshList();
      })
      .catch((e: any) => setError(e?.message || "Transfer failed"))
      .finally(() => setTransferring(false));
  };

  const endCall = () => {
    if (!token || !selectedId || ending) return;
    setEnding(true);
    setError("");
    fetch(`${API}/api/calls/${selectedId}/end`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ outcome }),
    })
      .then((r: any) => r.json())
      .then((r: any) => {
        if (r?.detail && !r?.id) throw new Error(typeof r.detail === "string" ? r.detail : "End failed");
        setDetail(r);
        refreshList();
      })
      .catch((e: any) => setError(e?.message || "End failed"))
      .finally(() => setEnding(false));
  };

  const analysis = detail?.analysis || null;
  const talkPct = Number(analysis?.talk_ratio_caller_pct || 0);
  const isLive = detail?.status === "live";

  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 px-4 py-6 sm:px-6">
      <div>
        <h1 className="text-2xl font-bold sm:text-3xl">Calls</h1>
        <p className="text-sm text-muted-foreground">
          Retell-style live sessions, transfer and post-call analysis.
        </p>
      </div>

      {!token && (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">
            Sign in to view and manage calls.
          </CardContent>
        </Card>
      )}

      {error && (
        <button
          type="button"
          onClick={() => setError("")}
          className="w-full rounded-xl border border-red-400/40 bg-red-500/10 px-4 py-2.5 text-left text-sm text-red-600"
        >
          {error} <span className="underline underline-offset-2">Dismiss</span>
        </button>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Phone className="h-4 w-4" /> New call
          </CardTitle>
          <CardDescription>Start a live session (demo, phone or realtime channel).</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label className="grid gap-1 text-xs font-medium">
            Direction
            <select
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
              className="h-10 rounded-lg border border-input bg-background px-3 text-sm"
            >
              <option value="inbound">inbound</option>
              <option value="outbound">outbound</option>
            </select>
          </label>
          <label className="grid gap-1 text-xs font-medium">
            Channel
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              className="h-10 rounded-lg border border-input bg-background px-3 text-sm"
            >
              <option value="demo">demo</option>
              <option value="phone">phone</option>
              <option value="realtime">realtime</option>
            </select>
          </label>
          <Input
            placeholder="customer_id (optional)"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
          />
          <Input
            placeholder="job_id (optional)"
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
          />
          <Button onClick={startCall} disabled={!token || starting} className="w-full">
            <Phone className="mr-2 h-4 w-4" />
            {starting ? "Starting…" : "Start call"}
          </Button>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className={`${selectedId ? "hidden lg:block" : "block"} lg:col-span-2`}>
          <CardHeader>
            <CardTitle className="text-lg">Sessions ({calls.length})</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            {calls.length === 0 && (
              <p className="text-sm text-muted-foreground">No calls yet — start one above.</p>
            )}
            {calls.map((c: any) => (
              <button
                key={c.id}
                type="button"
                onClick={() => selectCall(c.id)}
                className={`w-full rounded-xl border p-3 text-left transition hover:bg-accent ${
                  selectedId === c.id ? "border-primary bg-accent" : ""
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge variant={statusVariant(c.status)}>
                    {c.status === "live" && (
                      <span className="mr-1.5 inline-block h-2 w-2 animate-pulse rounded-full bg-current" />
                    )}
                    {c.status}
                  </Badge>
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span className={`inline-block h-2 w-2 rounded-full ${sentimentDot(c.sentiment)}`} />
                    {c.sentiment || "pending"}
                  </span>
                </div>
                <div className="mt-2 text-xs text-muted-foreground">
                  {fmtTime(c.started_at)} · {c.turns_count ?? 0} turns
                </div>
                <div className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">
                  {String(c.id).slice(0, 8)}…
                </div>
              </button>
            ))}
          </CardContent>
        </Card>

        <div className={`${selectedId ? "block" : "hidden lg:block"} lg:col-span-3`}>
          {!detail ? (
            <Card>
              <CardContent className="pt-6 text-sm text-muted-foreground">
                Select a session to see the transcript, emotion timeline and analysis.
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4">
              <Card>
                <CardHeader>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <CardTitle className="text-lg">
                      Call <span className="font-mono text-sm">{String(detail.id).slice(0, 8)}…</span>
                    </CardTitle>
                    <Badge variant={statusVariant(detail.status)}>{detail.status}</Badge>
                  </div>
                  <CardDescription>
                    {fmtTime(detail.started_at)}
                    {detail.customer_id ? ` · customer ${detail.customer_id}` : ""}
                    {detail.job_id ? ` · job ${detail.job_id}` : ""}
                  </CardDescription>
                </CardHeader>
                <CardContent className="grid gap-4">
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedId(null);
                      setDetail(null);
                    }}
                    className="text-left text-xs text-muted-foreground underline underline-offset-2 lg:hidden"
                  >
                    ← Back to sessions
                  </button>

                  <div className="grid gap-2">
                    {(detail.turns || []).length === 0 && (
                      <p className="text-sm text-muted-foreground">No turns yet.</p>
                    )}
                    {(detail.turns || []).map((t: any) => (
                      <div
                        key={t.index}
                        className={`flex ${t.speaker === "caller" ? "justify-end" : "justify-start"}`}
                      >
                        <div
                          className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                            t.speaker === "caller"
                              ? "rounded-br-md bg-primary text-primary-foreground"
                              : "rounded-bl-md border bg-muted"
                          }`}
                        >
                          <div className="mb-1 flex items-center gap-1.5 text-[11px] opacity-70">
                            <span className="font-semibold uppercase">{t.speaker}</span>
                            {t.emotion && (
                              <span className="inline-flex items-center gap-1 rounded-full border px-1.5 py-px">
                                <span className={`inline-block h-1.5 w-1.5 rounded-full ${emotionColor(t.emotion)}`} />
                                {t.emotion}
                              </span>
                            )}
                          </div>
                          {t.text}
                        </div>
                      </div>
                    ))}
                  </div>

                  {(detail.emotions || detail.emotion_timeline || []).length > 0 && (
                    <div>
                      <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
                        Emotion timeline
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {(detail.emotion_timeline || detail.emotions || []).map((e: any, i: number) => (
                          <span
                            key={i}
                            title={`turn ${e.turn_index}: ${e.emotion}`}
                            className="inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-xs"
                          >
                            <span className={`inline-block h-2 w-2 rounded-full ${emotionColor(e.emotion)}`} />
                            #{e.turn_index} {e.emotion}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {isLive && (
                    <div className="grid gap-2 rounded-xl border p-3">
                      <p className="text-xs font-semibold uppercase text-muted-foreground">Add turn</p>
                      <div className="flex gap-2">
                        {(["caller", "agent"] as const).map((s) => (
                          <Button
                            key={s}
                            size="sm"
                            variant={speaker === s ? "default" : "outline"}
                            onClick={() => setSpeaker(s)}
                          >
                            {s}
                          </Button>
                        ))}
                      </div>
                      <div className="grid gap-2 sm:grid-cols-[1fr_160px_auto]">
                        <Input
                          placeholder="Turn text…"
                          value={turnText}
                          onChange={(e) => setTurnText(e.target.value)}
                        />
                        <Input
                          placeholder="emotion (optional)"
                          value={turnEmotion}
                          onChange={(e) => setTurnEmotion(e.target.value)}
                        />
                        <Button onClick={sendTurn} disabled={sendingTurn || !turnText.trim()}>
                          {sendingTurn ? "Sending…" : "Send"}
                        </Button>
                      </div>
                    </div>
                  )}

                  {(detail.status === "live" || detail.status === "transferred") && (
                    <div className="grid gap-3 rounded-xl border p-3">
                      {detail.status === "live" && (
                        <div className="grid gap-2">
                          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
                            <ArrowRightLeft className="h-3.5 w-3.5" /> Transfer
                          </p>
                          <div className="grid gap-2 sm:grid-cols-[1fr_180px_auto]">
                            <Input
                              placeholder="Transfer reason…"
                              value={transferReason}
                              onChange={(e) => setTransferReason(e.target.value)}
                            />
                            <Input
                              placeholder="On-call phone (optional)"
                              value={oncallPhone}
                              onChange={(e) => setOncallPhone(e.target.value)}
                            />
                            <Button
                              variant="secondary"
                              onClick={transferCall}
                              disabled={transferring || !transferReason.trim()}
                            >
                              <ArrowRightLeft className="mr-2 h-4 w-4" />
                              {transferring ? "Transferring…" : "Transfer"}
                            </Button>
                          </div>
                        </div>
                      )}
                      <div className="grid gap-2">
                        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
                          <PhoneOff className="h-3.5 w-3.5" /> End call
                        </p>
                        <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                          <select
                            value={outcome}
                            onChange={(e) => setOutcome(e.target.value)}
                            className="h-10 rounded-lg border border-input bg-background px-3 text-sm"
                          >
                            {OUTCOMES.map((o) => (
                              <option key={o} value={o}>
                                {o}
                              </option>
                            ))}
                          </select>
                          <Button variant="destructive" onClick={endCall} disabled={ending}>
                            <PhoneOff className="mr-2 h-4 w-4" />
                            {ending ? "Ending…" : "End & analyse"}
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}

                  {analysis && (
                    <div className="grid gap-3 rounded-xl border p-4">
                      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
                        <BarChart3 className="h-3.5 w-3.5" /> Post-call analysis
                      </p>
                      <p className="text-sm leading-relaxed">{analysis.summary}</p>
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="flex items-center gap-1.5">
                          <span className={`inline-block h-2.5 w-2.5 rounded-full ${sentimentDot(analysis.sentiment)}`} />
                          {analysis.sentiment || "neutral"}
                        </span>
                        {analysis.follow_up_suggested && (
                          <Badge variant="secondary">follow-up suggested</Badge>
                        )}
                        {analysis.outcome && <Badge variant="outline">{analysis.outcome}</Badge>}
                      </div>
                      <div>
                        <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                          <span>Caller talk ratio</span>
                          <span>{talkPct}%</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded bg-muted">
                          <div className="h-2 rounded bg-primary" style={{ width: `${talkPct}%` }} />
                        </div>
                      </div>
                      {(analysis.action_items || []).length > 0 && (
                        <div>
                          <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase text-muted-foreground">
                            <ListChecks className="h-3.5 w-3.5" /> Actions
                          </p>
                          <ul className="grid gap-1.5">
                            {(analysis.action_items || []).map((a: string, i: number) => (
                              <li key={i} className="flex items-start gap-2 text-sm">
                                <input type="checkbox" className="mt-1" />
                                <span>{a}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {(analysis.key_quotes || []).length > 0 && (
                        <div className="grid gap-1.5">
                          {(analysis.key_quotes || []).map((q: string, i: number) => (
                            <blockquote key={i} className="border-l-2 border-primary/40 pl-3 text-sm italic">
                              “{q}”
                            </blockquote>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
