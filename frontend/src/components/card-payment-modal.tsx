"use client";

import { useEffect, useState } from "react";
import { loadStripe } from "@stripe/stripe-js";
import {
  Elements,
  CardElement,
  useStripe,
  useElements,
} from "@stripe/react-stripe-js";
import { X, CheckCircle2, Loader2, CreditCard } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/store";

export interface CardPaymentModalProps {
  invoiceId: string;
  amount: number;
  onSuccess: () => void;
  onClose: () => void;
  /** Optional auth token. Falls back to useAuth() token. Public pay-links pass none. */
  token?: string;
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatGBP(amount: number): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
  }).format(amount);
}

function CardForm({
  clientSecret,
  amount,
  onSuccess,
}: {
  clientSecret: string;
  amount: number;
  onSuccess: () => void;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!stripe || !elements) {
      setError("Stripe is still loading. Please wait a moment.");
      return;
    }
    const card = elements.getElement(CardElement);
    if (!card) {
      setError("Card field not ready. Please try again.");
      return;
    }
    setPaying(true);
    try {
      const result: any = await stripe.confirmCardPayment(clientSecret, {
        payment_method: { card },
      });
      if (result?.error) {
        setError(result.error.message || "Card payment failed.");
      } else if (result?.paymentIntent?.status === "succeeded") {
        onSuccess();
      } else {
        setError(
          `Payment status: ${result?.paymentIntent?.status || "unknown"}. Please check with your bank.`
        );
      }
    } catch (err: any) {
      setError(err?.message || "Card payment failed.");
    } finally {
      setPaying(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-3">
        <CardElement
          options={{
            style: {
              base: {
                color: "#fff",
                backgroundColor: "transparent",
                fontSize: "16px",
                fontFamily: "inherit",
                "::placeholder": { color: "#71717a" },
              },
              invalid: { color: "#f87171" },
            },
          }}
        />
      </div>
      {error && (
        <p className="text-sm text-red-400" role="alert">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={paying || !stripe}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-opacity disabled:opacity-50"
      >
        {paying ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Processing…
          </>
        ) : (
          <>
            <CreditCard className="h-4 w-4" />
            Pay {formatGBP(amount)}
          </>
        )}
      </button>
      <p className="text-center text-xs text-zinc-500">
        3D Secure is handled automatically by Stripe.
      </p>
    </form>
  );
}

export default function CardPaymentModal({
  invoiceId,
  amount,
  onSuccess,
  onClose,
  token: tokenProp,
}: CardPaymentModalProps) {
  const { token: authToken } = useAuth();
  const authHeaderToken = tokenProp ?? authToken ?? null;

  const [loading, setLoading] = useState(true);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [publishableKey, setPublishableKey] = useState<string | null>(null);
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [succeeded, setSucceeded] = useState(false);
  const [stripePromise, setStripePromise] = useState<Promise<any> | null>(
    null
  );

  useEffect(() => {
    let cancelled = false;

    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (authHeaderToken) {
      headers["Authorization"] = `Bearer ${authHeaderToken}`;
    }

    // NOTE (api.ts inspection): api.payments has createIntent/confirm/gocardless/list/status
    // but NO getConfig/config method, and createIntent POSTs to /api/payments/create-intent
    // with JSON body — NOT the spec'd POST /api/payments/create-payment-intent?invoice_id=UUID.
    // So we call the spec'd endpoints directly via fetch (defensive), with api.payments as fallback.
    fetch(`${API_BASE}/api/payments/config`, { headers })
      .then((r: any) => {
        if (!r.ok) throw new Error(`config HTTP ${r.status}`);
        return r.json();
      })
      .then((cfg: any) => {
        if (cancelled) return;
        const isConfigured = cfg?.configured !== false && !!cfg?.publishable_key;
        setConfigured(isConfigured);
        if (!isConfigured) {
          setLoading(false);
          return;
        }
        setPublishableKey(cfg.publishable_key);
        setStripePromise(loadStripe(cfg.publishable_key));

        // Fetch client secret for this invoice (spec endpoint first)
        return fetch(
          `${API_BASE}/api/payments/create-payment-intent?invoice_id=${encodeURIComponent(invoiceId)}`,
          { method: "POST", headers }
        )
          .then((r: any) => {
            if (!r.ok) throw new Error(`intent HTTP ${r.status}`);
            return r.json();
          })
          .then((d: any) => {
            if (cancelled) return;
            if (!d?.client_secret) throw new Error("No client_secret returned");
            setClientSecret(d.client_secret);
            setLoading(false);
          })
          .catch(() => {
            // Fallback: legacy api.payments.createIntent shape (POST /api/payments/create-intent {invoice_id})
            if (!authHeaderToken) throw new Error("intent failed");
            return (api.payments.createIntent as any)(invoiceId, authHeaderToken)
              .then((d: any) => {
                if (cancelled) return;
                const secret = d?.client_secret || d?.clientSecret;
                if (!secret) throw new Error("No client_secret returned");
                setClientSecret(secret);
                setLoading(false);
              })
              .catch((err: any) => {
                throw err;
              });
          });
      })
      .catch((err: any) => {
        if (cancelled) return;
        const msg = String(err?.message || "");
        // 503 / not-configured → friendly bank-transfer notice, not a crash
        if (msg.includes("503") || msg.includes("intent") || msg.includes("config")) {
          setConfigured(false);
        } else {
          setNotice(err?.message || "Could not start card payment.");
          setConfigured(false);
        }
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invoiceId]);

  const handleInnerSuccess = () => {
    setSucceeded(true);
    onSuccess();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-950 p-6 text-zinc-100 shadow-2xl">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">Pay by card</h2>
            <p className="text-sm text-zinc-400">
              {formatGBP(amount)} · Invoice {invoiceId.slice(0, 8)}…
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {loading && (
          <div className="flex items-center justify-center gap-2 py-10 text-zinc-400">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span className="text-sm">Loading secure payment…</span>
          </div>
        )}

        {!loading && succeeded && (
          <div className="py-6 text-center">
            <CheckCircle2 className="mx-auto h-12 w-12 text-green-400" />
            <p className="mt-3 font-semibold">Payment successful</p>
            <p className="mt-1 text-sm text-zinc-400">
              {formatGBP(amount)} paid by card.
            </p>
            <button
              onClick={onClose}
              className="mt-5 w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground"
            >
              Done
            </button>
          </div>
        )}

        {!loading && !succeeded && configured === false && (
          <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-200">
            Card payments not enabled yet — pay by bank transfer.
            {notice && (
              <p className="mt-1 text-xs text-yellow-200/70">{notice}</p>
            )}
            <button
              onClick={onClose}
              className="mt-4 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-100 hover:bg-zinc-800"
            >
              Close
            </button>
          </div>
        )}

        {!loading && !succeeded && configured && !clientSecret && (
          <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-200">
            Card payments not enabled yet — pay by bank transfer.
            <button
              onClick={onClose}
              className="mt-4 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-100 hover:bg-zinc-800"
            >
              Close
            </button>
          </div>
        )}

        {!loading &&
          !succeeded &&
          configured &&
          clientSecret &&
          stripePromise && (
            <Elements stripe={stripePromise as any}>
              <CardForm
                clientSecret={clientSecret}
                amount={amount}
                onSuccess={handleInnerSuccess}
              />
            </Elements>
          )}
      </div>
    </div>
  );
}
