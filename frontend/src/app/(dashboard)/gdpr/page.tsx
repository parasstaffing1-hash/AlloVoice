"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  Shield,
  Download,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Users,
  FileText,
  Receipt,
} from "lucide-react";

type DataMap = {
  customers: { total: number };
  jobs: { total: number };
  invoices: { total: number };
};

type ConsentState = {
  marketing: boolean;
  analytics: boolean;
  third_party: boolean;
};

type CustomerWithConsent = {
  id: string;
  full_name: string;
  email: string;
  consent: ConsentState;
};

type ErasureRequest = {
  id: string;
  customer_id: string;
  customer_name: string;
  reason: string;
  status: "pending" | "approved" | "completed";
  created_at: string;
};

export default function GdprPage() {
  const { token } = useAuth();
  const [activeSection, setActiveSection] = useState<"map" | "consent" | "erasure" | "export">("map");

  // Data Map
  const [dataMap, setDataMap] = useState<DataMap | null>(null);

  // Consent
  const [customers, setCustomers] = useState<CustomerWithConsent[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<string>("");
  const [consentSearch, setConsentSearch] = useState("");

  // Erasure
  const [erasureRequests, setErasureRequests] = useState<ErasureRequest[]>([]);
  const [showErasureForm, setShowErasureForm] = useState(false);
  const [erasureForm, setErasureForm] = useState({ customer_id: "", reason: "" });

  // Export
  const [exportCustomerId, setExportCustomerId] = useState("");
  const [exporting, setExporting] = useState(false);

  // Feedback
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");

  const formatDate = (date: string) =>
    new Date(date).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });

  const flash = (msg: string, isError = false) => {
    if (isError) setError(msg);
    else setSuccess(msg);
    setTimeout(() => {
      setSuccess("");
      setError("");
    }, 3000);
  };

  // ── Data Map ──
  // Backend data-map returns { note, data_categories } (no totals), so build the
  // totals cards from the real list endpoints.
  const loadDataMap = async () => {
    if (!token) return;
    try {
      const [customerList, jobList, invoiceList]: any[] = await Promise.all([
        api.customers.list(token).catch(() => []),
        api.jobs.list(token).catch(() => []),
        api.invoices.list(token).catch(() => []),
      ]);
      await api.gdpr.dataMap(token).catch(() => null);
      setDataMap({
        customers: { total: Array.isArray(customerList) ? customerList.length : 0 },
        jobs: { total: Array.isArray(jobList) ? jobList.length : 0 },
        invoices: { total: Array.isArray(invoiceList) ? invoiceList.length : 0 },
      });
    } catch (e: any) {
      flash(e.message || "Failed to load data map", true);
    }
  };

  // ── Consent ──
  // Backend consent-status is per current (logged-in) user, not per customer —
  // fetch once and reflect it for every row (customer marketing_consent as fallback).
  const loadCustomersWithConsent = async () => {
    if (!token) return;
    try {
      const list: any = await api.customers.list(token);
      const rows = Array.isArray(list) ? list : [];
      let granted: Record<string, boolean> = {};
      try {
        const res: any = await api.gdpr.consentStatus(token);
        for (const c of res?.consents || []) {
          if (c?.type) granted[c.type] = !!c.granted;
        }
      } catch {
        granted = {};
      }
      setCustomers(
        rows.map((c: any) => ({
          id: c.id,
          full_name: c.full_name,
          email: c.email,
          consent: {
            marketing: granted.marketing ?? !!c.marketing_consent,
            analytics: granted.analytics ?? false,
            third_party: granted.third_party ?? false,
          },
        }))
      );
    } catch (e: any) {
      flash(e.message || "Failed to load customers", true);
    }
  };

  const updateConsent = async (customerId: string, consentType: string, consentGiven: boolean) => {
    if (!token) return;
    try {
      // Backend records consent for the current user only (no customer id).
      await api.gdpr.consent(
        { consent_type: consentType, granted: consentGiven },
        token
      );
      setCustomers((prev) =>
        prev.map((c) =>
          c.id === customerId
            ? { ...c, consent: { ...c.consent, [consentType]: consentGiven } }
            : c
        )
      );
      flash("Consent updated");
    } catch (e: any) {
      flash(e.message || "Failed to update consent", true);
    }
  };

  // ── Erasure ──
  const loadErasureRequests = async () => {
    if (!token) return;
    try {
      const data: any = await api.audit.logs(token, 50);
      const requests = (data || [])
        .filter((log: any) => log.action === "erasure_request")
        .map((log: any) => ({
          id: log.id || log.created_at,
          customer_id: log.metadata?.customer_id || "",
          customer_name: log.metadata?.customer_name || "Unknown",
          reason: log.metadata?.reason || "",
          status: log.metadata?.status || "pending",
          created_at: log.created_at,
        }));
      setErasureRequests(requests);
    } catch {
      setErasureRequests([]);
    }
  };

  const submitErasure = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    try {
      // Backend takes only customer_id (query); the reason field has no backend counterpart.
      await api.gdpr.requestErasure({ customer_id: erasureForm.customer_id }, token);
      setErasureForm({ customer_id: "", reason: "" });
      setShowErasureForm(false);
      flash("Erasure request submitted");
      loadErasureRequests();
    } catch (e: any) {
      flash(e.message || "Failed to submit erasure request", true);
    }
  };

  // ── Export ──
  const handleExport = async () => {
    if (!token || !exportCustomerId) return;
    setExporting(true);
    try {
      const data: any = await api.gdpr.exportData(exportCustomerId, token);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `gdpr-export-${exportCustomerId}-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      flash("Data exported successfully");
    } catch (e: any) {
      flash(e.message || "Failed to export data", true);
    } finally {
      setExporting(false);
    }
  };

  // ── Init ──
  useEffect(() => {
    if (!token) return;
    if (activeSection === "map") loadDataMap();
    if (activeSection === "consent") loadCustomersWithConsent();
    if (activeSection === "erasure") loadErasureRequests();
  }, [token, activeSection]);

  const sections = [
    { id: "map" as const, label: "Data Map", icon: Shield },
    { id: "consent" as const, label: "Consent", icon: Users },
    { id: "erasure" as const, label: "Erasure Requests", icon: Trash2 },
    { id: "export" as const, label: "Data Export", icon: Download },
  ];

  const filteredCustomers = customers.filter(
    (c) =>
      c.full_name.toLowerCase().includes(consentSearch.toLowerCase()) ||
      c.email?.toLowerCase().includes(consentSearch.toLowerCase())
  );

  const erasureStatusVariant = (status: string) => {
    if (status === "completed") return "default";
    if (status === "approved") return "secondary";
    return "outline";
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Shield className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">GDPR Compliance</h1>
          <p className="text-muted-foreground">Manage data protection and privacy in line with UK GDPR</p>
        </div>
      </div>

      {(success || error) && (
        <div
          className={`flex items-center gap-2 rounded-lg px-4 py-3 text-sm ${
            error
              ? "bg-destructive/10 text-destructive border border-destructive/20"
              : "bg-green-500/10 text-green-600 border border-green-500/20"
          }`}
        >
          {error ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
          {error || success}
        </div>
      )}

      <div className="flex gap-2 overflow-x-auto pb-2">
        {sections.map((s) => (
          <Button
            key={s.id}
            variant={activeSection === s.id ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveSection(s.id)}
            className="gap-2 shrink-0"
          >
            <s.icon className="h-4 w-4" />
            {s.label}
          </Button>
        ))}
      </div>

      {/* ─── Data Map ─── */}
      {activeSection === "map" && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Personal Data Held</CardTitle>
              <CardDescription>
                Overview of personal data stored across the platform. UK GDPR requires lawful basis for each category.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {dataMap ? (
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="flex items-center gap-4 rounded-lg border p-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-500/10">
                      <Users className="h-6 w-6 text-blue-500" />
                    </div>
                    <div>
                      <p className="text-2xl font-bold">{dataMap.customers.total}</p>
                      <p className="text-sm text-muted-foreground">Customers</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 rounded-lg border p-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-orange-500/10">
                      <FileText className="h-6 w-6 text-orange-500" />
                    </div>
                    <div>
                      <p className="text-2xl font-bold">{dataMap.jobs.total}</p>
                      <p className="text-sm text-muted-foreground">Jobs</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 rounded-lg border p-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-500/10">
                      <Receipt className="h-6 w-6 text-green-500" />
                    </div>
                    <div>
                      <p className="text-2xl font-bold">{dataMap.invoices.total}</p>
                      <p className="text-sm text-muted-foreground">Invoices</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center py-8 text-muted-foreground">Loading data map...</div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Data Categories</CardTitle>
              <CardDescription>
                Personal data processed under UK GDPR. Lawful basis must be documented for each.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {[
                  { category: "Contact Details", items: "Name, email, phone, address", basis: "Contract / Legitimate interest" },
                  { category: "Job History", items: "Service addresses, job descriptions, photos", basis: "Contract performance" },
                  { category: "Financial Data", items: "Invoices, payment records, bank details", basis: "Contract / Legal obligation" },
                  { category: "Marketing Preferences", items: "Email/SMS consent, campaign responses", basis: "Consent" },
                  { category: "Technical Data", items: "IP addresses, browser type, usage analytics", basis: "Legitimate interest" },
                ].map((row) => (
                  <div key={row.category} className="flex flex-col gap-1 rounded-lg border p-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <p className="font-medium">{row.category}</p>
                      <p className="text-xs text-muted-foreground">{row.items}</p>
                    </div>
                    <Badge variant="outline" className="shrink-0 mt-1 md:mt-0 w-fit">
                      {row.basis}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ─── Consent Management ─── */}
      {activeSection === "consent" && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Consent Management</CardTitle>
              <CardDescription>
                Manage marketing, analytics, and third-party data sharing consent per customer.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Input
                placeholder="Search customers by name or email..."
                value={consentSearch}
                onChange={(e) => setConsentSearch(e.target.value)}
                className="max-w-md"
              />

              {filteredCustomers.length === 0 ? (
                <div className="py-8 text-center text-muted-foreground">No customers found.</div>
              ) : (
                <div className="space-y-3">
                  {filteredCustomers.map((customer) => (
                    <div key={customer.id} className="rounded-lg border p-4">
                      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div>
                          <p className="font-medium">{customer.full_name}</p>
                          <p className="text-xs text-muted-foreground">{customer.email}</p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {(["marketing", "analytics", "third_party"] as const).map((type) => (
                            <Button
                              key={type}
                              variant={customer.consent[type] ? "default" : "outline"}
                              size="sm"
                              onClick={() => updateConsent(customer.id, type, !customer.consent[type])}
                              className="gap-1.5 text-xs"
                            >
                              {customer.consent[type] ? (
                                <CheckCircle2 className="h-3.5 w-3.5" />
                              ) : (
                                <AlertCircle className="h-3.5 w-3.5" />
                              )}
                              {type === "third_party" ? "Third-party" : type.charAt(0).toUpperCase() + type.slice(1)}
                            </Button>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ─── Erasure Requests ─── */}
      {activeSection === "erasure" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold">Erasure Requests</h2>
              <p className="text-sm text-muted-foreground">Right to be forgotten requests under Article 17</p>
            </div>
            <Button
              className="gap-2"
              onClick={() => setShowErasureForm(!showErasureForm)}
            >
              <Trash2 className="h-4 w-4" />
              New Request
            </Button>
          </div>

          {showErasureForm && (
            <Card>
              <CardContent className="p-6">
                <form onSubmit={submitErasure} className="space-y-4">
                  <div>
                    <label className="text-sm font-medium">Customer ID</label>
                    <Input
                      placeholder="Enter customer ID"
                      value={erasureForm.customer_id}
                      onChange={(e) => setErasureForm({ ...erasureForm, customer_id: e.target.value })}
                      required
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Reason for Erasure</label>
                    <Input
                      placeholder="e.g. Customer requested deletion of all personal data"
                      value={erasureForm.reason}
                      onChange={(e) => setErasureForm({ ...erasureForm, reason: e.target.value })}
                      required
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button type="submit">Submit Request</Button>
                    <Button type="button" variant="outline" onClick={() => setShowErasureForm(false)}>
                      Cancel
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent className="p-0">
              {erasureRequests.length === 0 ? (
                <div className="py-12 text-center text-muted-foreground">
                  No erasure requests found.
                </div>
              ) : (
                <div className="divide-y">
                  {erasureRequests.map((req) => (
                    <div key={req.id} className="flex flex-col gap-2 p-4 md:flex-row md:items-center md:justify-between">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <p className="font-medium">{req.customer_name || req.customer_id}</p>
                          <Badge variant={erasureStatusVariant(req.status)}>
                            {req.status}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">{req.reason}</p>
                        <p className="text-xs text-muted-foreground">
                          Submitted {formatDate(req.created_at)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* ─── Data Export ─── */}
      {activeSection === "export" && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Data Subject Access Request</CardTitle>
              <CardDescription>
                Export all personal data held for a customer as required under UK GDPR Article 15.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-end">
                <div className="flex-1">
                  <label className="text-sm font-medium">Customer ID</label>
                  <Input
                    placeholder="Enter customer ID to export"
                    value={exportCustomerId}
                    onChange={(e) => setExportCustomerId(e.target.value)}
                  />
                </div>
                <Button
                  onClick={handleExport}
                  disabled={!exportCustomerId || exporting}
                  className="gap-2"
                >
                  <Download className="h-4 w-4" />
                  {exporting ? "Exporting..." : "Export as JSON"}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                The export includes all personal data: contact details, job history, invoices, and consent records.
                This must be provided within one calendar month of the request.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Export Guidelines</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 text-sm text-muted-foreground">
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-green-500" />
                  <p>Must respond to subject access requests within <strong className="text-foreground">one calendar month</strong>.</p>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-green-500" />
                  <p>Data is exported in <strong className="text-foreground">JSON format</strong> for machine readability.</p>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-green-500" />
                  <p>Include all categories: contact info, jobs, invoices, and consent records.</p>
                </div>
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-green-500" />
                  <p>Keep a log of all data exports for accountability purposes.</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
