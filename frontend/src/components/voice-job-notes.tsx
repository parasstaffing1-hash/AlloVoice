"use client";

import { useState, useRef, useCallback } from "react";
import { useAuth } from "@/lib/store";
import { apiRequest } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";

interface PartUsed {
  name: string;
  quantity: number;
  condition: "new" | "reused";
}

interface JobReport {
  work_performed: string[];
  parts_used: PartUsed[];
  findings: string[];
  recommendations: string[];
  duration_minutes: number;
  follow_up_required: boolean;
  follow_up_details: string;
  report_markdown: string;
}

export function VoiceJobNotes({ jobId }: { jobId: string }) {
  const { token } = useAuth();
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [report, setReport] = useState<JobReport | null>(null);
  const [saving, setSaving] = useState(false);
  const [structuring, setStructuring] = useState(false);
  const [refining, setRefining] = useState(false);
  const [duration, setDuration] = useState(0);
  const [followUp, setFollowUp] = useState(false);
  const [followUpDetails, setFollowUpDetails] = useState("");
  const recognitionRef = useRef<any>(null);

  const startRecording = useCallback(() => {
    const SpeechRecognition =
      (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-GB";

    recognition.onresult = (event: any) => {
      let finalTranscript = "";
      for (let i = 0; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        }
      }
      if (finalTranscript) {
        setTranscript((prev) => (prev ? prev + " " + finalTranscript : finalTranscript));
      }
    };

    recognition.onerror = () => {
      setIsRecording(false);
    };

    recognition.onend = () => {
      setIsRecording(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsRecording(true);
  }, []);

  const stopRecording = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    setIsRecording(false);
  }, []);

  const handleTranscribeAudio = async () => {
    if (!token || !transcript.trim()) return;
    setStructuring(true);
    try {
      const result: any = await apiRequest("/api/voice-notes/transcribe-job", {
        method: "POST",
        body: JSON.stringify({ transcript, job_id: jobId }),
        token,
      });
      setReport(result);
      setDuration(result.duration_minutes || 0);
      setFollowUp(result.follow_up_required || false);
      setFollowUpDetails(result.follow_up_details || "");
    } catch (e) {
      console.error("Failed to structure report", e);
    } finally {
      setStructuring(false);
    }
  };

  const handleRefine = async (style: "professional" | "casual" | "detailed") => {
    if (!token || !transcript.trim()) return;
    setRefining(true);
    try {
      const result: any = await apiRequest("/api/voice-notes/refine", {
        method: "POST",
        body: JSON.stringify({ transcript, style }),
        token,
      });
      setTranscript(result.refined_text);
    } catch (e) {
      console.error("Failed to refine transcript", e);
    } finally {
      setRefining(false);
    }
  };

  const handleSave = async () => {
    if (!token || !report) return;
    setSaving(true);
    try {
      const notes = {
        ...report,
        duration_minutes: duration,
        follow_up_required: followUp,
        follow_up_details: followUpDetails,
      };
      await apiRequest("/api/voice-notes/save", {
        method: "POST",
        body: JSON.stringify({ job_id: jobId, notes }),
        token,
      });
    } catch (e) {
      console.error("Failed to save notes", e);
    } finally {
      setSaving(false);
    }
  };

  const updatePart = (index: number, field: keyof PartUsed, value: any) => {
    if (!report) return;
    const updated = [...report.parts_used];
    updated[index] = { ...updated[index], [field]: value };
    setReport({ ...report, parts_used: updated });
  };

  const removePart = (index: number) => {
    if (!report) return;
    setReport({ ...report, parts_used: report.parts_used.filter((_, i) => i !== index) });
  };

  const addPart = () => {
    if (!report) return;
    setReport({
      ...report,
      parts_used: [...report.parts_used, { name: "", quantity: 1, condition: "new" }],
    });
  };

  const toggleWorkItem = (index: number) => {
    if (!report) return;
    const updated = [...report.work_performed];
    updated[index] = updated[index].startsWith("[done] ")
      ? updated[index].slice(7)
      : `[done] ${updated[index]}`;
    setReport({ ...report, work_performed: updated });
  };

  return (
    <div className="space-y-4">
      {/* Recording Section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            Voice Job Notes
            {isRecording && (
              <span className="flex items-center gap-1.5 text-sm text-red-500">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
                </span>
                Recording
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Button
              onClick={isRecording ? stopRecording : startRecording}
              variant={isRecording ? "destructive" : "default"}
            >
              {isRecording ? "Stop" : "Record"}
            </Button>
            <Button
              onClick={handleTranscribeAudio}
              disabled={!transcript.trim() || structuring}
              variant="outline"
            >
              {structuring ? "Structuring..." : "Structure Report"}
            </Button>
          </div>

          <Textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            placeholder="Speak or type the job notes here..."
            rows={4}
          />

          <div className="flex gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => handleRefine("professional")}
              disabled={!transcript.trim() || refining}
            >
              Professional
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => handleRefine("casual")}
              disabled={!transcript.trim() || refining}
            >
              Casual
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => handleRefine("detailed")}
              disabled={!transcript.trim() || refining}
            >
              Detailed
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Structured Report */}
      {report && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Job Report</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* Work Performed */}
            {report.work_performed.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold mb-2">Work Performed</h4>
                <ul className="space-y-1">
                  {report.work_performed.map((item, i) => (
                    <li key={i} className="flex items-center gap-2 text-sm">
                      <button
                        onClick={() => toggleWorkItem(i)}
                        className={`w-4 h-4 rounded border flex-shrink-0 flex items-center justify-center ${
                          item.startsWith("[done]")
                            ? "bg-green-500 border-green-500 text-white"
                            : "border-muted-foreground"
                        }`}
                      >
                        {item.startsWith("[done]") && "✓"}
                      </button>
                      <span className={item.startsWith("[done]") ? "line-through text-muted-foreground" : ""}>
                        {item.replace("[done] ", "")}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Parts Used */}
            {report.parts_used.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-semibold">Parts Used</h4>
                  <Button size="sm" variant="ghost" onClick={addPart}>
                    + Add
                  </Button>
                </div>
                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-muted">
                        <th className="text-left p-2">Part</th>
                        <th className="text-left p-2 w-20">Qty</th>
                        <th className="text-left p-2 w-24">Condition</th>
                        <th className="p-2 w-10"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.parts_used.map((part, i) => (
                        <tr key={i} className="border-t">
                          <td className="p-2">
                            <input
                              value={part.name}
                              onChange={(e) => updatePart(i, "name", e.target.value)}
                              className="w-full bg-transparent text-sm"
                              placeholder="Part name"
                            />
                          </td>
                          <td className="p-2">
                            <input
                              type="number"
                              value={part.quantity}
                              onChange={(e) =>
                                updatePart(i, "quantity", parseInt(e.target.value) || 1)
                              }
                              className="w-full bg-transparent text-sm"
                              min={1}
                            />
                          </td>
                          <td className="p-2">
                            <select
                              value={part.condition}
                              onChange={(e) =>
                                updatePart(i, "condition", e.target.value)
                              }
                              className="w-full bg-transparent text-sm"
                            >
                              <option value="new">New</option>
                              <option value="reused">Reused</option>
                            </select>
                          </td>
                          <td className="p-2 text-center">
                            <button
                              onClick={() => removePart(i)}
                              className="text-destructive text-xs"
                            >
                              ✕
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Findings */}
            {report.findings.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold mb-2">Findings</h4>
                <ul className="space-y-1">
                  {report.findings.map((f, i) => (
                    <li key={i} className="text-sm flex items-start gap-2">
                      <span className="text-muted-foreground mt-0.5">•</span>
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Recommendations */}
            {report.recommendations.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold mb-2">Recommendations</h4>
                <ul className="space-y-2">
                  {report.recommendations.map((r, i) => (
                    <li key={i} className="flex items-center justify-between text-sm">
                      <span className="flex items-start gap-2">
                        <span className="text-muted-foreground mt-0.5">•</span>
                        {r}
                      </span>
                      <Button size="sm" variant="outline" className="ml-2 flex-shrink-0">
                        Add to Quote
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Duration */}
            <div>
              <h4 className="text-sm font-semibold mb-2">Duration</h4>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={duration}
                  onChange={(e) => setDuration(parseInt(e.target.value) || 0)}
                  className="w-20 bg-transparent border rounded px-2 py-1 text-sm"
                  min={0}
                />
                <span className="text-sm text-muted-foreground">minutes</span>
                <Badge variant="secondary" className="ml-2">
                  {Math.floor(duration / 60)}h {duration % 60}m
                </Badge>
              </div>
            </div>

            {/* Follow-up */}
            <div>
              <div className="flex items-center gap-2 mb-2">
                <h4 className="text-sm font-semibold">Follow-up Required</h4>
                <button
                  onClick={() => setFollowUp(!followUp)}
                  className={`relative w-10 h-5 rounded-full transition-colors ${
                    followUp ? "bg-green-500" : "bg-muted"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                      followUp ? "translate-x-5" : ""
                    }`}
                  />
                </button>
              </div>
              {followUp && (
                <Textarea
                  value={followUpDetails}
                  onChange={(e) => setFollowUpDetails(e.target.value)}
                  placeholder="Describe the follow-up work needed..."
                  rows={2}
                />
              )}
            </div>
          </CardContent>
          <CardFooter>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : "Save to Job"}
            </Button>
          </CardFooter>
        </Card>
      )}
    </div>
  );
}
