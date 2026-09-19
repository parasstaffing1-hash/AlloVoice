"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  DollarSign,
  Package,
  Settings,
  Calculator,
  Plus,
  Edit,
  Trash2,
  Save,
  X,
  RotateCcw,
} from "lucide-react";

interface Service {
  id: string;
  name: string;
  category: string;
  description?: string;
  base_price: number;
  unit: string;
  estimated_duration_minutes?: number;
  vat_rate: number;
}

interface Material {
  id: string;
  name: string;
  sku: string;
  category: string;
  unit_price: number;
  unit: string;
  supplier?: string;
  markup_percent: number;
}

interface MarkupRules {
  default_markup: number;
  emergency_markup: number;
  weekend_markup: number;
}

interface QuoteTemplate {
  includes_vat: boolean;
  payment_terms: string;
  valid_days: number;
  terms_text: string;
}

interface CalcResult {
  subtotal: number;
  materials_cost: number;
  labour_cost: number;
  markup_amount: number;
  vat_amount: number;
  total: number;
}

const TABS = [
  { key: "services", label: "Services", icon: Settings },
  { key: "materials", label: "Materials", icon: Package },
  { key: "markups", label: "Markup Rules", icon: DollarSign },
  { key: "template", label: "Quote Template", icon: Settings },
  { key: "calculator", label: "Calculator", icon: Calculator },
] as const;

type TabKey = (typeof TABS)[number]["key"];

const emptyService = {
  name: "",
  category: "",
  description: "",
  base_price: 0,
  unit: "fixed",
  estimated_duration_minutes: 0,
  vat_rate: 20,
};

const emptyMaterial = {
  name: "",
  sku: "",
  category: "",
  unit_price: 0,
  unit: "each",
  supplier: "",
  markup_percent: 0,
};

export default function PriceBookPage() {
  const { token } = useAuth();
  const [activeTab, setActiveTab] = useState<TabKey>("services");

  const [services, setServices] = useState<Service[]>([]);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [markups, setMarkups] = useState<MarkupRules>({
    default_markup: 30,
    emergency_markup: 50,
    weekend_markup: 25,
  });
  const [quoteTemplate, setQuoteTemplate] = useState<QuoteTemplate>({
    includes_vat: true,
    payment_terms: "Net 30",
    valid_days: 30,
    terms_text: "",
  });

  const [serviceForm, setServiceForm] = useState(emptyService);
  const [materialForm, setMaterialForm] = useState(emptyMaterial);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<any>({});

  const [categoryFilter, setCategoryFilter] = useState("");
  const [calcServiceIds, setCalcServiceIds] = useState<
    { id: string; quantity: number }[]
  >([]);
  const [calcMaterialIds, setCalcMaterialIds] = useState<
    { id: string; quantity: number }[]
  >([]);
  const [calcJobType, setCalcJobType] = useState<string>("standard");
  const [calcResult, setCalcResult] = useState<CalcResult | null>(null);

  useEffect(() => {
    if (!token) return;
    loadAll();
  }, [token]);

  const loadAll = async () => {
    try {
      const [s, m, mk, qt] = await Promise.all([
        api.pricebook.listServices(token!),
        api.pricebook.listMaterials(token!),
        api.pricebook.getMarkups(token!),
        api.pricebook.getQuoteTemplate(token!),
      ]);
      setServices(s as Service[]);
      setMaterials(m as Material[]);
      setMarkups(mk as MarkupRules);
      setQuoteTemplate(qt as QuoteTemplate);
    } catch (e) {
      console.error(e);
    }
  };

  const loadServices = async () => {
    try {
      const data: any = await api.pricebook.listServices(
        token!,
        categoryFilter || undefined
      );
      setServices(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (token) loadServices();
  }, [categoryFilter, token]);

  const createService = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.pricebook.createService(serviceForm, token!);
      setServiceForm(emptyService);
      loadServices();
    } catch (e) {
      console.error(e);
    }
  };

  const updateService = async (id: string) => {
    try {
      await api.pricebook.updateService(id, editForm, token!);
      setEditingId(null);
      loadServices();
    } catch (e) {
      console.error(e);
    }
  };

  const deleteService = async (id: string) => {
    if (!confirm("Delete this service?")) return;
    try {
      await api.pricebook.deleteService(id, token!);
      loadServices();
    } catch (e) {
      console.error(e);
    }
  };

  const createMaterial = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.pricebook.createMaterial(materialForm, token!);
      setMaterialForm(emptyMaterial);
      loadAll();
    } catch (e) {
      console.error(e);
    }
  };

  const updateMaterial = async (id: string) => {
    try {
      await api.pricebook.updateMaterial(id, editForm, token!);
      setEditingId(null);
      loadAll();
    } catch (e) {
      console.error(e);
    }
  };

  const deleteMaterial = async (id: string) => {
    if (!confirm("Delete this material?")) return;
    try {
      await api.pricebook.deleteMaterial(id, token!);
      loadAll();
    } catch (e) {
      console.error(e);
    }
  };

  const saveMarkups = async () => {
    try {
      await api.pricebook.updateMarkups(markups, token!);
    } catch (e) {
      console.error(e);
    }
  };

  const saveQuoteTemplate = async () => {
    try {
      await api.pricebook.updateQuoteTemplate(quoteTemplate, token!);
    } catch (e) {
      console.error(e);
    }
  };

  const runCalculation = async () => {
    try {
      const result: any = await api.pricebook.calculate(
        {
          services: calcServiceIds,
          materials: calcMaterialIds,
          job_type: calcJobType,
        },
        token!
      );
      setCalcResult(result);
    } catch (e) {
      console.error(e);
    }
  };

  const startEditService = (svc: Service) => {
    setEditingId(svc.id);
    setEditForm({ ...svc });
  };

  const startEditMaterial = (mat: Material) => {
    setEditingId(mat.id);
    setEditForm({ ...mat });
  };

  const calcTotal = (result: CalcResult) =>
    `£${result.total.toLocaleString("en-GB", { minimumFractionDigits: 2 })}`;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Price Book</h1>
          <p className="text-muted-foreground">
            Manage services, materials, markups &amp; quotes
          </p>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 border-b">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
                activeTab === tab.key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ── SERVICES TAB ── */}
      {activeTab === "services" && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <Input
              placeholder="Filter by category..."
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="max-w-xs"
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Add Service</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={createService} className="grid gap-4 md:grid-cols-3">
                <Input
                  placeholder="Name"
                  value={serviceForm.name}
                  onChange={(e) =>
                    setServiceForm({ ...serviceForm, name: e.target.value })
                  }
                  required
                />
                <Input
                  placeholder="Category"
                  value={serviceForm.category}
                  onChange={(e) =>
                    setServiceForm({
                      ...serviceForm,
                      category: e.target.value,
                    })
                  }
                  required
                />
                <Input
                  placeholder="Description"
                  value={serviceForm.description || ""}
                  onChange={(e) =>
                    setServiceForm({
                      ...serviceForm,
                      description: e.target.value,
                    })
                  }
                />
                <Input
                  type="number"
                  step="0.01"
                  placeholder="Base Price (£)"
                  value={serviceForm.base_price || ""}
                  onChange={(e) =>
                    setServiceForm({
                      ...serviceForm,
                      base_price: parseFloat(e.target.value) || 0,
                    })
                  }
                  required
                />
                <Input
                  placeholder="Unit (fixed/hour/day)"
                  value={serviceForm.unit}
                  onChange={(e) =>
                    setServiceForm({ ...serviceForm, unit: e.target.value })
                  }
                />
                <Input
                  type="number"
                  step="0.5"
                  placeholder="Duration (min)"
                  value={serviceForm.estimated_duration_minutes || ""}
                  onChange={(e) =>
                    setServiceForm({
                      ...serviceForm,
                      estimated_duration_minutes:
                        parseFloat(e.target.value) || 0,
                    })
                  }
                />
                <Input
                  type="number"
                  step="0.1"
                  placeholder="VAT %"
                  value={serviceForm.vat_rate}
                  onChange={(e) =>
                    setServiceForm({
                      ...serviceForm,
                      vat_rate: parseFloat(e.target.value) || 0,
                    })
                  }
                />
                <div className="md:col-span-3">
                  <Button type="submit" className="gap-2">
                    <Plus className="h-4 w-4" />
                    Add Service
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="text-left p-3 font-medium">Name</th>
                      <th className="text-left p-3 font-medium">Category</th>
                      <th className="text-right p-3 font-medium">Price</th>
                      <th className="text-right p-3 font-medium">Duration</th>
                      <th className="text-right p-3 font-medium">VAT</th>
                      <th className="text-right p-3 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {services.length === 0 ? (
                      <tr>
                        <td
                          colSpan={6}
                          className="p-6 text-center text-muted-foreground"
                        >
                          No services yet.
                        </td>
                      </tr>
                    ) : (
                      services.map((svc) => (
                        <tr key={svc.id} className="border-b last:border-0">
                          {editingId === svc.id ? (
                            <>
                              <td className="p-2">
                                <Input
                                  value={editForm.name}
                                  onChange={(e) =>
                                    setEditForm({
                                      ...editForm,
                                      name: e.target.value,
                                    })
                                  }
                                  className="h-8 text-xs"
                                />
                              </td>
                              <td className="p-2">
                                <Input
                                  value={editForm.category}
                                  onChange={(e) =>
                                    setEditForm({
                                      ...editForm,
                                      category: e.target.value,
                                    })
                                  }
                                  className="h-8 text-xs"
                                />
                              </td>
                              <td className="p-2">
                                <Input
                                  type="number"
                                  step="0.01"
                                  value={editForm.base_price}
                                  onChange={(e) =>
                                    setEditForm({
                                      ...editForm,
                                      base_price:
                                        parseFloat(e.target.value) || 0,
                                    })
                                  }
                                  className="h-8 text-xs text-right"
                                />
                              </td>
                              <td className="p-2">
                                <Input
                                  type="number"
                                  value={
                                    editForm.estimated_duration_minutes || ""
                                  }
                                  onChange={(e) =>
                                    setEditForm({
                                      ...editForm,
                                      estimated_duration_minutes:
                                        parseFloat(e.target.value) || 0,
                                    })
                                  }
                                  className="h-8 text-xs text-right"
                                />
                              </td>
                              <td className="p-2">
                                <Input
                                  type="number"
                                  step="0.1"
                                  value={editForm.vat_rate}
                                  onChange={(e) =>
                                    setEditForm({
                                      ...editForm,
                                      vat_rate:
                                        parseFloat(e.target.value) || 0,
                                    })
                                  }
                                  className="h-8 text-xs text-right"
                                />
                              </td>
                              <td className="p-2">
                                <div className="flex justify-end gap-1">
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => updateService(svc.id)}
                                  >
                                    <Save className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => setEditingId(null)}
                                  >
                                    <X className="h-3.5 w-3.5" />
                                  </Button>
                                </div>
                              </td>
                            </>
                          ) : (
                            <>
                              <td className="p-3 font-medium">{svc.name}</td>
                              <td className="p-3">
                                <Badge variant="secondary">
                                  {svc.category}
                                </Badge>
                              </td>
                              <td className="p-3 text-right">
                                £
                                {svc.base_price.toLocaleString("en-GB", {
                                  minimumFractionDigits: 2,
                                })}
                              </td>
                              <td className="p-3 text-right text-muted-foreground">
                                {svc.estimated_duration_minutes
                                  ? `${svc.estimated_duration_minutes} min`
                                  : "—"}
                              </td>
                              <td className="p-3 text-right text-muted-foreground">
                                {svc.vat_rate}%
                              </td>
                              <td className="p-3">
                                <div className="flex justify-end gap-1">
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => startEditService(svc)}
                                  >
                                    <Edit className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => deleteService(svc.id)}
                                    className="text-destructive hover:text-destructive"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>
                                </div>
                              </td>
                            </>
                          )}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── MATERIALS TAB ── */}
      {activeTab === "materials" && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Add Material</CardTitle>
            </CardHeader>
            <CardContent>
              <form
                onSubmit={createMaterial}
                className="grid gap-4 md:grid-cols-3"
              >
                <Input
                  placeholder="Name"
                  value={materialForm.name}
                  onChange={(e) =>
                    setMaterialForm({ ...materialForm, name: e.target.value })
                  }
                  required
                />
                <Input
                  placeholder="SKU"
                  value={materialForm.sku}
                  onChange={(e) =>
                    setMaterialForm({ ...materialForm, sku: e.target.value })
                  }
                  required
                />
                <Input
                  placeholder="Category"
                  value={materialForm.category}
                  onChange={(e) =>
                    setMaterialForm({
                      ...materialForm,
                      category: e.target.value,
                    })
                  }
                  required
                />
                <Input
                  type="number"
                  step="0.01"
                  placeholder="Unit Price (£)"
                  value={materialForm.unit_price || ""}
                  onChange={(e) =>
                    setMaterialForm({
                      ...materialForm,
                      unit_price: parseFloat(e.target.value) || 0,
                    })
                  }
                  required
                />
                <Input
                  placeholder="Unit (each/box/metre)"
                  value={materialForm.unit}
                  onChange={(e) =>
                    setMaterialForm({ ...materialForm, unit: e.target.value })
                  }
                />
                <Input
                  placeholder="Supplier"
                  value={materialForm.supplier || ""}
                  onChange={(e) =>
                    setMaterialForm({
                      ...materialForm,
                      supplier: e.target.value,
                    })
                  }
                />
                <Input
                  type="number"
                  step="0.1"
                  placeholder="Markup %"
                  value={materialForm.markup_percent || ""}
                  onChange={(e) =>
                    setMaterialForm({
                      ...materialForm,
                      markup_percent: parseFloat(e.target.value) || 0,
                    })
                  }
                />
                <div className="md:col-span-3">
                  <Button type="submit" className="gap-2">
                    <Plus className="h-4 w-4" />
                    Add Material
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      <th className="text-left p-3 font-medium">Name</th>
                      <th className="text-left p-3 font-medium">SKU</th>
                      <th className="text-left p-3 font-medium">Category</th>
                      <th className="text-right p-3 font-medium">Price</th>
                      <th className="text-right p-3 font-medium">Markup</th>
                      <th className="text-left p-3 font-medium">Supplier</th>
                      <th className="text-right p-3 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {materials.length === 0 ? (
                      <tr>
                        <td
                          colSpan={7}
                          className="p-6 text-center text-muted-foreground"
                        >
                          No materials yet.
                        </td>
                      </tr>
                    ) : (
                      materials.map((mat) => (
                        <tr key={mat.id} className="border-b last:border-0">
                          {editingId === mat.id ? (
                            <>
                              <td className="p-2">
                                <Input
                                  value={editForm.name}
                                  onChange={(e) =>
                                    setEditForm({
                                      ...editForm,
                                      name: e.target.value,
                                    })
                                  }
                                  className="h-8 text-xs"
                                />
                              </td>
                              <td className="p-2">
                                <Input
                                  value={editForm.sku}
                                  onChange={(e) =>
                                    setEditForm({
                                      ...editForm,
                                      sku: e.target.value,
                                    })
                                  }
                                  className="h-8 text-xs"
                                />
                              </td>
                              <td className="p-2">
                                <Input
                                  value={editForm.category}
                                  onChange={(e) =>
                                    setEditForm({
                                      ...editForm,
                                      category: e.target.value,
                                    })
                                  }
                                  className="h-8 text-xs"
                                />
                              </td>
                              <td className="p-2">
                                <Input
                                  type="number"
                                  step="0.01"
                                  value={editForm.unit_price}
                                  onChange={(e) =>
                                    setEditForm({
                                      ...editForm,
                                      unit_price:
                                        parseFloat(e.target.value) || 0,
                                    })
                                  }
                                  className="h-8 text-xs text-right"
                                />
                              </td>
                              <td className="p-2">
                                <Input
                                  type="number"
                                  step="0.1"
                                  value={editForm.markup_percent}
                                  onChange={(e) =>
                                    setEditForm({
                                      ...editForm,
                                      markup_percent:
                                        parseFloat(e.target.value) || 0,
                                    })
                                  }
                                  className="h-8 text-xs text-right"
                                />
                              </td>
                              <td className="p-2">
                                <Input
                                  value={editForm.supplier || ""}
                                  onChange={(e) =>
                                    setEditForm({
                                      ...editForm,
                                      supplier: e.target.value,
                                    })
                                  }
                                  className="h-8 text-xs"
                                />
                              </td>
                              <td className="p-2">
                                <div className="flex justify-end gap-1">
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => updateMaterial(mat.id)}
                                  >
                                    <Save className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => setEditingId(null)}
                                  >
                                    <X className="h-3.5 w-3.5" />
                                  </Button>
                                </div>
                              </td>
                            </>
                          ) : (
                            <>
                              <td className="p-3 font-medium">{mat.name}</td>
                              <td className="p-3 text-muted-foreground font-mono text-xs">
                                {mat.sku}
                              </td>
                              <td className="p-3">
                                <Badge variant="secondary">
                                  {mat.category}
                                </Badge>
                              </td>
                              <td className="p-3 text-right">
                                £
                                {mat.unit_price.toLocaleString("en-GB", {
                                  minimumFractionDigits: 2,
                                })}
                              </td>
                              <td className="p-3 text-right">
                                {mat.markup_percent}%
                              </td>
                              <td className="p-3 text-muted-foreground">
                                {mat.supplier || "—"}
                              </td>
                              <td className="p-3">
                                <div className="flex justify-end gap-1">
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => startEditMaterial(mat)}
                                  >
                                    <Edit className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => deleteMaterial(mat.id)}
                                    className="text-destructive hover:text-destructive"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>
                                </div>
                              </td>
                            </>
                          )}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── MARKUP RULES TAB ── */}
      {activeTab === "markups" && (
        <Card className="max-w-lg">
          <CardHeader>
            <CardTitle className="text-lg">Markup Rules</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Default Markup (%)</label>
              <Input
                type="number"
                step="0.1"
                value={markups.default_markup}
                onChange={(e) =>
                  setMarkups({
                    ...markups,
                    default_markup: parseFloat(e.target.value) || 0,
                  })
                }
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">
                Emergency Markup (%)
              </label>
              <Input
                type="number"
                step="0.1"
                value={markups.emergency_markup}
                onChange={(e) =>
                  setMarkups({
                    ...markups,
                    emergency_markup: parseFloat(e.target.value) || 0,
                  })
                }
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Weekend Markup (%)</label>
              <Input
                type="number"
                step="0.1"
                value={markups.weekend_markup}
                onChange={(e) =>
                  setMarkups({
                    ...markups,
                    weekend_markup: parseFloat(e.target.value) || 0,
                  })
                }
              />
            </div>
            <Button onClick={saveMarkups} className="gap-2">
              <Save className="h-4 w-4" />
              Save Markup Rules
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ── QUOTE TEMPLATE TAB ── */}
      {activeTab === "template" && (
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle className="text-lg">Quote Template</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium">Includes VAT</label>
              <button
                type="button"
                onClick={() =>
                  setQuoteTemplate({
                    ...quoteTemplate,
                    includes_vat: !quoteTemplate.includes_vat,
                  })
                }
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  quoteTemplate.includes_vat ? "bg-primary" : "bg-muted"
                }`}
              >
                <span
                  className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                    quoteTemplate.includes_vat
                      ? "translate-x-6"
                      : "translate-x-1"
                  }`}
                />
              </button>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Payment Terms</label>
              <Input
                value={quoteTemplate.payment_terms}
                onChange={(e) =>
                  setQuoteTemplate({
                    ...quoteTemplate,
                    payment_terms: e.target.value,
                  })
                }
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Valid For (days)</label>
              <Input
                type="number"
                value={quoteTemplate.valid_days}
                onChange={(e) =>
                  setQuoteTemplate({
                    ...quoteTemplate,
                    valid_days: parseInt(e.target.value) || 30,
                  })
                }
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Terms &amp; Conditions</label>
              <textarea
                value={quoteTemplate.terms_text}
                onChange={(e) =>
                  setQuoteTemplate({
                    ...quoteTemplate,
                    terms_text: e.target.value,
                  })
                }
                rows={5}
                className="flex w-full rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>
            <Button onClick={saveQuoteTemplate} className="gap-2">
              <Save className="h-4 w-4" />
              Save Template
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ── CALCULATOR TAB ── */}
      {activeTab === "calculator" && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Price Calculator</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium">Services</h3>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      setCalcServiceIds([
                        ...calcServiceIds,
                        { id: services[0]?.id || "", quantity: 1 },
                      ])
                    }
                    disabled={services.length === 0}
                    className="gap-1"
                  >
                    <Plus className="h-3 w-3" />
                    Add
                  </Button>
                </div>
                {calcServiceIds.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    No services selected.
                  </p>
                )}
                {calcServiceIds.map((item, idx) => (
                  <div key={idx} className="flex items-center gap-3">
                    <select
                      value={item.id}
                      onChange={(e) => {
                        const updated = [...calcServiceIds];
                        updated[idx] = { ...updated[idx], id: e.target.value };
                        setCalcServiceIds(updated);
                      }}
                      className="flex h-9 rounded-lg border border-input bg-background px-3 text-sm"
                    >
                      <option value="">Select service...</option>
                      {services.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name} (£{s.base_price})
                        </option>
                      ))}
                    </select>
                    <Input
                      type="number"
                      min="0.5"
                      step="0.5"
                      value={item.quantity}
                      onChange={(e) => {
                        const updated = [...calcServiceIds];
                        updated[idx] = {
                          ...updated[idx],
                          quantity: parseFloat(e.target.value) || 1,
                        };
                        setCalcServiceIds(updated);
                      }}
                      className="w-24 h-9"
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        setCalcServiceIds(
                          calcServiceIds.filter((_, i) => i !== idx)
                        )
                      }
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium">Materials</h3>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      setCalcMaterialIds([
                        ...calcMaterialIds,
                        { id: materials[0]?.id || "", quantity: 1 },
                      ])
                    }
                    disabled={materials.length === 0}
                    className="gap-1"
                  >
                    <Plus className="h-3 w-3" />
                    Add
                  </Button>
                </div>
                {calcMaterialIds.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    No materials selected.
                  </p>
                )}
                {calcMaterialIds.map((item, idx) => (
                  <div key={idx} className="flex items-center gap-3">
                    <select
                      value={item.id}
                      onChange={(e) => {
                        const updated = [...calcMaterialIds];
                        updated[idx] = { ...updated[idx], id: e.target.value };
                        setCalcMaterialIds(updated);
                      }}
                      className="flex h-9 rounded-lg border border-input bg-background px-3 text-sm"
                    >
                      <option value="">Select material...</option>
                      {materials.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name} (£{m.unit_price})
                        </option>
                      ))}
                    </select>
                    <Input
                      type="number"
                      min="1"
                      step="1"
                      value={item.quantity}
                      onChange={(e) => {
                        const updated = [...calcMaterialIds];
                        updated[idx] = {
                          ...updated[idx],
                          quantity: parseInt(e.target.value) || 1,
                        };
                        setCalcMaterialIds(updated);
                      }}
                      className="w-24 h-9"
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        setCalcMaterialIds(
                          calcMaterialIds.filter((_, i) => i !== idx)
                        )
                      }
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-4">
                <div className="space-y-1">
                  <label className="text-sm font-medium">Job Type</label>
                  <select
                    value={calcJobType}
                    onChange={(e) => setCalcJobType(e.target.value)}
                    className="flex h-9 rounded-lg border border-input bg-background px-3 text-sm"
                  >
                    <option value="standard">Standard</option>
                    <option value="emergency">Emergency</option>
                    <option value="weekend">Weekend</option>
                  </select>
                </div>
                <Button
                  onClick={runCalculation}
                  className="gap-2 self-end"
                  disabled={
                    calcServiceIds.length === 0 &&
                    calcMaterialIds.length === 0
                  }
                >
                  <Calculator className="h-4 w-4" />
                  Calculate
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setCalcServiceIds([]);
                    setCalcMaterialIds([]);
                    setCalcResult(null);
                  }}
                  className="self-end gap-1"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Reset
                </Button>
              </div>
            </CardContent>
          </Card>

          {calcResult && (
            <Card className="max-w-md">
              <CardHeader>
                <CardTitle className="text-lg">Result</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Labour</span>
                  <span>£{calcResult.labour_cost.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Materials</span>
                  <span>£{calcResult.materials_cost.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Subtotal</span>
                  <span>£{calcResult.subtotal.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Markup</span>
                  <span>£{calcResult.markup_amount.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">VAT</span>
                  <span>£{calcResult.vat_amount.toFixed(2)}</span>
                </div>
                <div className="border-t pt-2 flex justify-between font-semibold text-lg">
                  <span>Total</span>
                  <span className="text-primary">{calcTotal(calcResult)}</span>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
