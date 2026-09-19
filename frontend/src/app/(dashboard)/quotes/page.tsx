"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { formatCurrency, formatDateTime } from "@/lib/utils";
import { FileText, CheckCircle2, Clock, Send } from "lucide-react";

export default function QuotesPage() {
  const { token } = useAuth();
  const [quotes, setQuotes] = useState<any[]>([]);

  useEffect(() => {
    if (!token) return;
    loadQuotes();
  }, [token]);

  const loadQuotes = async () => {
    try {
      const data: any = await api.quotes.list(token!);
      setQuotes(data);
    } catch (e) {
      console.error(e);
    }
  };

  const acceptQuote = async (id: string) => {
    try {
      await api.quotes.accept(id, token!);
      loadQuotes();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Quotes</h1>
          <p className="text-muted-foreground">Manage your quotes and proposals</p>
        </div>
        <a href="/quote">
          <Button className="gap-2">
            <FileText className="h-4 w-4" />
            New Quote
          </Button>
        </a>
      </div>

      <div className="space-y-4">
        {quotes.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              No quotes yet. Create your first AI-powered quote.
            </CardContent>
          </Card>
        ) : (
          quotes.map((quote) => (
            <Card key={quote.id} className="hover:border-primary/30 transition-all">
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 shrink-0">
                      <FileText className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-lg">
                          {quote.title || quote.quote_number}
                        </h3>
                        <Badge
                          variant={quote.is_accepted ? "default" : "secondary"}
                        >
                          {quote.is_accepted ? "Accepted" : "Pending"}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">
                        {quote.quote_number} • Created {formatDateTime(quote.created_at)}
                      </p>
                      {quote.valid_until && (
                        <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          Valid until {formatDateTime(quote.valid_until)}
                        </p>
                      )}
                      {/* Line items */}
                      <div className="mt-3 space-y-1">
                        {quote.items?.map((item: any, i: number) => (
                          <div key={i} className="flex justify-between text-sm">
                            <span className="text-muted-foreground">{item.description}</span>
                            <span>
                              {item.quantity} × {formatCurrency(item.unit_price)} = {formatCurrency(item.total)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-2xl font-bold gradient-text">
                      {formatCurrency(quote.total)}
                    </div>
                    {quote.tax_amount > 0 && (
                      <p className="text-xs text-muted-foreground">
                        incl. {formatCurrency(quote.tax_amount)} tax
                      </p>
                    )}
                    {!quote.is_accepted && (
                      <Button
                        size="sm"
                        className="mt-3 gap-1"
                        onClick={() => acceptQuote(quote.id)}
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Accept
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
