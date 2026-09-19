"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import {
  FileText,
  CheckCircle2,
  AlertCircle,
  Download,
  Calculator,
  Building,
} from "lucide-react";

type Tab = "subcontractors" | "payments" | "returns" | "annual";

export default function CISPage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<Tab>("subcontractors");
  const [subs, setSubs] = useState<any[]>([]);
  const [paymentsList, setPaymentsList] = useState<any[]>([]);
  const [returnData, setReturnData] = useState<any>(null);
  const [annualData, setAnnualData] = useState<any>(null);
  const [period, setPeriod] = useState(
    new Date().toISOString().slice(0, 7)
  );
  const [taxYear, setTaxYear] = useState("2025/26");
  const [showRegForm, setShowRegForm] = useState(false);
  const [showPayForm, setShowPayForm] = useState(false);
  const [regForm, setRegForm] = useState({
    company_name: "",
    utr_number: "",
    cis_number: "",
    contact_name: "",
    phone: "",
    email: "",
    address: "",
  });
  const [payForm, setPayForm] = useState({
    subcontractor_id: "",
    gross_amount: "",
    materials_deducted: "",
    cis_deduction_rate: "20",
    payment_date: new Date().toISOString().slice(0, 10),
    payment_reference: "",
  });

  useEffect(() => {
    if (!token) return;
    if (tab === "subcontractors") loadSubs();
    if (tab === "payments") loadPayments();
    if (tab === "returns") loadReturns();
    if (tab === "annual") loadAnnual();
  }, [token, tab, period, taxYear]);

  const loadSubs = async () => {
    try {
      const data: any = await api.cis.listSubs(token!);
      setSubs(data);
    } catch (e) {
      console.error(e);
    }
  };

  const loadPayments = async () => {
    try {
      const data: any = await api.cis.periodPayments(period, token!);
      setPaymentsList(data);
    } catch (e) {
      console.error(e);
    }
  };

  const loadReturns = async () => {
    try {
      const data: any = await api.cis.returns(period, token!);
      setReturnData(data);
    } catch (e) {
      console.error(e);
    }
  };

  const loadAnnual = async () => {
    try {
      const data: any = await api.cis.annualSummary(taxYear, token!);
      setAnnualData(data);
    } catch (e) {
      console.error(e);
    }
  };

  const registerSub = async () => {
    try {
      await api.cis.registerSub(
        {
          ...regForm,
          verification_status: "pending",
          deduction_rate: 20,
        },
        token!
      );
      setShowRegForm(false);
      setRegForm({
        company_name: "",
        utr_number: "",
        cis_number: "",
        contact_name: "",
        phone: "",
        email: "",
        address: "",
      });
      loadSubs();
    } catch (e) {
      console.error(e);
    }
  };

  const verifySub = async (id: string) => {
    try {
      await api.cis.verifySub(
        id,
        {
          utr: subs.find((s) => s.id === id)?.utr_number || "",
          verification_date: new Date().toISOString().slice(0, 10),
          verified_by: "Admin",
        },
        token!
      );
      loadSubs();
    } catch (e) {
      console.error(e);
    }
  };

  const createPayment = async () => {
    try {
      const gross = parseFloat(payForm.gross_amount) || 0;
      const materials = parseFloat(payForm.materials_deducted) || 0;
      const rate = parseInt(payForm.cis_deduction_rate);
      const deductionAmount = (gross - materials) * (rate / 100);
      const net = gross - materials - deductionAmount;

      await api.cis.createPayment(
        {
          subcontractor_id: payForm.subcontractor_id,
          payment_period: period,
          gross_amount: gross,
          materials_deducted: materials,
          cis_deduction_rate: rate,
          cis_deduction_amount: deductionAmount,
          net_payment: net,
          payment_date: payForm.payment_date,
          payment_reference: payForm.payment_reference,
        },
        token!
      );
      setShowPayForm(false);
      setPayForm({
        subcontractor_id: "",
        gross_amount: "",
        materials_deducted: "",
        cis_deduction_rate: "20",
        payment_date: new Date().toISOString().slice(0, 10),
        payment_reference: "",
      });
      loadPayments();
    } catch (e) {
      console.error(e);
    }
  };

  const downloadPayslip = async (paymentId: string) => {
    try {
      const data: any = await api.cis.payslip(paymentId, token!);
      if (data?.payslip) {
        const byteChars = atob(data.payslip);
        const bytes = new Uint8Array(byteChars.length);
        for (let i = 0; i < byteChars.length; i++) {
          bytes[i] = byteChars.charCodeAt(i);
        }
        const blob = new Blob([bytes], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `payslip-${paymentId}.txt`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const tabs: { key: Tab; label: string; icon: any }[] = [
    { key: "subcontractors", label: "Subcontractors", icon: Building },
    { key: "payments", label: "Payments", icon: FileText },
    { key: "returns", label: "Returns", icon: Calculator },
    { key: "annual", label: "Annual", icon: Download },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">CIS Management</h1>
        <p className="text-muted-foreground">
          Construction Industry Scheme tax management
        </p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-2 border-b pb-2">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t.key
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent"
            }`}
          >
            <t.icon className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Subcontractors tab ──────────────────────────── */}
      {tab === "subcontractors" && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-semibold">Registered Subcontractors</h2>
            <Button
              onClick={() => setShowRegForm(!showRegForm)}
              size="sm"
            >
              + Register
            </Button>
          </div>

          {showRegForm && (
            <Card>
              <CardHeader>
                <CardTitle>Register Subcontractor</CardTitle>
                <CardDescription>
                  Register a new CIS subcontractor
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    placeholder="Company Name"
                    value={regForm.company_name}
                    onChange={(e) =>
                      setRegForm({ ...regForm, company_name: e.target.value })
                    }
                  />
                  <Input
                    placeholder="UTR Number"
                    value={regForm.utr_number}
                    onChange={(e) =>
                      setRegForm({ ...regForm, utr_number: e.target.value })
                    }
                  />
                  <Input
                    placeholder="CIS Number"
                    value={regForm.cis_number}
                    onChange={(e) =>
                      setRegForm({ ...regForm, cis_number: e.target.value })
                    }
                  />
                  <Input
                    placeholder="Contact Name"
                    value={regForm.contact_name}
                    onChange={(e) =>
                      setRegForm({ ...regForm, contact_name: e.target.value })
                    }
                  />
                  <Input
                    placeholder="Phone"
                    value={regForm.phone}
                    onChange={(e) =>
                      setRegForm({ ...regForm, phone: e.target.value })
                    }
                  />
                  <Input
                    placeholder="Email"
                    type="email"
                    value={regForm.email}
                    onChange={(e) =>
                      setRegForm({ ...regForm, email: e.target.value })
                    }
                  />
                </div>
                <Input
                  placeholder="Address"
                  value={regForm.address}
                  onChange={(e) =>
                    setRegForm({ ...regForm, address: e.target.value })
                  }
                />
                <div className="flex gap-2">
                  <Button onClick={registerSub} size="sm">
                    Register
                  </Button>
                  <Button
                    onClick={() => setShowRegForm(false)}
                    variant="outline"
                    size="sm"
                  >
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {subs.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                No subcontractors registered yet.
              </CardContent>
            </Card>
          ) : (
            subs.map((sub) => (
              <Card key={sub.id} className="hover:border-primary/30 transition-all">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-4">
                      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-500/10 shrink-0">
                        <Building className="h-5 w-5 text-blue-400" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold">{sub.company_name}</h3>
                          <Badge
                            className={
                              sub.verification_status === "verified"
                                ? "bg-green-500/20 text-green-400"
                                : sub.verification_status === "pending"
                                  ? "bg-yellow-500/20 text-yellow-400"
                                  : "bg-red-500/20 text-red-400"
                            }
                          >
                            {sub.verification_status === "verified" ? (
                              <CheckCircle2 className="h-3 w-3 mr-1" />
                            ) : (
                              <AlertCircle className="h-3 w-3 mr-1" />
                            )}
                            {sub.verification_status}
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                          UTR: {sub.utr_number} | CIS: {sub.cis_number}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {sub.contact_name} | {sub.phone} | {sub.email}
                        </p>
                        <p className="text-xs text-muted-foreground mt-1">
                          Deduction Rate: {sub.deduction_rate}%
                        </p>
                      </div>
                    </div>
                    {sub.verification_status !== "verified" && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => verifySub(sub.id)}
                      >
                        <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
                        Verify
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}

      {/* ── Payments tab ────────────────────────────────── */}
      {tab === "payments" && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-semibold">Monthly Payments</h2>
              <Input
                type="month"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                className="w-40"
              />
            </div>
            <Button onClick={() => setShowPayForm(!showPayForm)} size="sm">
              + Record Payment
            </Button>
          </div>

          {showPayForm && (
            <Card>
              <CardHeader>
                <CardTitle>Record CIS Payment</CardTitle>
                <CardDescription>
                  Record a monthly payment to a subcontractor
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <select
                    className="flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                    value={payForm.subcontractor_id}
                    onChange={(e) =>
                      setPayForm({
                        ...payForm,
                        subcontractor_id: e.target.value,
                      })
                    }
                  >
                    <option value="">Select Subcontractor</option>
                    {subs.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.company_name}
                      </option>
                    ))}
                  </select>
                  <Input
                    placeholder="Gross Amount"
                    type="number"
                    step="0.01"
                    value={payForm.gross_amount}
                    onChange={(e) =>
                      setPayForm({ ...payForm, gross_amount: e.target.value })
                    }
                  />
                  <Input
                    placeholder="Materials Deducted"
                    type="number"
                    step="0.01"
                    value={payForm.materials_deducted}
                    onChange={(e) =>
                      setPayForm({
                        ...payForm,
                        materials_deducted: e.target.value,
                      })
                    }
                  />
                  <select
                    className="flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                    value={payForm.cis_deduction_rate}
                    onChange={(e) =>
                      setPayForm({
                        ...payForm,
                        cis_deduction_rate: e.target.value,
                      })
                    }
                  >
                    <option value="0">0% Deduction</option>
                    <option value="20">20% Deduction</option>
                    <option value="30">30% Deduction</option>
                  </select>
                  <Input
                    type="date"
                    value={payForm.payment_date}
                    onChange={(e) =>
                      setPayForm({ ...payForm, payment_date: e.target.value })
                    }
                  />
                  <Input
                    placeholder="Payment Reference"
                    value={payForm.payment_reference}
                    onChange={(e) =>
                      setPayForm({
                        ...payForm,
                        payment_reference: e.target.value,
                      })
                    }
                  />
                </div>
                <div className="flex gap-2">
                  <Button onClick={createPayment} size="sm">
                    Record Payment
                  </Button>
                  <Button
                    onClick={() => setShowPayForm(false)}
                    variant="outline"
                    size="sm"
                  >
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {paymentsList.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                No payments recorded for {period}.
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="p-3">Subcontractor</th>
                      <th className="p-3 text-right">Gross</th>
                      <th className="p-3 text-right">Materials</th>
                      <th className="p-3 text-right">Rate</th>
                      <th className="p-3 text-right">Deduction</th>
                      <th className="p-3 text-right">Net</th>
                      <th className="p-3">Reference</th>
                      <th className="p-3 text-right">Payslip</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paymentsList.map((p) => (
                      <tr key={p.id} className="border-b hover:bg-accent/50">
                        <td className="p-3 font-medium">
                          {p.subcontractor_name}
                        </td>
                        <td className="p-3 text-right">
                          {formatCurrency(p.gross_amount)}
                        </td>
                        <td className="p-3 text-right">
                          {formatCurrency(p.materials_deducted)}
                        </td>
                        <td className="p-3 text-right">
                          {p.cis_deduction_rate}%
                        </td>
                        <td className="p-3 text-right text-red-400">
                          -{formatCurrency(p.cis_deduction_amount)}
                        </td>
                        <td className="p-3 text-right font-semibold">
                          {formatCurrency(p.net_payment)}
                        </td>
                        <td className="p-3 text-muted-foreground text-xs">
                          {p.payment_reference}
                        </td>
                        <td className="p-3 text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => downloadPayslip(p.id)}
                          >
                            <Download className="h-4 w-4" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ── Returns tab ─────────────────────────────────── */}
      {tab === "returns" && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-semibold">CIS Return Summary</h2>
            <Input
              type="month"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="w-40"
            />
            <Button size="sm" variant="outline">
              <Download className="h-4 w-4 mr-1" />
              Export
            </Button>
          </div>

          {!returnData ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                Select a period to view the CIS return.
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Total Gross</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold gradient-text">
                      {formatCurrency(returnData.total_gross)}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Total Materials</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">
                      {formatCurrency(returnData.total_materials)}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Total Deductions</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-red-400">
                      {formatCurrency(returnData.total_deductions)}
                    </div>
                  </CardContent>
                </Card>
              </div>

              {returnData.subcontractors.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>Subcontractor Breakdown</CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-muted-foreground">
                          <th className="p-3">Name</th>
                          <th className="p-3">UTR</th>
                          <th className="p-3 text-right">Gross</th>
                          <th className="p-3 text-right">Deductions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {returnData.subcontractors.map(
                          (s: any, i: number) => (
                            <tr key={i} className="border-b hover:bg-accent/50">
                              <td className="p-3 font-medium">{s.name}</td>
                              <td className="p-3 text-muted-foreground">
                                {s.utr}
                              </td>
                              <td className="p-3 text-right">
                                {formatCurrency(s.gross)}
                              </td>
                              <td className="p-3 text-right text-red-400">
                                {formatCurrency(s.deductions)}
                              </td>
                            </tr>
                          )
                        )}
                      </tbody>
                    </table>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Annual tab ──────────────────────────────────── */}
      {tab === "annual" && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-semibold">Annual CIS Summary</h2>
            <Input
              placeholder="Tax Year (e.g. 2025/26)"
              value={taxYear}
              onChange={(e) => setTaxYear(e.target.value)}
              className="w-40"
            />
            <Button size="sm" variant="outline">
              <Download className="h-4 w-4 mr-1" />
              Download Summary
            </Button>
          </div>

          {!annualData ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                Enter a tax year to view the annual summary.
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>
                      Total Gross ({annualData.tax_year})
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold gradient-text">
                      {formatCurrency(annualData.total_gross)}
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>
                      Total Deductions ({annualData.tax_year})
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold text-red-400">
                      {formatCurrency(annualData.total_deductions)}
                    </div>
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader>
                  <CardTitle>Monthly Breakdown</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="p-3">Month</th>
                        <th className="p-3 text-right">Payments</th>
                        <th className="p-3 text-right">Gross</th>
                        <th className="p-3 text-right">Deductions</th>
                        <th className="p-3 text-right">Net</th>
                      </tr>
                    </thead>
                    <tbody>
                      {annualData.monthly_breakdown.map(
                        (m: any, i: number) => (
                          <tr key={i} className="border-b hover:bg-accent/50">
                            <td className="p-3 font-medium">{m.month}</td>
                            <td className="p-3 text-right text-muted-foreground">
                              {m.payment_count}
                            </td>
                            <td className="p-3 text-right">
                              {formatCurrency(m.gross)}
                            </td>
                            <td className="p-3 text-right text-red-400">
                              {formatCurrency(m.deductions)}
                            </td>
                            <td className="p-3 text-right font-semibold">
                              {formatCurrency(m.net)}
                            </td>
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      )}
    </div>
  );
}
