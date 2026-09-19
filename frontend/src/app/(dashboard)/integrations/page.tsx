"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  Plug,
  Building2,
  Star,
  Mail,
  Zap,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Send,
  Trash2,
} from "lucide-react";

function StatusBadge({ connected }: { connected: boolean }) {
  return connected ? (
    <Badge className="bg-green-500/15 text-green-400 border-green-500/30 flex items-center gap-1">
      <CheckCircle2 className="h-3 w-3" /> Connected
    </Badge>
  ) : (
    <Badge className="bg-red-500/15 text-red-400 border-red-500/30 flex items-center gap-1">
      <XCircle className="h-3 w-3" /> Disconnected
    </Badge>
  );
}

const fmtGBP = (n: number) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(n ?? 0);

const fmtDate = (d: string) => {
  try {
    return new Date(d).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return d;
  }
};

export default function IntegrationsPage() {
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // QuickBooks
  const [qb, setQb] = useState<any>(null);
  const [qbPL, setQbPL] = useState<any>(null);
  const [qbSyncMsg, setQbSyncMsg] = useState<string | null>(null);

  // Google
  const [googleStatus, setGoogleStatus] = useState<any>(null);
  const [googleReviews, setGoogleReviews] = useState<any[]>([]);
  const [locationId, setLocationId] = useState("");
  const [replyTexts, setReplyTexts] = useState<Record<string, string>>({});

  // Trustpilot
  const [tpStatus, setTpStatus] = useState<any>(null);
  const [tpApiKey, setTpApiKey] = useState("");
  const [tpBuId, setTpBuId] = useState("");
  const [tpInvitations, setTpInvitations] = useState<any[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteJobId, setInviteJobId] = useState("");

  // Brevo / marketing
  const [mktStatus, setMktStatus] = useState<any>(null);
  const [winback, setWinback] = useState<any>(null);
  const [campName, setCampName] = useState("");
  const [campSubject, setCampSubject] = useState("");
  const [campHtml, setCampHtml] = useState("");
  const [campList, setCampList] = useState("");

  // Zapier / Make
  const [triggers, setTriggers] = useState<any[]>([]);
  const [subs, setSubs] = useState<any[]>([]);
  const [subTrigger, setSubTrigger] = useState("");
  const [subUrl, setSubUrl] = useState("");

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const refreshAll = () => {
    if (!token) return;
    setLoading(true);
    api.quickbooks
      .status(token)
      .then((r: any) => setQb(r))
      .catch(() => setQb({ connected: false }));
    api.quickbooks
      .profitLoss(token)
      .then((r: any) => setQbPL(r))
      .catch(() => setQbPL(null));
    api.reviewPlatforms
      .googleStatus(token)
      .then((r: any) => setGoogleStatus(r))
      .catch(() => setGoogleStatus({ connected: false }));
    api.reviewPlatforms
      .googleReviews(token)
      .then((r: any) => setGoogleReviews(Array.isArray(r) ? r : r?.reviews ?? []))
      .catch(() => setGoogleReviews([]));
    api.reviewPlatforms
      .trustpilotStatus(token)
      .then((r: any) => setTpStatus(r))
      .catch(() => setTpStatus({ connected: false }));
    api.reviewPlatforms
      .trustpilotInvitations(token)
      .then((r: any) => setTpInvitations(Array.isArray(r) ? r : r?.invitations ?? []))
      .catch(() => setTpInvitations([]));
    api.marketing
      .status(token)
      .then((r: any) => setMktStatus(r))
      .catch(() => setMktStatus(null));
    api.marketing
      .zapierTriggers(token)
      .then((r: any) => setTriggers(Array.isArray(r) ? r : r?.triggers ?? []))
      .catch(() => setTriggers([]));
    api.marketing
      .zapierSubscriptions(token)
      .then((r: any) => setSubs(Array.isArray(r) ? r : r?.subscriptions ?? []))
      .catch(() => setSubs([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!token) return;
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // ---------- QuickBooks actions ----------
  const qbConnect = () => {
    if (!token) return;
    setBusy("qb-connect");
    api.quickbooks
      .authUrl(token)
      .then((r: any) => {
        const url = r?.auth_url ?? r?.url;
        if (url) window.open(url, "_blank");
        else showToast("No auth URL returned");
      })
      .catch((e: any) => showToast(e.message || "QuickBooks connect failed"))
      .finally(() => setBusy(null));
  };

  const qbDisconnect = () => {
    if (!token) return;
    setBusy("qb-disconnect");
    api.quickbooks
      .disconnect(token)
      .then((r: any) => {
        showToast("QuickBooks disconnected");
        refreshAll();
      })
      .catch((e: any) => showToast(e.message || "Disconnect failed"))
      .finally(() => setBusy(null));
  };

  const qbSync = (kind: "invoices" | "contacts" | "payments") => {
    if (!token) return;
    setBusy(`qb-${kind}`);
    setQbSyncMsg(null);
    const call =
      kind === "invoices"
        ? api.quickbooks.syncInvoices(token)
        : kind === "contacts"
          ? api.quickbooks.syncContacts(token)
          : api.quickbooks.syncPayments(token);
    call
      .then((r: any) => {
        const count = r?.synced ?? r?.count ?? r?.total ?? JSON.stringify(r);
        setQbSyncMsg(`${kind}: ${count} synced`);
        showToast(`QuickBooks ${kind} synced (${count})`);
        refreshAll();
      })
      .catch((e: any) => {
        setQbSyncMsg(`${kind} sync failed: ${e.message}`);
        showToast(e.message || "Sync failed");
      })
      .finally(() => setBusy(null));
  };

  // ---------- Google actions ----------
  const googleConnect = () => {
    if (!token || !locationId.trim()) {
      showToast("Enter a location ID first");
      return;
    }
    setBusy("google-connect");
    api.reviewPlatforms
      .googleConnect(locationId.trim(), token)
      .then((r: any) => {
        showToast("Google Business Profile connected");
        setLocationId("");
        refreshAll();
      })
      .catch((e: any) => showToast(e.message || "Google connect failed"))
      .finally(() => setBusy(null));
  };

  const googleDisconnect = () => {
    if (!token) return;
    setBusy("google-disconnect");
    api.reviewPlatforms
      .googleDisconnect(token)
      .then((r: any) => {
        showToast("Google disconnected");
        refreshAll();
      })
      .catch((e: any) => showToast(e.message || "Disconnect failed"))
      .finally(() => setBusy(null));
  };

  const googleReply = (reviewId: string) => {
    if (!token) return;
    const text = (replyTexts[reviewId] || "").trim();
    if (!text) {
      showToast("Type a reply first");
      return;
    }
    setBusy(`reply-${reviewId}`);
    api.reviewPlatforms
      .googleReply(reviewId, text, token)
      .then((r: any) => {
        showToast("Reply posted");
        setReplyTexts((p) => ({ ...p, [reviewId]: "" }));
        refreshAll();
      })
      .catch((e: any) => showToast(e.message || "Reply failed"))
      .finally(() => setBusy(null));
  };

  // ---------- Trustpilot actions ----------
  const tpConnect = () => {
    if (!token) return;
    if (!tpApiKey.trim() || !tpBuId.trim()) {
      showToast("Enter API key + business unit ID");
      return;
    }
    setBusy("tp-connect");
    api.reviewPlatforms
      .trustpilotConnect({ api_key: tpApiKey.trim(), business_unit_id: tpBuId.trim() }, token)
      .then((r: any) => {
        showToast("Trustpilot connected");
        setTpApiKey("");
        setTpBuId("");
        refreshAll();
      })
      .catch((e: any) => showToast(e.message || "Trustpilot connect failed"))
      .finally(() => setBusy(null));
  };

  const tpInvite = () => {
    if (!token) return;
    if (!inviteEmail.trim() || !inviteJobId.trim()) {
      showToast("Enter customer email + job ID");
      return;
    }
    setBusy("tp-invite");
    api.reviewPlatforms
      .trustpilotInvite(
        { customer_id: inviteEmail.trim(), job_id: inviteJobId.trim(), email: inviteEmail.trim() },
        token
      )
      .then((r: any) => {
        showToast("Trustpilot invitation sent");
        setInviteEmail("");
        setInviteJobId("");
        refreshAll();
      })
      .catch((e: any) => showToast(e.message || "Invite failed"))
      .finally(() => setBusy(null));
  };

  // ---------- Brevo actions ----------
  const mktSyncContacts = () => {
    if (!token) return;
    setBusy("mkt-sync");
    api.marketing
      .syncContacts(token)
      .then((r: any) => {
        showToast(`Contacts synced (${r?.synced ?? r?.count ?? "done"})`);
        refreshAll();
      })
      .catch((e: any) => showToast(e.message || "Sync failed"))
      .finally(() => setBusy(null));
  };

  const mktWinback = () => {
    if (!token) return;
    setBusy("mkt-winback");
    api.marketing
      .winback(token)
      .then((r: any) => {
        setWinback(r);
        showToast(`Win-back preview: ${r?.target_count ?? 0} targets`);
      })
      .catch((e: any) => showToast(e.message || "Win-back preview failed"))
      .finally(() => setBusy(null));
  };

  const mktSendCampaign = () => {
    if (!token) return;
    if (!campName.trim() || !campSubject.trim() || !campHtml.trim() || !campList.trim()) {
      showToast("Fill name, subject, HTML and list ID");
      return;
    }
    setBusy("mkt-campaign");
    api.marketing
      .sendCampaign(
        { name: campName.trim(), subject: campSubject.trim(), html_content: campHtml, list_id: campList.trim() },
        token
      )
      .then((r: any) => {
        showToast("Campaign sent");
        setCampName("");
        setCampSubject("");
        setCampHtml("");
        setCampList("");
        refreshAll();
      })
      .catch((e: any) => showToast(e.message || "Campaign failed"))
      .finally(() => setBusy(null));
  };

  // ---------- Zapier actions ----------
  const zapSubscribe = () => {
    if (!token) return;
    if (!subTrigger || !subUrl.trim()) {
      showToast("Pick a trigger + target URL");
      return;
    }
    setBusy("zap-sub");
    api.marketing
      .zapierSubscribe(subTrigger, subUrl.trim(), token)
      .then((r: any) => {
        showToast("Webhook subscribed");
        setSubTrigger("");
        setSubUrl("");
        refreshAll();
      })
      .catch((e: any) => showToast(e.message || "Subscribe failed"))
      .finally(() => setBusy(null));
  };

  const zapUnsubscribe = (id: string) => {
    if (!token) return;
    setBusy(`zap-del-${id}`);
    api.marketing
      .zapierUnsubscribe(id, token)
      .then((r: any) => {
        showToast("Subscription removed");
        refreshAll();
      })
      .catch((e: any) => showToast(e.message || "Delete failed"))
      .finally(() => setBusy(null));
  };

  const zapTest = (trigger: string) => {
    if (!token) return;
    setBusy(`zap-test-${trigger}`);
    api.marketing
      .zapierTest(trigger, token)
      .then((r: any) => showToast(`Test event sent for ${trigger}`))
      .catch((e: any) => showToast(e.message || "Test failed"))
      .finally(() => setBusy(null));
  };

  const qbConnected = !!qb?.connected;
  const gConnected = !!(googleStatus?.connected ?? googleStatus?.google_connected);
  const tpConnected = !!(tpStatus?.connected ?? tpStatus?.trustpilot_connected);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-muted-foreground">Loading integrations...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Plug className="h-7 w-7 text-primary" /> Integrations
          </h1>
          <p className="text-muted-foreground">Connect QuickBooks, reviews, marketing and automation.</p>
        </div>
        <Button variant="outline" size="sm" onClick={refreshAll} disabled={!token}>
          <RefreshCw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>

      {toast && (
        <div className="rounded-lg border border-primary/30 bg-primary/10 px-4 py-2 text-sm">{toast}</div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* QuickBooks */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Building2 className="h-5 w-5 text-green-400" /> QuickBooks
            </CardTitle>
            <StatusBadge connected={qbConnected} />
          </CardHeader>
          <CardContent className="space-y-4">
            {qbConnected ? (
              <div className="text-sm space-y-1">
                <p>
                  <span className="text-muted-foreground">Company: </span>
                  <span className="font-medium">{qb?.company_name ?? "Connected"}</span>
                </p>
                {qb?.last_synced && (
                  <p>
                    <span className="text-muted-foreground">Last synced: </span>
                    {fmtDate(qb.last_synced)}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Sync invoices, contacts and payments with QuickBooks Online.
              </p>
            )}

            {qbPL && (
              <div className="grid grid-cols-3 gap-2 rounded-lg border border-border/50 bg-background/50 p-3 text-center">
                <div>
                  <p className="text-xs text-muted-foreground">Revenue</p>
                  <p className="font-semibold text-green-400">{fmtGBP(qbPL.revenue ?? 0)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Expenses</p>
                  <p className="font-semibold text-red-400">{fmtGBP(qbPL.expenses ?? 0)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Profit</p>
                  <p className="font-semibold">{fmtGBP(qbPL.profit ?? 0)}</p>
                </div>
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              {!qbConnected ? (
                <Button size="sm" onClick={qbConnect} disabled={busy === "qb-connect"}>
                  Connect QuickBooks
                </Button>
              ) : (
                <>
                  <Button size="sm" variant="outline" onClick={() => qbSync("invoices")} disabled={!!busy}>
                    <RefreshCw className="h-3 w-3 mr-1" /> Invoices
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => qbSync("contacts")} disabled={!!busy}>
                    <RefreshCw className="h-3 w-3 mr-1" /> Contacts
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => qbSync("payments")} disabled={!!busy}>
                    <RefreshCw className="h-3 w-3 mr-1" /> Payments
                  </Button>
                  <Button size="sm" variant="destructive" onClick={qbDisconnect} disabled={busy === "qb-disconnect"}>
                    Disconnect
                  </Button>
                </>
              )}
            </div>
            {qbSyncMsg && <p className="text-xs text-muted-foreground">{qbSyncMsg}</p>}
          </CardContent>
        </Card>

        {/* Google Business Profile */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Star className="h-5 w-5 text-yellow-400" /> Google Business Profile
            </CardTitle>
            <StatusBadge connected={gConnected} />
          </CardHeader>
          <CardContent className="space-y-3">
            {!gConnected ? (
              <div className="flex gap-2">
                <Input
                  placeholder="Location ID (e.g. accounts/123/locations/456)"
                  value={locationId}
                  onChange={(e) => setLocationId(e.target.value)}
                />
                <Button size="sm" onClick={googleConnect} disabled={busy === "google-connect"}>
                  Connect
                </Button>
              </div>
            ) : (
              <Button size="sm" variant="destructive" onClick={googleDisconnect} disabled={busy === "google-disconnect"}>
                Disconnect
              </Button>
            )}

            <div className="space-y-3 max-h-72 overflow-y-auto">
              {googleReviews.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">No recent reviews</p>
              ) : (
                googleReviews.slice(0, 5).map((rev: any, i: number) => {
                  const id = rev.id ?? rev.review_id ?? String(i);
                  return (
                    <div key={id} className="rounded-lg border border-border/50 bg-background/50 p-3 space-y-2">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium">{rev.author ?? rev.reviewer ?? "Customer"}</p>
                        <span className="text-xs text-yellow-400">
                          {"★".repeat(Math.round(rev.rating ?? rev.stars ?? 0))}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground">{rev.text ?? rev.comment ?? ""}</p>
                      <div className="flex gap-2">
                        <Input
                          placeholder="Write a reply..."
                          value={replyTexts[id] || ""}
                          onChange={(e) => setReplyTexts((p) => ({ ...p, [id]: e.target.value }))}
                        />
                        <Button size="sm" onClick={() => googleReply(id)} disabled={busy === `reply-${id}`}>
                          <Send className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </CardContent>
        </Card>

        {/* Trustpilot */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Star className="h-5 w-5 text-green-400" /> Trustpilot
            </CardTitle>
            <StatusBadge connected={tpConnected} />
          </CardHeader>
          <CardContent className="space-y-3">
            {!tpConnected && (
              <div className="space-y-2">
                <Input placeholder="API key" value={tpApiKey} onChange={(e) => setTpApiKey(e.target.value)} />
                <Input
                  placeholder="Business unit ID"
                  value={tpBuId}
                  onChange={(e) => setTpBuId(e.target.value)}
                />
                <Button size="sm" onClick={tpConnect} disabled={busy === "tp-connect"}>
                  Connect Trustpilot
                </Button>
              </div>
            )}
            <div className="space-y-2 rounded-lg border border-border/50 bg-background/50 p-3">
              <p className="text-sm font-medium">Send review invitation</p>
              <div className="flex flex-col sm:flex-row gap-2">
                <Input
                  placeholder="Customer email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                />
                <Input placeholder="Job ID" value={inviteJobId} onChange={(e) => setInviteJobId(e.target.value)} />
                <Button size="sm" onClick={tpInvite} disabled={busy === "tp-invite"}>
                  <Send className="h-3 w-3 mr-1" /> Invite
                </Button>
              </div>
            </div>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {tpInvitations.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-2">No invitations yet</p>
              ) : (
                tpInvitations.slice(0, 10).map((inv: any, i: number) => (
                  <div
                    key={inv.id ?? i}
                    className="flex items-center justify-between rounded-lg border border-border/50 px-3 py-2 text-sm"
                  >
                    <span>{inv.email ?? inv.customer_email ?? inv.customer_id ?? "—"}</span>
                    <Badge variant="secondary">{inv.status ?? "sent"}</Badge>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        {/* Brevo marketing */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Mail className="h-5 w-5 text-blue-400" /> Brevo Marketing
            </CardTitle>
            <StatusBadge connected={!!mktStatus?.brevo_connected} />
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2 text-sm">
              <Badge variant="secondary">Contacts synced: {mktStatus?.contacts_synced ?? 0}</Badge>
              <Badge variant="secondary">Lists: {mktStatus?.lists?.length ?? mktStatus?.lists ?? 0}</Badge>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={mktSyncContacts} disabled={busy === "mkt-sync"}>
                <RefreshCw className="h-3 w-3 mr-1" /> Sync contacts
              </Button>
              <Button size="sm" variant="outline" onClick={mktWinback} disabled={busy === "mkt-winback"}>
                Win-back preview
              </Button>
            </div>
            {winback && (
              <div className="rounded-lg border border-border/50 bg-background/50 p-3 text-sm">
                <p>
                  <span className="text-muted-foreground">Targets: </span>
                  <span className="font-semibold">{winback.target_count ?? 0}</span>
                </p>
                {winback.subject && (
                  <p>
                    <span className="text-muted-foreground">Subject: </span>
                    {winback.subject}
                  </p>
                )}
              </div>
            )}
            <div className="space-y-2 rounded-lg border border-border/50 bg-background/50 p-3">
              <p className="text-sm font-medium">New campaign</p>
              <Input placeholder="Campaign name" value={campName} onChange={(e) => setCampName(e.target.value)} />
              <Input placeholder="Subject" value={campSubject} onChange={(e) => setCampSubject(e.target.value)} />
              <Input placeholder="List ID" value={campList} onChange={(e) => setCampList(e.target.value)} />
              <Input placeholder="HTML content" value={campHtml} onChange={(e) => setCampHtml(e.target.value)} />
              <Button size="sm" onClick={mktSendCampaign} disabled={busy === "mkt-campaign"}>
                <Send className="h-3 w-3 mr-1" /> Send campaign
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Zapier / Make */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Zap className="h-5 w-5 text-orange-400" /> Zapier / Make Automation
          </CardTitle>
          <Badge variant="secondary">{subs.length} active subscriptions</Badge>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <p className="text-sm font-medium">Available triggers</p>
              {triggers.length === 0 ? (
                <p className="text-sm text-muted-foreground">No triggers found</p>
              ) : (
                triggers.map((t: any, i: number) => {
                  const name = typeof t === "string" ? t : (t.name ?? t.trigger ?? `trigger-${i}`);
                  return (
                    <div
                      key={name + i}
                      className="flex items-center justify-between rounded-lg border border-border/50 px-3 py-2 text-sm"
                    >
                      <span className="font-mono text-xs">{name}</span>
                      <Button size="sm" variant="outline" onClick={() => zapTest(name)} disabled={!!busy}>
                        Test
                      </Button>
                    </div>
                  );
                })
              )}
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium">Subscriptions</p>
              {subs.length === 0 ? (
                <p className="text-sm text-muted-foreground">No subscriptions yet</p>
              ) : (
                subs.map((s: any, i: number) => {
                  const id = s.id ?? s.subscription_id ?? String(i);
                  return (
                    <div
                      key={id}
                      className="flex items-center justify-between rounded-lg border border-border/50 px-3 py-2 text-sm"
                    >
                      <div>
                        <p className="font-medium text-xs">{s.trigger ?? s.event ?? "webhook"}</p>
                        <p className="text-xs text-muted-foreground truncate max-w-[220px]">
                          {s.target_url ?? s.url ?? ""}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => zapUnsubscribe(id)}
                        disabled={busy === `zap-del-${id}`}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  );
                })
              )}
            </div>
          </div>
          <div className="flex flex-col sm:flex-row gap-2 rounded-lg border border-border/50 bg-background/50 p-3">
            <select
              className="flex h-10 rounded-lg border border-input bg-background px-3 py-2 text-sm"
              value={subTrigger}
              onChange={(e) => setSubTrigger(e.target.value)}
            >
              <option value="">Select trigger...</option>
              {triggers.map((t: any, i: number) => {
                const name = typeof t === "string" ? t : (t.name ?? t.trigger ?? `trigger-${i}`);
                return (
                  <option key={name + i} value={name}>
                    {name}
                  </option>
                );
              })}
            </select>
            <Input
              placeholder="Target URL (https://...)"
              value={subUrl}
              onChange={(e) => setSubUrl(e.target.value)}
              className="flex-1"
            />
            <Button size="sm" onClick={zapSubscribe} disabled={busy === "zap-sub"}>
              Subscribe
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
