"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { getStatusColor, getStatusLabel, formatDateTime } from "@/lib/utils";
import { formatMoney, resolveCurrency } from "@/lib/money";
import { Receipt, CheckCircle2, Clock, CreditCard } from "lucide-react";
import { toast } from "sonner";
import CardPaymentModal from "@/components/card-payment-modal";

export default function InvoicesPage() {
  const { token } = useAuth();
  const [invoices, setInvoices] = useState<any[]>([]);
  const [cardInvoice, setCardInvoice] = useState<any | null>(null);
  const [currency, setCurrency] = useState("GBP");

  useEffect(() => {
    if (!token) return;
    loadInvoices();
    api.auth.getBusiness(token).then((r: any) => setCurrency(resolveCurrency(r))).catch(() => setCurrency(resolveCurrency(null)));
  }, [token]);

  const loadInvoices = async () => {
    try {
      const data: any = await api.invoices.list(token!);
      setInvoices(data);
    } catch (e) {
      console.error(e);
    }
  };

  const markPaid = async (id: string) => {
    try {
      await api.invoices.pay(id, token!);
      loadInvoices();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Invoices</h1>
        <p className="text-muted-foreground">Track payments and generate invoices</p>
      </div>

      <div className="space-y-4">
        {invoices.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              No invoices yet. Complete a job to generate an invoice.
            </CardContent>
          </Card>
        ) : (
          invoices.map((invoice) => (
            <Card key={invoice.id} className="hover:border-primary/30 transition-all">
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-green-500/10 shrink-0">
                      <Receipt className="h-5 w-5 text-green-400" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-lg">{invoice.invoice_number}</h3>
                        <Badge className={getStatusColor(invoice.payment_status)}>
                          {getStatusLabel(invoice.payment_status)}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">
                        Created {formatDateTime(invoice.created_at)}
                      </p>
                      {invoice.due_date && (
                        <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          Due {formatDateTime(invoice.due_date)}
                        </p>
                      )}
                      {/* Line items */}
                      <div className="mt-3 space-y-1">
                        {invoice.items?.map((item: any, i: number) => (
                          <div key={i} className="flex justify-between text-sm">
                            <span className="text-muted-foreground">{item.description}</span>
                            <span>
                              {item.quantity} × {formatMoney(item.unit_price, currency)} = {formatMoney(item.total, currency)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-2xl font-bold gradient-text">
                      {formatMoney(invoice.total, currency)}
                    </div>
                    {invoice.amount_paid > 0 && (
                      <p className="text-xs text-green-400">
                        Paid: {formatMoney(invoice.amount_paid, currency)}
                      </p>
                    )}
                    {invoice.payment_status !== "paid" && (
                      <div className="mt-3 flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-1"
                          onClick={() => setCardInvoice(invoice)}
                        >
                          <CreditCard className="h-3.5 w-3.5" />
                          Card
                        </Button>
                        <Button
                          size="sm"
                          className="gap-1"
                          onClick={() => markPaid(invoice.id)}
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Mark Paid
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {cardInvoice && (
        <CardPaymentModal
          invoiceId={cardInvoice.id}
          amount={cardInvoice.total}
          token={token ?? undefined}
          onClose={() => setCardInvoice(null)}
          onSuccess={() => {
            loadInvoices();
            toast.success("Card payment successful");
            setCardInvoice(null);
          }}
        />
      )}
    </div>
  );
}
