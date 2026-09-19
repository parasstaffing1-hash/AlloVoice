"use client";

import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { Truck, Plus, MapPin, Clock } from "lucide-react";

export default function FleetPage() {
  const { token } = useAuth();
  const [vehicles, setVehicles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    api.fleet.list(token)
      .then((r: any) => setVehicles(r.vehicles || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  const statusColor: Record<string, string> = {
    active: "bg-green-500/20 text-green-400",
    maintenance: "bg-yellow-500/20 text-yellow-400",
    offline: "bg-zinc-500/20 text-zinc-400",
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Fleet</h1>
        <Button className="gap-2"><Plus className="h-4 w-4" />Add Vehicle</Button>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : vehicles.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <Truck className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium">No vehicles</h3>
            <p className="text-sm text-muted-foreground mt-1">Add vans and track GPS location in real-time</p>
            <Button className="mt-4 gap-2"><Plus className="h-4 w-4" />Add Vehicle</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {vehicles.map((v) => (
            <Card key={v.id}>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="font-medium">{v.registration}</p>
                  <Badge className={statusColor[v.status] || "bg-zinc-500/20 text-zinc-400"}>
                    {v.status}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground">{v.make} {v.model}</p>
                <p className="text-sm text-muted-foreground">Assigned to: {v.assigned_to || "—"}</p>
                {v.last_location && (
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <MapPin className="h-3 w-3" />
                    {v.last_location}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
