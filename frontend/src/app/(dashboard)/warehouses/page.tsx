"use client";

import { useState, useEffect, useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@/components/data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  Warehouse,
  Package,
  ArrowRightLeft,
  Plus,
  CheckCircle2,
  Truck,
  AlertTriangle,
} from "lucide-react";

type Tab = "depots" | "stock" | "transfers";

function getDepotCount(d: any): number {
  if (typeof d?.sku_count === "number") return d.sku_count;
  if (typeof d?.item_count === "number") return d.item_count;
  if (Array.isArray(d?.stock)) return d.stock.length;
  if (Array.isArray(d?.items)) return d.items.length;
  return 0;
}

function getStockList(detail: any): any[] {
  if (!detail) return [];
  if (Array.isArray(detail?.stock)) return detail.stock;
  if (Array.isArray(detail?.items)) return detail.items;
  if (Array.isArray(detail?.warehouse?.stock)) return detail.warehouse.stock;
  if (Array.isArray(detail?.warehouse?.items)) return detail.warehouse.items;
  if (Array.isArray(detail?.inventory)) return detail.inventory;
  return [];
}

function transferStatusBadge(status: string) {
  const s = (status || "").toLowerCase();
  if (s === "in_transit")
    return <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30">In transit</Badge>;
  if (s === "completed")
    return <Badge className="bg-green-500/20 text-green-400 border-green-500/30">Completed</Badge>;
  if (s === "partial")
    return <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/30">Partial</Badge>;
  return <Badge variant="secondary">{status || "Unknown"}</Badge>;
}

export default function WarehousesPage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<Tab>("depots");

  // Depots
  const [depots, setDepots] = useState<any[]>([]);
  const [loadingDepots, setLoadingDepots] = useState(true);
  const [selectedDepotId, setSelectedDepotId] = useState<string | null>(null);
  const [depotDetail, setDepotDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [createForm, setCreateForm] = useState({ name: "", address: "", postcode: "", is_default: false });
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Stock
  const [stockDepotId, setStockDepotId] = useState<string>("");
  const [stockDetail, setStockDetail] = useState<any>(null);
  const [stockLoading, setStockLoading] = useState(false);
  const [adjustForm, setAdjustForm] = useState({ sku: "", quantity_change: "", reason: "" });
  const [adjusting, setAdjusting] = useState(false);

  // Transfers
  const [transfers, setTransfers] = useState<any[]>([]);
  const [loadingTransfers, setLoadingTransfers] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [transferForm, setTransferForm] = useState({
    from_warehouse_id: "",
    to_warehouse_id: "",
    notes: "",
    items: [{ sku: "", name: "", quantity: 1 }] as { sku: string; name: string; quantity: number }[],
  });
  const [creatingTransfer, setCreatingTransfer] = useState(false);
  const [receivingId, setReceivingId] = useState<string | null>(null);

  const fetchDepots = () => {
    if (!token) return;
    setLoadingDepots(true);
    setError(null);
    api.warehouses
      .list(token)
      .then((r: any) => {
        const list = r?.warehouses || r?.items || r?.data || (Array.isArray(r) ? r : []);
        setDepots(Array.isArray(list) ? list : []);
        if (!stockDepotId && Array.isArray(list) && list.length > 0) {
          setStockDepotId(list[0].id);
        }
        if (!transferForm.from_warehouse_id && Array.isArray(list) && list.length > 0) {
          setTransferForm((f) => ({ ...f, from_warehouse_id: f.from_warehouse_id || list[0].id }));
        }
      })
      .catch((e: any) => setError(e?.message || "Failed to load depots"))
      .finally(() => setLoadingDepots(false));
  };

  const fetchDepotDetail = (id: string) => {
    if (!token || !id) return;
    setDetailLoading(true);
    api.warehouses
      .get(id, token)
      .then((r: any) => {
        setDepotDetail(r?.warehouse || r?.data || r);
      })
      .catch((e: any) => setError(e?.message || "Failed to load depot detail"))
      .finally(() => setDetailLoading(false));
  };

  const fetchStock = (id: string) => {
    if (!token || !id) return;
    setStockLoading(true);
    api.warehouses
      .get(id, token)
      .then((r: any) => {
        setStockDetail(r?.warehouse || r?.data || r);
      })
      .catch((e: any) => setError(e?.message || "Failed to load stock"))
      .finally(() => setStockLoading(false));
  };

  const fetchTransfers = () => {
    if (!token) return;
    setLoadingTransfers(true);
    api.warehouses
      .listTransfers(token, statusFilter || undefined, undefined)
      .then((r: any) => {
        const list = r?.transfers || r?.items || r?.data || (Array.isArray(r) ? r : []);
        setTransfers(Array.isArray(list) ? list : []);
      })
      .catch((e: any) => setError(e?.message || "Failed to load transfers"))
      .finally(() => setLoadingTransfers(false));
  };

  useEffect(() => {
    if (!token) return;
    fetchDepots();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  useEffect(() => {
    if (!token) return;
    fetchTransfers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, statusFilter]);

  useEffect(() => {
    if (selectedDepotId) fetchDepotDetail(selectedDepotId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDepotId]);

  useEffect(() => {
    if (stockDepotId) fetchStock(stockDepotId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stockDepotId]);

  const handleCreateDepot = (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !createForm.name.trim()) return;
    setCreating(true);
    setMessage(null);
    setError(null);
    api.warehouses
      .create(
        {
          name: createForm.name.trim(),
          address: createForm.address.trim() || undefined,
          postcode: createForm.postcode.trim() || undefined,
          is_default: createForm.is_default,
        },
        token
      )
      .then((r: any) => {
        setMessage("Depot created");
        setCreateForm({ name: "", address: "", postcode: "", is_default: false });
        fetchDepots();
        const created = r?.warehouse || r?.data || r;
        if (created?.id) {
          setSelectedDepotId(created.id);
        }
      })
      .catch((e: any) => setError(e?.message || "Failed to create depot"))
      .finally(() => setCreating(false));
  };

  const handleAdjust = (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !stockDepotId || !adjustForm.sku.trim()) return;
    const qty = Number(adjustForm.quantity_change);
    if (Number.isNaN(qty) || qty === 0) {
      setError("Quantity change must be a non-zero number");
      return;
    }
    setAdjusting(true);
    setMessage(null);
    setError(null);
    api.warehouses
      .adjust(
        stockDepotId,
        { sku: adjustForm.sku.trim(), quantity_change: qty, reason: adjustForm.reason.trim() || undefined },
        token
      )
      .then((r: any) => {
        setMessage("Stock adjusted");
        setAdjustForm({ sku: "", quantity_change: "", reason: "" });
        fetchStock(stockDepotId);
      })
      .catch((e: any) => setError(e?.message || "Failed to adjust stock"))
      .finally(() => setAdjusting(false));
  };

  const updateTransferItem = (index: number, field: "sku" | "name" | "quantity", value: string | number) => {
    setTransferForm((f) => {
      const items = [...f.items];
      items[index] = { ...items[index], [field]: value };
      return { ...f, items };
    });
  };

  const addTransferItem = () => {
    setTransferForm((f) => ({ ...f, items: [...f.items, { sku: "", name: "", quantity: 1 }] }));
  };

  const removeTransferItem = (index: number) => {
    setTransferForm((f) => ({ ...f, items: f.items.filter((_, i) => i !== index) }));
  };

  const handleCreateTransfer = (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    if (!transferForm.from_warehouse_id || !transferForm.to_warehouse_id) {
      setError("Select both source and destination depots");
      return;
    }
    if (transferForm.from_warehouse_id === transferForm.to_warehouse_id) {
      setError("Source and destination depots must differ");
      return;
    }
    const items = transferForm.items
      .filter((i) => i.sku.trim() && Number(i.quantity) > 0)
      .map((i) => ({ sku: i.sku.trim(), name: i.name.trim() || i.sku.trim(), quantity: Number(i.quantity) }));
    if (items.length === 0) {
      setError("Add at least one item with SKU and quantity");
      return;
    }
    setCreatingTransfer(true);
    setMessage(null);
    setError(null);
    api.warehouses
      .createTransfer(
        {
          from_warehouse_id: transferForm.from_warehouse_id,
          to_warehouse_id: transferForm.to_warehouse_id,
          items,
          notes: transferForm.notes.trim() || undefined,
        },
        token
      )
      .then((r: any) => {
        setMessage("Transfer created");
        setTransferForm((f) => ({
          from_warehouse_id: f.from_warehouse_id,
          to_warehouse_id: f.to_warehouse_id,
          notes: "",
          items: [{ sku: "", name: "", quantity: 1 }],
        }));
        fetchTransfers();
      })
      .catch((e: any) => setError(e?.message || "Failed to create transfer"))
      .finally(() => setCreatingTransfer(false));
  };

  const handleReceive = (id: string) => {
    if (!token) return;
    setReceivingId(id);
    setMessage(null);
    setError(null);
    api.warehouses
      .receiveTransfer(id, token)
      .then((r: any) => {
        setMessage("Transfer received");
        fetchTransfers();
      })
      .catch((e: any) => setError(e?.message || "Failed to receive transfer"))
      .finally(() => setReceivingId(null));
  };

  const depotNameById = (id: string) => depots.find((d) => d.id === id)?.name || id?.slice(0, 8) || "—";

  const transferColumns: ColumnDef<any, any>[] = useMemo(
    () => [
      {
        id: "id",
        accessorKey: "id",
        header: "ID",
        cell: ({ row }) => (
          <span className="font-mono text-xs">{String(row.original.id).slice(0, 8)}</span>
        ),
      },
      {
        id: "route",
        header: "Route",
        accessorFn: (row: any) =>
          `${row.from_warehouse_name || depotNameById(row.from_warehouse_id || row.from_id)} ${row.to_warehouse_name || depotNameById(row.to_warehouse_id || row.to_id)}`,
        cell: ({ row }: any) => {
          const t = row.original;
          const from = t.from_warehouse_name || depotNameById(t.from_warehouse_id || t.from_id);
          const to = t.to_warehouse_name || depotNameById(t.to_warehouse_id || t.to_id);
          return (
            <span className="flex items-center gap-1">
              {from} <ArrowRightLeft className="h-3 w-3 text-muted-foreground" /> {to}
            </span>
          );
        },
      },
      {
        id: "items",
        header: "Items",
        accessorFn: (row: any) =>
          Array.isArray(row.items) ? row.items.length : (row.items_count ?? row.item_count ?? 0),
        cell: ({ row }: any) => {
          const t = row.original;
          return Array.isArray(t.items) ? t.items.length : (t.items_count ?? t.item_count ?? 0);
        },
      },
      {
        id: "status",
        accessorKey: "status",
        header: "Status",
        cell: ({ row }: any) => transferStatusBadge(row.original.status),
      },
      {
        id: "created",
        header: "Created",
        accessorFn: (row: any) => row.created_at || "",
        cell: ({ row }: any) => {
          const created = row.original.created_at
            ? new Date(row.original.created_at).toLocaleDateString("en-GB", {
                day: "2-digit",
                month: "short",
                year: "numeric",
              })
            : "—";
          return <span className="text-muted-foreground">{created}</span>;
        },
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }: any) => {
          const t = row.original;
          const isTransit = (t.status || "").toLowerCase() === "in_transit";
          if (!isTransit) return null;
          return (
            <div className="text-right">
              <Button
                size="sm"
                variant="outline"
                className="gap-1"
                disabled={receivingId === t.id}
                onClick={() => handleReceive(t.id)}
              >
                <CheckCircle2 className="h-3 w-3" />
                {receivingId === t.id ? "Receiving…" : "Receive"}
              </Button>
            </div>
          );
        },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [depots, receivingId]
  );

  const stockList = getStockList(stockDetail);
  const depotStockList = getStockList(depotDetail);
  const lowStockCount = stockList.filter((s: any) => Number(s?.quantity ?? 0) < 5).length;

  const tabs: { key: Tab; label: string }[] = [
    { key: "depots", label: "Depots" },
    { key: "stock", label: "Stock" },
    { key: "transfers", label: "Transfers" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Warehouse className="h-7 w-7" /> Depots & Stock Transfers
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Manage depots, stock levels and inter-depot transfers</p>
        </div>
      </div>

      <div className="flex gap-2 border-b border-zinc-800 pb-2">
        {tabs.map((t) => (
          <Button
            key={t.key}
            variant={tab === t.key ? "default" : "ghost"}
            size="sm"
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </Button>
        ))}
      </div>

      {message && (
        <Card className="border-green-500/40 bg-green-500/10">
          <CardContent className="py-3 flex items-center gap-2 text-sm text-green-300">
            <CheckCircle2 className="h-4 w-4" /> {message}
          </CardContent>
        </Card>
      )}
      {error && (
        <Card className="border-red-500/40 bg-red-500/10">
          <CardContent className="py-3 flex items-center gap-2 text-sm text-red-300">
            <AlertTriangle className="h-4 w-4" /> {error}
          </CardContent>
        </Card>
      )}

      {tab === "depots" && (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-4">
            {loadingDepots ? (
              <p className="text-muted-foreground">Loading depots…</p>
            ) : depots.length === 0 ? (
              <Card>
                <CardContent className="py-16 text-center">
                  <Warehouse className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                  <h3 className="text-lg font-medium">No depots yet</h3>
                  <p className="text-sm text-muted-foreground mt-1">Create your first depot to hold stock</p>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                {depots.map((d) => (
                  <Card
                    key={d.id}
                    className={`cursor-pointer transition-colors hover:border-zinc-600 ${
                      selectedDepotId === d.id ? "border-primary" : ""
                    }`}
                    onClick={() => setSelectedDepotId(d.id)}
                  >
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base flex items-center gap-2">
                        <Warehouse className="h-4 w-4" /> {d.name}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-sm">
                      <p className="text-muted-foreground">{d.address || "No address"}</p>
                      <p className="text-muted-foreground">{d.postcode || "No postcode"}</p>
                      <div className="flex items-center gap-2 pt-1">
                        {d.is_default && <Badge className="bg-blue-500/20 text-blue-400">Default</Badge>}
                        <Badge variant="secondary" className="gap-1">
                          <Package className="h-3 w-3" /> {getDepotCount(d)} SKUs
                        </Badge>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            {selectedDepotId && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Package className="h-5 w-5" /> Stock snapshot
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {detailLoading ? (
                    <p className="text-sm text-muted-foreground">Loading detail…</p>
                  ) : !depotDetail ? (
                    <p className="text-sm text-muted-foreground">Select a depot to view its stock.</p>
                  ) : (
                    <div className="space-y-3">
                      <div className="text-sm">
                        <p className="font-medium">{depotDetail?.name || depotDetail?.warehouse?.name}</p>
                        <p className="text-muted-foreground">
                          {(depotDetail?.address || "")} {(depotDetail?.postcode || "")}
                        </p>
                      </div>
                      {depotStockList.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No stock recorded at this depot.</p>
                      ) : (
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b text-left text-muted-foreground">
                              <th className="p-2 font-medium">SKU</th>
                              <th className="p-2 font-medium">Name</th>
                              <th className="p-2 font-medium">Qty</th>
                            </tr>
                          </thead>
                          <tbody>
                            {depotStockList.map((s: any, i: number) => (
                              <tr key={`${s.sku || i}-${i}`} className="border-b last:border-0">
                                <td className="p-2 font-mono">{s.sku || "—"}</td>
                                <td className="p-2">{s.name || s.item_name || "—"}</td>
                                <td className="p-2">
                                  {s.quantity ?? s.qty ?? 0}{" "}
                                  {Number(s.quantity ?? s.qty ?? 0) < 5 && (
                                    <Badge className="ml-2 bg-red-500/20 text-red-400">Low</Badge>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>

          <div>
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Plus className="h-5 w-5" /> New depot
                </CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleCreateDepot} className="space-y-3">
                  <Input
                    placeholder="Depot name e.g. Manchester North"
                    value={createForm.name}
                    onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                    required
                  />
                  <Input
                    placeholder="Address"
                    value={createForm.address}
                    onChange={(e) => setCreateForm((f) => ({ ...f, address: e.target.value }))}
                  />
                  <Input
                    placeholder="Postcode e.g. M1 1AE"
                    value={createForm.postcode}
                    onChange={(e) => setCreateForm((f) => ({ ...f, postcode: e.target.value.toUpperCase() }))}
                  />
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={createForm.is_default}
                      onChange={(e) => setCreateForm((f) => ({ ...f, is_default: e.target.checked }))}
                      className="h-4 w-4 rounded border-zinc-700"
                    />
                    Set as default depot
                  </label>
                  <Button type="submit" disabled={creating} className="w-full gap-2">
                    <Plus className="h-4 w-4" /> {creating ? "Creating…" : "Create depot"}
                  </Button>
                </form>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {tab === "stock" && (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Package className="h-5 w-5" /> Stock levels
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center gap-3">
                  <label className="text-sm text-muted-foreground whitespace-nowrap">Depot</label>
                  <select
                    value={stockDepotId}
                    onChange={(e) => setStockDepotId(e.target.value)}
                    className="flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                  >
                    <option value="">Select depot…</option>
                    {depots.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                </div>

                {lowStockCount > 0 && (
                  <div className="flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
                    <AlertTriangle className="h-4 w-4" />
                    {lowStockCount} low-stock line{lowStockCount !== 1 ? "s" : ""} (below 5 units)
                  </div>
                )}

                {stockLoading ? (
                  <p className="text-sm text-muted-foreground">Loading stock…</p>
                ) : !stockDepotId ? (
                  <p className="text-sm text-muted-foreground">Select a depot to view stock.</p>
                ) : stockList.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No stock lines at this depot.</p>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="p-2 font-medium">SKU</th>
                        <th className="p-2 font-medium">Name</th>
                        <th className="p-2 font-medium">Quantity</th>
                        <th className="p-2 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stockList.map((s: any, i: number) => {
                        const qty = Number(s.quantity ?? s.qty ?? 0);
                        return (
                          <tr key={`${s.sku || i}-${i}`} className="border-b last:border-0">
                            <td className="p-2 font-mono">{s.sku || "—"}</td>
                            <td className="p-2">{s.name || s.item_name || "—"}</td>
                            <td className="p-2 font-medium">{qty}</td>
                            <td className="p-2">
                              {qty < 5 ? (
                                <Badge className="bg-red-500/20 text-red-400 border-red-500/30 gap-1">
                                  <AlertTriangle className="h-3 w-3" /> Low
                                </Badge>
                              ) : (
                                <Badge className="bg-green-500/20 text-green-400 border-green-500/30">OK</Badge>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          </div>

          <div>
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Adjust stock</CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleAdjust} className="space-y-3">
                  <Input
                    placeholder="SKU"
                    value={adjustForm.sku}
                    onChange={(e) => setAdjustForm((f) => ({ ...f, sku: e.target.value }))}
                    required
                  />
                  <Input
                    placeholder="Quantity change e.g. 5 or -3"
                    type="number"
                    value={adjustForm.quantity_change}
                    onChange={(e) => setAdjustForm((f) => ({ ...f, quantity_change: e.target.value }))}
                    required
                  />
                  <Input
                    placeholder="Reason e.g. stocktake correction"
                    value={adjustForm.reason}
                    onChange={(e) => setAdjustForm((f) => ({ ...f, reason: e.target.value }))}
                  />
                  <Button type="submit" disabled={adjusting || !stockDepotId} className="w-full">
                    {adjusting ? "Adjusting…" : "Apply adjustment"}
                  </Button>
                </form>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {tab === "transfers" && (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Truck className="h-5 w-5" /> Transfers
                  </CardTitle>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="h-9 rounded-lg border border-input bg-background px-3 text-sm"
                  >
                    <option value="">All statuses</option>
                    <option value="in_transit">In transit</option>
                    <option value="completed">Completed</option>
                    <option value="partial">Partial</option>
                  </select>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                {loadingTransfers ? (
                  <p className="p-6 text-sm text-muted-foreground">Loading transfers…</p>
                ) : transfers.length === 0 ? (
                  <div className="py-12 text-center">
                    <ArrowRightLeft className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
                    <p className="font-medium">No transfers</p>
                    <p className="text-sm text-muted-foreground">Move stock between depots</p>
                  </div>
                ) : (
                  <div className="p-4">
                    <DataTable
                      columns={transferColumns}
                      data={transfers}
                      filterColumn="route"
                      filterPlaceholder="Filter by route…"
                      pageSize={10}
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div>
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Plus className="h-5 w-5" /> New transfer
                </CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleCreateTransfer} className="space-y-3">
                  <div>
                    <label className="text-xs text-muted-foreground">From depot</label>
                    <select
                      value={transferForm.from_warehouse_id}
                      onChange={(e) => setTransferForm((f) => ({ ...f, from_warehouse_id: e.target.value }))}
                      className="mt-1 flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                      required
                    >
                      <option value="">Select source…</option>
                      {depots.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">To depot</label>
                    <select
                      value={transferForm.to_warehouse_id}
                      onChange={(e) => setTransferForm((f) => ({ ...f, to_warehouse_id: e.target.value }))}
                      className="mt-1 flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                      required
                    >
                      <option value="">Select destination…</option>
                      {depots.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs text-muted-foreground">Items</label>
                    {transferForm.items.map((item, idx) => (
                      <div key={idx} className="grid grid-cols-[1fr_1fr_64px_auto] gap-2">
                        <Input
                          placeholder="SKU"
                          value={item.sku}
                          onChange={(e) => updateTransferItem(idx, "sku", e.target.value)}
                        />
                        <Input
                          placeholder="Name"
                          value={item.name}
                          onChange={(e) => updateTransferItem(idx, "name", e.target.value)}
                        />
                        <Input
                          type="number"
                          min={1}
                          value={item.quantity}
                          onChange={(e) => updateTransferItem(idx, "quantity", Number(e.target.value))}
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={transferForm.items.length === 1}
                          onClick={() => removeTransferItem(idx)}
                        >
                          ✕
                        </Button>
                      </div>
                    ))}
                    <Button type="button" variant="outline" size="sm" className="gap-1" onClick={addTransferItem}>
                      <Plus className="h-3 w-3" /> Add row
                    </Button>
                  </div>

                  <Input
                    placeholder="Notes (optional)"
                    value={transferForm.notes}
                    onChange={(e) => setTransferForm((f) => ({ ...f, notes: e.target.value }))}
                  />
                  <Button type="submit" disabled={creatingTransfer} className="w-full gap-2">
                    <Truck className="h-4 w-4" /> {creatingTransfer ? "Creating…" : "Create transfer"}
                  </Button>
                </form>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
