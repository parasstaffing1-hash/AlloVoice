"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import CardPaymentModal from "@/components/card-payment-modal";
import {
  Globe, Shield, Calendar, FileText, Camera, Star,
  MessageSquare, CheckCircle2, CreditCard,
} from "lucide-react";

export default function PortalPage() {
  const [token, setToken] = useState("");
  const [loginCode, setLoginCode] = useState("");
  const [authenticated, setAuthenticated] = useState(false);
  const [portalData, setPortalData] = useState<any>(null);
  const [cardInvoice, setCardInvoice] = useState<any | null>(null);

  const reloadPortal = () => {
    if (!token) return;
    api.portal
      .dashboard(token)
      .then((r: any) => setPortalData(r))
      .catch(() => {});
  };

  const handleLogin = async () => {
    try {
      const result: any = await api.portal.login(loginCode);
      setToken(result.token);
      setAuthenticated(true);
      const data: any = await api.portal.dashboard(result.token);
      setPortalData(data);
    } catch {
      setAuthenticated(false);
    }
  };

  if (!authenticated) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <Globe className="h-12 w-12 mx-auto text-primary mb-2" />
            <CardTitle>Customer Portal</CardTitle>
            <p className="text-sm text-muted-foreground">
              Enter the access code from your email to view your account
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input
              placeholder="Enter access code"
              value={loginCode}
              onChange={(e) => setLoginCode(e.target.value)}
            />
            <Button className="w-full" onClick={handleLogin}>Sign In</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const stats = portalData
    ? [
        { label: "Open Jobs", value: portalData.open_jobs?.length || 0, icon: FileText, color: "text-blue-400" },
        { label: "Completed Jobs", value: portalData.completed_jobs?.length || 0, icon: CheckCircle2, color: "text-green-400" },
        { label: "Unpaid Invoices", value: portalData.unpaid_invoices?.length || 0, icon: Globe, color: "text-yellow-400" },
        { label: "Upcoming Jobs", value: portalData.upcoming_jobs?.length || 0, icon: Calendar, color: "text-purple-400" },
      ]
    : [];

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">My Account</h1>

      <div className="grid gap-4 md:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardContent className="py-4 flex items-center gap-3">
              <s.icon className={`h-8 w-8 ${s.color}`} />
              <div>
                <p className="text-2xl font-bold">{s.value}</p>
                <p className="text-xs text-muted-foreground">{s.label}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Upcoming Jobs</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {portalData?.upcoming_jobs?.length > 0 ? portalData.upcoming_jobs.map((j: any) => (
              <div key={j.id} className="flex items-center justify-between text-sm py-2 border-b last:border-0">
                <div>
                  <p className="font-medium">{j.title}</p>
                  <p className="text-muted-foreground">{j.scheduled_at ? new Date(j.scheduled_at).toLocaleDateString("en-GB") : "TBC"}</p>
                </div>
                <Badge>{j.status}</Badge>
              </div>
            )) : (
              <p className="text-sm text-muted-foreground">No upcoming jobs</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Unpaid Invoices</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {portalData?.unpaid_invoices?.length > 0 ? portalData.unpaid_invoices.map((i: any) => (
              <div key={i.id} className="flex items-center justify-between gap-3 text-sm py-2 border-b last:border-0">
                <div>
                  <p className="font-medium">{i.invoice_number}</p>
                  <p className="text-muted-foreground">Due: {i.due_date ? new Date(i.due_date).toLocaleDateString("en-GB") : "TBC"}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className="font-medium">£{i.total?.toFixed(2)}</p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-1 gap-1"
                    onClick={() => setCardInvoice(i)}
                  >
                    <CreditCard className="h-3.5 w-3.5" />
                    Pay by card
                  </Button>
                </div>
              </div>
            )) : (
              <p className="text-sm text-muted-foreground">No outstanding invoices</p>
            )}
          </CardContent>
        </Card>
      </div>

      {cardInvoice && (
        <CardPaymentModal
          invoiceId={cardInvoice.id}
          amount={cardInvoice.total}
          token={token || undefined}
          onClose={() => setCardInvoice(null)}
          onSuccess={() => {
            reloadPortal();
            setCardInvoice(null);
          }}
        />
      )}
    </div>
  );
}
