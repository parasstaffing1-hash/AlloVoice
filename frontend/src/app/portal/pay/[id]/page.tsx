"use client";

import { Suspense, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import CardPaymentModal from "@/components/card-payment-modal";
import {
  Loader2,
  CheckCircle2,
  CreditCard,
  Receipt,
  Link2Off,
} from "lucide-react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function formatGBP(amount: number): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
  }).format(amount ?? 0);
}

function PayContent() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const invoiceId = params?.id as string;

  const [portalToken, setPortalToken] = useState<string | null>(null);
  const [invoice, setInvoice] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPay, setShowPay] = useState(false);
  const [paid, setPaid] = useState(false);
  const [accessCode, setAccessCode] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);

  // Accept ?token= query param (what email/SMS pay links point to)
  useEffect(() => {
    const t = searchParams.get("token");
    if (t) setPortalToken(t);
    else setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Load invoice once we have a token
  useEffect(() => {
    if (!portalToken || !invoiceId) return;
    setLoading(true);
    setError(null);

    // Preferred: portal invoice list (portal token = access-code JWT), find by id
    api.portal
      .invoices(portalToken)
      .then((r: any) => {
        const list = Array.isArray(r) ? r : r?.invoices || r?.data || [];
        const found = list.find((x: any) => x.id === invoiceId);
        if (found) {
          setInvoice(found);
          setLoading(false);
          return;
        }
        // Fallback: direct invoice fetch with the same token
        return api.invoices
          .get(invoiceId, portalToken)
          .then((r2: any) => {
            setInvoice(r2);
            setLoading(false);
          })
          .catch(() =>
            fetch(`${API_BASE}/api/invoices/${encodeURIComponent(invoiceId)}`, {
              headers: { Authorization: `Bearer ${portalToken}` },
            })
              .then((res: any) => {
                if (!res.ok) throw new Error("not found");
                return res.json();
              })
              .then((r3: any) => {
                setInvoice(r3);
                setLoading(false);
              })
              .catch(() => {
                setError("link invalid");
                setLoading(false);
              })
          );
      })
      .catch(() =>
        // portal.invoices failed → try staff invoice endpoint + raw fetch
        api.invoices
          .get(invoiceId, portalToken)
          .then((r: any) => {
            setInvoice(r);
            setLoading(false);
          })
          .catch(() => {
            setError("link invalid");
            setLoading(false);
          })
      );
  }, [portalToken, invoiceId]);

  const handleAccessCode = () => {
    setCodeError(null);
    if (!accessCode.trim()) {
      setCodeError("Enter the access code from your email.");
      return;
    }
    api.portal
      .login(accessCode.trim())
      .then((r: any) => {
        if (!r?.token) throw new Error("invalid");
        setPortalToken(r.token);
        // Update URL so refresh keeps working
        const url = new URL(window.location.href);
        url.searchParams.set("token", r.token);
        window.history.replaceState(null, "", url.toString());
      })
      .catch(() => setCodeError("That access code was not recognised."));
  };

  if (paid && invoice) {
    return (
      <div className="mx-auto flex min-h-[60vh] w-full max-w-md items-center justify-center p-4">
        <Card className="w-full border-zinc-800 bg-zinc-950 text-center">
          <CardContent className="py-10">
            <CheckCircle2 className="mx-auto h-14 w-14 text-green-400" />
            <h1 className="mt-4 text-2xl font-bold text-zinc-100">
              Payment successful
            </h1>
            <p className="mt-2 text-sm text-zinc-400">
              {formatGBP(invoice.total)} paid for invoice{" "}
              <span className="font-medium text-zinc-200">
                {invoice.invoice_number}
              </span>
            </p>
            <p className="mt-1 text-xs text-zinc-500">
              Reference: {invoice.id?.slice(0, 8)}… · Keep this for your
              records.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // No token at all → access-code gate (public link without ?token=)
  if (!portalToken && !loading) {
    return (
      <div className="mx-auto flex min-h-[60vh] w-full max-w-md items-center justify-center p-4">
        <Card className="w-full border-zinc-800 bg-zinc-950">
          <CardHeader className="text-center">
            <Receipt className="mx-auto mb-2 h-10 w-10 text-primary" />
            <CardTitle className="text-zinc-100">Pay your invoice</CardTitle>
            <p className="text-sm text-zinc-400">
              This payment link needs an access code. Enter the code from your
              email or SMS.
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            <Input
              placeholder="Access code"
              value={accessCode}
              onChange={(e) => setAccessCode(e.target.value)}
              className="border-zinc-700 bg-zinc-900 text-zinc-100"
            />
            {codeError && (
              <p className="text-sm text-red-400">{codeError}</p>
            )}
            <Button className="w-full" onClick={handleAccessCode}>
              Continue to payment
            </Button>
            <p className="flex items-center justify-center gap-1 text-xs text-zinc-500">
              <Link2Off className="h-3 w-3" /> link invalid without a valid code
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center gap-2 text-zinc-400">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-sm">Loading invoice…</span>
      </div>
    );
  }

  if (error || !invoice) {
    return (
      <div className="mx-auto flex min-h-[60vh] w-full max-w-md items-center justify-center p-4">
        <Card className="w-full border-zinc-800 bg-zinc-950 text-center">
          <CardContent className="py-10">
            <Link2Off className="mx-auto h-10 w-10 text-zinc-500" />
            <p className="mt-3 font-medium text-zinc-200">
              This payment link is invalid or has expired.
            </p>
            <p className="mt-1 text-sm text-zinc-500">
              Please contact the business for a fresh pay link.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const alreadyPaid =
    invoice.payment_status === "paid" || invoice.status === "paid";

  return (
    <div className="mx-auto w-full max-w-md p-4">
      <Card className="border-zinc-800 bg-zinc-950">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-green-500/10">
              <Receipt className="h-5 w-5 text-green-400" />
            </div>
            <div>
              <CardTitle className="text-zinc-100">
                {invoice.invoice_number}
              </CardTitle>
              <p className="text-sm text-zinc-400">
                Due:{" "}
                {invoice.due_date
                  ? new Date(invoice.due_date).toLocaleDateString("en-GB")
                  : "TBC"}
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-center">
            <p className="text-sm text-zinc-400">Amount due</p>
            <p className="text-4xl font-bold text-zinc-50">
              {formatGBP(invoice.total)}
            </p>
            {invoice.amount_paid > 0 && (
              <p className="mt-1 text-xs text-green-400">
                Already paid: {formatGBP(invoice.amount_paid)}
              </p>
            )}
          </div>

          {alreadyPaid ? (
            <div className="rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-3 text-center text-sm text-green-200">
              This invoice is already paid. Thank you.
            </div>
          ) : (
            <Button
              className="w-full gap-2"
              onClick={() => setShowPay(true)}
            >
              <CreditCard className="h-4 w-4" />
              Pay {formatGBP(invoice.total)} by card
            </Button>
          )}

          {showPay && !alreadyPaid && (
            <CardPaymentModal
              invoiceId={invoice.id}
              amount={invoice.total}
              token={portalToken ?? undefined}
              onClose={() => setShowPay(false)}
              onSuccess={() => {
                setShowPay(false);
                setPaid(true);
              }}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function PortalPayPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[60vh] items-center justify-center gap-2 text-zinc-400">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-sm">Loading…</span>
        </div>
      }
    >
      <PayContent />
    </Suspense>
  );
}
