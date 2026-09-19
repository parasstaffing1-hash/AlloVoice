"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { SignaturePad } from "@/components/signature-pad";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  ClipboardCheck, AlertTriangle, ShieldCheck, Pen, ChevronLeft,
} from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function RamsPage() {
  const { token } = useAuth();
  const [templates, setTemplates] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [jobId, setJobId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [answers, setAnswers] = useState<Record<string, { checked: boolean; note: string }>>({});
  const [engineer, setEngineer] = useState("");
  const [signature, setSignature] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    fetch(`${API}/api/rams/templates`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r: any) => r.json())
      .then((r: any) => setTemplates(r.templates || []))
      .catch(() => {});
    api.jobs.list(token).then((r: any) => setJobs(Array.isArray(r) ? r : r.jobs || [])).catch(() => {});
  }, [token]);

  useEffect(() => {
    if (!token || !jobId) { setHistory([]); return; }
    fetch(`${API}/api/rams/assessments?job_id=${jobId}`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r: any) => r.json())
      .then((r: any) => setHistory(r.assessments || []))
      .catch(() => {});
  }, [token, jobId]);

  const tpl = templates.find((t) => t.id === templateId);
  const toggle = (id: string) =>
    setAnswers((a) => ({ ...a, [id]: { checked: !(a[id]?.checked), note: a[id]?.note || "" } }));
  const setNote = (id: string, note: string) =>
    setAnswers((a) => ({ ...a, [id]: { checked: a[id]?.checked || false, note } }));

  const submit = async () => {
    if (!token || !tpl || submitting) return;
    setSubmitting(true); setError(""); setVerdict(null);
    try {
      const res = await fetch(`${API}/api/rams/assessments`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: jobId || null,
          template_id: tpl.id,
          engineer_name: engineer,
          signature_base64: signature,
          answers: tpl.items.map((it: any) => ({
            item_id: it.id,
            checked: !!answers[it.id]?.checked,
            note: answers[it.id]?.note || "",
          })),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Submit failed");
      setVerdict(data);
      if (jobId) {
        const h = await fetch(`${API}/api/rams/assessments?job_id=${jobId}`,
          { headers: { Authorization: `Bearer ${token}` } }).then((r: any) => r.json());
        setHistory(h.assessments || []);
      }
    } catch (e: any) {
      setError(e.message || "Submit failed");
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    setTemplateId(""); setAnswers({}); setSignature(null); setVerdict(null); setError("");
  };

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div>
        <h1 className="text-3xl font-bold">RAMS — Risk Assessment</h1>
        <p className="text-muted-foreground">60-second safety check before starting work.</p>
      </div>

      {!tpl && !verdict && (
        <>
          <Card>
            <CardHeader><CardTitle className="text-lg">1. Which job?</CardTitle></CardHeader>
            <CardContent>
              <div className="grid gap-2">
                <Button variant={jobId === "" ? "default" : "outline"} size="lg" className="min-h-14 justify-start"
                  onClick={() => setJobId("")}>General (no specific job)</Button>
                {jobs.slice(0, 8).map((j: any) => (
                  <Button key={j.id} variant={jobId === j.id ? "default" : "outline"} size="lg"
                    className="min-h-14 justify-start" onClick={() => setJobId(j.id)}>
                    {j.title}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-lg">2. Which assessment?</CardTitle></CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-3">
              {templates.map((t) => (
                <Button key={t.id} variant="outline" size="lg" className="min-h-20 flex-col gap-1 h-auto py-4"
                  onClick={() => setTemplateId(t.id)}>
                  <ClipboardCheck className="h-6 w-6 text-primary" />
                  <span className="font-semibold">{t.name}</span>
                  <span className="text-xs text-muted-foreground">{t.trade}</span>
                </Button>
              ))}
            </CardContent>
          </Card>
        </>
      )}

      {tpl && !verdict && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => setTemplateId("")}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <CardTitle>{tpl.name}</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {tpl.items.map((it: any) => (
              <div key={it.id} className="rounded-xl border border-border/60 p-3">
                {it.kind === "check" ? (
                  <button onClick={() => toggle(it.id)}
                    className={`w-full min-h-14 flex items-center gap-3 rounded-lg px-3 text-left font-medium transition-colors ${
                      answers[it.id]?.checked ? "bg-green-500/15 text-green-300" : "bg-muted/40"
                    }`}>
                    <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border text-lg ${
                      answers[it.id]?.checked ? "border-green-400 bg-green-400 text-black" : "border-border"
                    }`}>
                      {answers[it.id]?.checked ? "✓" : ""}
                    </span>
                    <span className="flex-1">{it.label}
                      {it.required && <Badge variant="outline" className="ml-2 text-[10px]">REQUIRED</Badge>}
                    </span>
                  </button>
                ) : (
                  <div>
                    <p className="font-medium mb-2">{it.label}</p>
                    <Input className="min-h-14" placeholder={it.hint || "Type here…"}
                      value={answers[it.id]?.note || ""} onChange={(e) => setNote(it.id, e.target.value)} />
                  </div>
                )}
                {it.kind === "check" && it.hint && (
                  <p className="text-xs text-muted-foreground mt-1.5 px-1">{it.hint}</p>
                )}
              </div>
            ))}
            <div>
              <p className="font-medium mb-2 flex items-center gap-2"><Pen className="h-4 w-4" />Engineer name</p>
              <Input className="min-h-14" placeholder="Your full name" value={engineer}
                onChange={(e) => setEngineer(e.target.value)} />
            </div>
            <div>
              <p className="font-medium mb-2">Sign to confirm</p>
              <SignaturePad onSave={setSignature} label="Sign here" />
            </div>
            {error && <p className="text-sm text-red-400">{error}</p>}
            <Button size="lg" className="w-full min-h-14 text-base" onClick={submit} disabled={submitting || !engineer}>
              {submitting ? "Submitting…" : "Submit assessment"}
            </Button>
          </CardContent>
        </Card>
      )}

      {verdict && (
        <Card className={verdict.passed ? "border-green-500/50" : "border-red-500/50"}>
          <CardContent className="py-10 text-center space-y-4">
            {verdict.passed ? (
              <>
                <ShieldCheck className="h-16 w-16 mx-auto text-green-400" />
                <h2 className="text-3xl font-bold text-green-400">PASS — safe to start</h2>
                <p className="text-muted-foreground">All required checks confirmed and recorded.</p>
              </>
            ) : (
              <>
                <AlertTriangle className="h-16 w-16 mx-auto text-red-400" />
                <h2 className="text-3xl font-bold text-red-400">STOP — do not start</h2>
                <p className="text-muted-foreground">Outstanding required checks:</p>
                <div className="flex flex-wrap gap-2 justify-center">
                  {(verdict.failed_items || []).map((f: string) => (
                    <Badge key={f} variant="outline" className="text-red-300 border-red-500/40">{f}</Badge>
                  ))}
                </div>
              </>
            )}
            <Button size="lg" variant="outline" className="min-h-12" onClick={reset}>
              New assessment
            </Button>
          </CardContent>
        </Card>
      )}

      {history.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-lg">History for this job</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {history.map((h: any) => (
              <div key={h.id} className="flex items-center justify-between text-sm py-2 border-b last:border-0">
                <span>{h.template_name} · {h.engineer_name || "—"}</span>
                <span className="text-muted-foreground">
                  {h.created_at ? new Date(h.created_at).toLocaleString("en-GB") : ""}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
