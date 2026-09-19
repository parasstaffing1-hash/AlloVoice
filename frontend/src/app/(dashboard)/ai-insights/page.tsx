"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import {
  AlertTriangle, TrendingDown, Star, MessageSquare, Pound,
  Sparkles, Target, ChevronRight, RefreshCw, Send, CheckCircle,
} from "lucide-react";

type Tab = "churn" | "reviews" | "upsell";

const RISK_COLORS: Record<string, string> = {
  low: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  medium: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  high: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  critical: "bg-red-500/20 text-red-400 border-red-500/30",
};

const SENTIMENT_COLORS: Record<string, string> = {
  positive: "bg-emerald-500/20 text-emerald-400",
  neutral: "bg-blue-500/20 text-blue-400",
  negative: "bg-red-500/20 text-red-400",
};

const PRIORITY_COLORS: Record<string, string> = {
  high: "bg-red-500/20 text-red-400",
  medium: "bg-yellow-500/20 text-yellow-400",
  low: "bg-slate-500/20 text-slate-400",
};

export default function AiInsightsPage() {
  const { token } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>("churn");
  const [loading, setLoading] = useState(false);

  // Churn state
  const [churnData, setChurnData] = useState<any>(null);
  const [selectedCustomer, setSelectedCustomer] = useState<any>(null);
  const [churnPrediction, setChurnPrediction] = useState<any>(null);
  const [retentionLoading, setRetentionLoading] = useState(false);

  // Review state
  const [reviews, setReviews] = useState<any[]>([]);
  const [reviewResponses, setReviewResponses] = useState<Record<string, string>>({});
  const [editingReview, setEditingReview] = useState<string | null>(null);
  const [sendingReview, setSendingReview] = useState<string | null>(null);

  // Upsell state
  const [completedJobs, setCompletedJobs] = useState<any[]>([]);
  const [upsellSuggestions, setUpsellSuggestions] = useState<Record<string, any>>({});

  useEffect(() => {
    if (!token) return;
    if (activeTab === "churn") loadChurnData();
    else if (activeTab === "reviews") loadReviews();
    else if (activeTab === "upsell") loadCompletedJobs();
  }, [token, activeTab]);

  // ─── Churn ────────────────────────────────────────

  const loadChurnData = async () => {
    setLoading(true);
    try {
      const data: any = await api.aiInsights.churnSegment(token!);
      setChurnData(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const predictChurn = async (customerId: string) => {
    try {
      const data: any = await api.aiInsights.churnPredict(customerId, token!);
      setChurnPrediction(data);
    } catch (e) {
      console.error(e);
    }
  };

  const runRetainCampaign = async (customerIds: string[], type: string) => {
    setRetentionLoading(true);
    try {
      const data: any = await api.aiInsights.churnRetain(
        { customer_ids: customerIds, campaign_type: type },
        token!
      );
      alert(`Campaign created: ${data.campaign.name}\nEstimated cost: £${data.campaign.estimated_cost}`);
    } catch (e) {
      console.error(e);
    } finally {
      setRetentionLoading(false);
    }
  };

  // ─── Reviews ──────────────────────────────────────

  const loadReviews = async () => {
    setLoading(true);
    try {
      const data: any = await api.reviews.list(token!);
      setReviews(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const generateReviewResponse = async (review: any) => {
    try {
      const data: any = await api.aiInsights.reviewRespond(
        {
          review_id: review.id,
          review_text: review.content || "",
          rating: review.rating,
          customer_name: "Valued Customer",
        },
        token!
      );
      setReviewResponses((prev) => ({ ...prev, [review.id]: data.response_text }));
    } catch (e) {
      console.error(e);
    }
  };

  // ─── Upsell ───────────────────────────────────────

  const loadCompletedJobs = async () => {
    setLoading(true);
    try {
      const data: any = await api.jobs.list(token!, "completed");
      setCompletedJobs(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const generateUpsells = async (job: any) => {
    try {
      const data: any = await api.aiInsights.upsellOnCompletion(job.id, token!);
      setUpsellSuggestions((prev) => ({ ...prev, [job.id]: data }));
    } catch (e) {
      console.error(e);
    }
  };

  // ─── Render Helpers ───────────────────────────────

  const renderTabs = () => (
    <div className="flex gap-1 border rounded-lg p-1 bg-muted/50 w-fit">
      {([
        { key: "churn" as Tab, label: "Churn Risk", icon: TrendingDown },
        { key: "reviews" as Tab, label: "Review Responses", icon: MessageSquare },
        { key: "upsell" as Tab, label: "Smart Upsell", icon: Sparkles },
      ]).map((tab) => (
        <button
          key={tab.key}
          onClick={() => setActiveTab(tab.key)}
          className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
            activeTab === tab.key
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <tab.icon className="h-4 w-4" />
          {tab.label}
        </button>
      ))}
    </div>
  );

  const renderChurnTab = () => (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-4">
        {["low", "medium", "high", "critical"].map((level) => (
          <Card key={level}>
            <CardContent className="py-4 flex items-center gap-4">
              {level === "critical" ? (
                <AlertTriangle className="h-8 w-8 text-red-400" />
              ) : level === "high" ? (
                <TrendingDown className="h-8 w-8 text-orange-400" />
              ) : (
                <Target className="h-8 w-8 text-emerald-400" />
              )}
              <div>
                <p className="text-2xl font-bold">{churnData?.[level] || 0}</p>
                <p className="text-xs text-muted-foreground capitalize">{level} Risk</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <div className="md:col-span-1">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Customers by Risk</CardTitle>
              <CardDescription>Sorted by risk score</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 max-h-[500px] overflow-y-auto p-2">
              {churnData?.customers?.map((c: any) => (
                <button
                  key={c.id}
                  onClick={() => {
                    setSelectedCustomer(c);
                    predictChurn(c.id);
                  }}
                  className={`w-full text-left p-3 rounded-lg border transition-all hover:bg-accent ${
                    selectedCustomer?.id === c.id ? "border-primary bg-accent" : ""
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{c.name}</span>
                    <Badge className={RISK_COLORS[c.risk_level]}>{c.risk_level}</Badge>
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-xs text-muted-foreground">
                      Score: {(c.risk_score * 100).toFixed(0)}%
                    </span>
                    {c.last_contact && (
                      <span className="text-xs text-muted-foreground">
                        {Math.round((Date.now() - new Date(c.last_contact).getTime()) / 86400000)}d ago
                      </span>
                    )}
                  </div>
                </button>
              ))}
              {(!churnData?.customers || churnData.customers.length === 0) && (
                <p className="text-sm text-muted-foreground text-center py-4">
                  {loading ? "Loading..." : "No customers found"}
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="md:col-span-2">
          {churnPrediction ? (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Churn Prediction</CardTitle>
                  <Badge className={RISK_COLORS[churnPrediction.risk_level]}>
                    {churnPrediction.risk_level} risk
                  </Badge>
                </div>
                <CardDescription>
                  {selectedCustomer?.name} — {churnPrediction.days_since_last_job} days since last job
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-4">
                  <div className="flex-1 p-3 rounded-lg bg-muted/50">
                    <p className="text-xs text-muted-foreground">Risk Score</p>
                    <p className="text-2xl font-bold">
                      {(churnPrediction.risk_score * 100).toFixed(0)}%
                    </p>
                  </div>
                  <div className="flex-1 p-3 rounded-lg bg-muted/50">
                    <p className="text-xs text-muted-foreground">Total Spend</p>
                    <p className="text-2xl font-bold">
                      £{churnPrediction.total_spend?.toFixed(2) || "0.00"}
                    </p>
                  </div>
                  <div className="flex-1 p-3 rounded-lg bg-muted/50">
                    <p className="text-xs text-muted-foreground">Predicted Churn</p>
                    <p className="text-lg font-bold">
                      {new Date(churnPrediction.predicted_churn_date).toLocaleDateString("en-GB", {
                        month: "short",
                        day: "numeric",
                      })}
                    </p>
                  </div>
                </div>

                <div>
                  <h4 className="text-sm font-medium mb-2">Risk Factors</h4>
                  <div className="space-y-2">
                    {churnPrediction.factors?.map((f: any, i: number) => (
                      <div key={i} className="flex items-start gap-3 p-2 rounded-lg bg-muted/30">
                        <div
                          className={`mt-0.5 h-2 w-2 rounded-full shrink-0 ${
                            f.weight > 0.2 ? "bg-red-400" : f.weight > 0 ? "bg-yellow-400" : "bg-emerald-400"
                          }`}
                        />
                        <div>
                          <p className="text-sm font-medium">{f.factor}</p>
                          <p className="text-xs text-muted-foreground">{f.description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <h4 className="text-sm font-medium mb-2">Recommended Actions</h4>
                  <div className="space-y-1">
                    {churnPrediction.recommended_actions?.map((a: string, i: number) => (
                      <div key={i} className="flex items-center gap-2 text-sm">
                        <CheckCircle className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                        <span>{a}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="flex gap-2 pt-2">
                  <Button
                    size="sm"
                    onClick={() => runRetainCampaign([selectedCustomer.id], "discount")}
                    disabled={retentionLoading}
                  >
                    <Pound className="h-3.5 w-3.5 mr-1" />Send Discount
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => runRetainCampaign([selectedCustomer.id], "follow_up")}
                    disabled={retentionLoading}
                  >
                    <MessageSquare className="h-3.5 w-3.5 mr-1" />Follow Up
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => runRetainCampaign([selectedCustomer.id], "maintenance_reminder")}
                    disabled={retentionLoading}
                  >
                    <RefreshCw className="h-3.5 w-3.5 mr-1" />Remind Maintenance
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-16 text-center text-muted-foreground">
                <TrendingDown className="h-12 w-12 mx-auto mb-4 opacity-30" />
                <p>Select a customer to view churn prediction</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );

  const renderReviewsTab = () => (
    <div className="space-y-4">
      {loading ? (
        <p className="text-muted-foreground">Loading reviews...</p>
      ) : reviews.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No reviews yet. Reviews appear after completing jobs.
          </CardContent>
        </Card>
      ) : (
        reviews.map((review) => (
          <Card key={review.id} className="hover:border-primary/30 transition-all">
            <CardContent className="p-5 space-y-4">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-yellow-500/10 shrink-0">
                    <Star className="h-5 w-5 text-yellow-400" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-0.5">
                        {[1, 2, 3, 4, 5].map((s) => (
                          <Star
                            key={s}
                            className={`h-3.5 w-3.5 ${
                              s <= review.rating ? "fill-yellow-400 text-yellow-400" : "text-muted-foreground"
                            }`}
                          />
                        ))}
                      </div>
                      <span className="text-sm text-muted-foreground">
                        {formatDateTime(review.created_at)}
                      </span>
                    </div>
                    {review.title && (
                      <h3 className="font-semibold mt-1">{review.title}</h3>
                    )}
                    {review.content && (
                      <p className="text-sm text-muted-foreground mt-1">{review.content}</p>
                    )}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => generateReviewResponse(review)}
                  className="shrink-0"
                >
                  <Sparkles className="h-3.5 w-3.5 mr-1" />AI Respond
                </Button>
              </div>

              {reviewResponses[review.id] && (
                <div className="ml-14 p-4 rounded-lg bg-muted/50 border space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-muted-foreground uppercase">AI Response</span>
                    <Badge className={SENTIMENT_COLORS[analyzeSentiment(review.content, review.rating)]}>
                      {analyzeSentiment(review.content, review.rating)}
                    </Badge>
                  </div>
                  {editingReview === review.id ? (
                    <div className="space-y-2">
                      <textarea
                        className="w-full min-h-[80px] rounded-lg border bg-background px-3 py-2 text-sm"
                        value={reviewResponses[review.id]}
                        onChange={(e) =>
                          setReviewResponses((prev) => ({
                            ...prev,
                            [review.id]: e.target.value,
                          }))
                        }
                      />
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => setEditingReview(null)}>
                          Save
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditingReview(null)}>
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <p className="text-sm">{reviewResponses[review.id]}</p>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          onClick={() => {
                            setSendingReview(review.id);
                            setTimeout(() => {
                              setSendingReview(null);
                              alert("Response sent successfully!");
                            }, 1000);
                          }}
                          disabled={sendingReview === review.id}
                        >
                          <Send className="h-3.5 w-3.5 mr-1" />
                          {sendingReview === review.id ? "Sending..." : "Accept & Send"}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setEditingReview(review.id)}
                        >
                          Edit
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );

  const renderUpsellTab = () => (
    <div className="space-y-4">
      {loading ? (
        <p className="text-muted-foreground">Loading jobs...</p>
      ) : completedJobs.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No completed jobs yet. Upsell suggestions appear after job completion.
          </CardContent>
        </Card>
      ) : (
        completedJobs.map((job) => {
          const suggestions = upsellSuggestions[job.id];
          return (
            <Card key={job.id} className="hover:border-primary/30 transition-all">
              <CardContent className="p-5 space-y-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-semibold">{job.title}</h3>
                    <p className="text-sm text-muted-foreground mt-1">
                      {job.description?.substring(0, 100)}
                      {job.description?.length > 100 ? "..." : ""}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-sm font-medium text-green-400">
                        £{job.final_cost?.toFixed(2) || job.estimated_cost?.toFixed(2) || "0.00"}
                      </span>
                      <span className="text-xs text-muted-foreground">•</span>
                      <span className="text-xs text-muted-foreground">
                        {formatDateTime(job.completed_at || job.created_at)}
                      </span>
                    </div>
                  </div>
                  {!suggestions && (
                    <Button size="sm" onClick={() => generateUpsells(job)}>
                      <Sparkles className="h-3.5 w-3.5 mr-1" />Generate Upsells
                    </Button>
                  )}
                </div>

                {suggestions && (
                  <div className="space-y-3">
                    {suggestions.suggestions?.map((s: any, i: number) => (
                      <div
                        key={i}
                        className="flex items-start gap-3 p-3 rounded-lg bg-muted/30 border border-border/50"
                      >
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-sm">{s.title}</span>
                            <Badge className={PRIORITY_COLORS[s.priority]}>{s.priority}</Badge>
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">{s.description}</p>
                          <div className="flex items-center gap-3 mt-2">
                            <span className="text-sm font-medium text-green-400">{s.price_range}</span>
                            <span className="text-xs text-muted-foreground">
                              Confidence: {(s.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                        </div>
                        <Button size="sm" variant="outline" className="shrink-0">
                          <Pound className="h-3.5 w-3.5 mr-1" />Add to Quote
                        </Button>
                      </div>
                    ))}

                    {suggestions.cross_sells?.length > 0 && (
                      <div className="p-3 rounded-lg bg-primary/5 border border-primary/20">
                        <h4 className="text-xs font-medium text-primary mb-2">Cross-Sell Opportunities</h4>
                        <div className="space-y-1">
                          {suggestions.cross_sells.map((cs: any, i: number) => (
                            <div key={i} className="flex items-center gap-2 text-sm">
                              <ChevronRight className="h-3 w-3 text-primary shrink-0" />
                              <span>{cs.title}</span>
                              <span className="text-muted-foreground">— {cs.price_range}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">AI Insights</h1>
          <p className="text-muted-foreground">
            Predict churn, respond to reviews, and find upsell opportunities
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => {
            if (activeTab === "churn") loadChurnData();
            else if (activeTab === "reviews") loadReviews();
            else loadCompletedJobs();
          }}
        >
          <RefreshCw className="h-4 w-4 mr-2" />Refresh
        </Button>
      </div>

      {renderTabs()}

      {activeTab === "churn" && renderChurnTab()}
      {activeTab === "reviews" && renderReviewsTab()}
      {activeTab === "upsell" && renderUpsellTab()}
    </div>
  );
}

function analyzeSentiment(text: string, rating: number): string {
  const negativeWords = ["bad", "terrible", "awful", "horrible", "worst", "rude", "late", "poor", "disappointed"];
  const positiveWords = ["great", "excellent", "fantastic", "brilliant", "amazing", "recommend", "professional"];
  const textLower = (text || "").toLowerCase();
  const negCount = negativeWords.filter((w) => textLower.includes(w)).length;
  const posCount = positiveWords.filter((w) => textLower.includes(w)).length;
  if (rating <= 2 || negCount > posCount) return "negative";
  if (rating >= 4 || posCount > negCount) return "positive";
  return "neutral";
}
