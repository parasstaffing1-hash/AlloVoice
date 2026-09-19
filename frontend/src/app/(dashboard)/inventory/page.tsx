"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { Package, Plus, AlertTriangle, ArrowUpDown } from "lucide-react";

export default function InventoryPage() {
  const { token } = useAuth();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!token) return;
    api.inventory.list(token)
      .then((r: any) => setItems(r.items || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  const lowStock = items.filter((i) => i.quantity <= (i.min_stock_level || 0));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Inventory</h1>
        <Button className="gap-2"><Plus className="h-4 w-4" />Add Item</Button>
      </div>

      {lowStock.length > 0 && (
        <Card className="border-yellow-500/50 bg-yellow-500/5">
          <CardContent className="py-4 flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-yellow-400" />
            <p className="text-sm">{lowStock.length} item{lowStock.length !== 1 ? "s" : ""} below minimum stock level</p>
          </CardContent>
        </Card>
      )}

      <div className="flex gap-3">
        <div className="relative flex-1">
          <Package className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Search inventory..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Button variant="outline" className="gap-2"><ArrowUpDown className="h-4 w-4" />Sort</Button>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <Package className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium">No inventory items</h3>
            <p className="text-sm text-muted-foreground mt-1">Track parts, materials and equipment</p>
            <Button className="mt-4 gap-2"><Plus className="h-4 w-4" />Add Item</Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="p-3 font-medium">Name</th>
                  <th className="p-3 font-medium">SKU</th>
                  <th className="p-3 font-medium">Qty</th>
                  <th className="p-3 font-medium">Unit Price</th>
                  <th className="p-3 font-medium">Location</th>
                  <th className="p-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {items
                  .filter((i) => !search || i.name.toLowerCase().includes(search.toLowerCase()))
                  .map((item) => (
                  <tr key={item.id} className="border-b last:border-0">
                    <td className="p-3 font-medium">{item.name}</td>
                    <td className="p-3 text-muted-foreground">{item.sku || "—"}</td>
                    <td className="p-3">{item.quantity}</td>
                    <td className="p-3">£{item.unit_price?.toFixed(2) || "—"}</td>
                    <td className="p-3 text-muted-foreground">{item.location || "—"}</td>
                    <td className="p-3">
                      {item.quantity <= (item.min_stock_level || 0)
                        ? <Badge className="bg-yellow-500/20 text-yellow-400">Low</Badge>
                        : <Badge className="bg-green-500/20 text-green-400">In Stock</Badge>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
