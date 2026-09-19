"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  FileText, Plus, Calendar, RefreshCw, AlertCircle,
} from "lucide-react";

export default function ContractsPage() {
  const { token } = useAuth();
  const [contracts, setContracts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    api.contracts.list(token)
      .then((r: any) => setContracts(r.contracts || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  const statusColor: Record<string, string> = {
    active: "bg-green-500/20 text-green-400",
    draft: "bg-yellow-500/20 text-yellow-400",
    cancelled: "bg-red-500/20 text-red-400",
    expired: "bg-zinc-500/20 text-zinc-400",
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Contracts</h1>
        <Button className="gap-2"><Plus className="h-4 w-4" />New Contract</Button>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : contracts.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <FileText className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium">No contracts yet</h3>
            <p className="text-sm text-muted-foreground mt-1">
              Create recurring service agreements for your customers
            </p>
            <Button className="mt-4 gap-2"><Plus className="h-4 w-4" />Create Contract</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {contracts.map((c) => (
            <Card key={c.id}>
              <CardContent className="py-4 flex items-center justify-between">
                <div>
                  <p className="font-medium">{c.title}</p>
                  <p className="text-sm text-muted-foreground">
                    £{c.monthly_amount}/mo · {c.job_frequency}
                  </p>
                </div>
                <Badge className={statusColor[c.status] || "bg-zinc-500/20 text-zinc-400"}>
                  {c.status}
                </Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
