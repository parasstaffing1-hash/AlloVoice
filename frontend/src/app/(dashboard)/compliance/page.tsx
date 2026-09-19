"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Shield,
  AlertTriangle,
  FileText,
  Download,
  Calendar,
  CheckCircle2,
  Clock,
  Plus,
  RefreshCw,
  Filter,
  ChevronDown,
  ChevronUp,
  Loader2,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface FGasCertificate {
  id: string;
  certificate_number: string;
  customer_id: string;
  property_address: string;
  equipment_type: string;
  equipment_location: string;
  make_model: string;
  serial_number: string;
  gas_type: string;
  leak_check_result: string;
  leak_check_method: string;
  quantity_kg: number;
  next_leak_check_date: string;
  engineer_name: string;
  notes: string | null;
  status: string;
  created_at: string;
  original_id: string | null;
}

interface SafetyTestResult {
  appliance: string;
  test_result: string;
  defect_found: string;
  action_required: string;
}

interface GasSafetyCertificate {
  id: string;
  certificate_number: string;
  customer_id: string;
  property_address: string;
  property_type: string;
  boiler_make: string;
  boiler_model: string;
  boiler_type: string;
  boiler_location: string;
  flue_type: string;
  gas_supply_condition: string;
  ventilation_condition: string;
  safety_test_results: SafetyTestResult[];
  gas_safe_registered_number: string;
  next_check_date: string;
  status: string;
  created_at: string;
}

const API_BASE = "/api/compliance";

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { color: string; label: string; icon: React.ReactNode }> = {
    valid: {
      color: "bg-emerald-100 text-emerald-800 border-emerald-200",
      label: "Valid",
      icon: <CheckCircle2 className="w-3 h-3" />,
    },
    expiring_soon: {
      color: "bg-amber-100 text-amber-800 border-amber-200",
      label: "Expiring Soon",
      icon: <Clock className="w-3 h-3" />,
    },
    warning: {
      color: "bg-orange-100 text-orange-800 border-orange-200",
      label: "Warning",
      icon: <AlertTriangle className="w-3 h-3" />,
    },
    expired: {
      color: "bg-red-100 text-red-800 border-red-200",
      label: "Expired",
      icon: <AlertTriangle className="w-3 h-3" />,
    },
  };
  const c = config[status] || config.valid;
  return (
    <Badge variant="outline" className={`${c.color} flex items-center gap-1`}>
      {c.icon}
      {c.label}
    </Badge>
  );
}

export default function ComplianceDashboard() {
  const [activeTab, setActiveTab] = useState("overview");
  const [fgasCerts, setFGasCerts] = useState<FGasCertificate[]>([]);
  const [gasSafetyCerts, setGasSafetyCerts] = useState<GasSafetyCertificate[]>([]);
  const [expiringFGas, setExpiringFGas] = useState<FGasCertificate[]>([]);
  const [expiringGas, setExpiringGas] = useState<GasSafetyCertificate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showFGasForm, setShowFGasForm] = useState(false);
  const [showGasForm, setShowGasForm] = useState(false);

  const [fgasForm, setFGasForm] = useState({
    customer_id: "",
    job_id: "",
    property_address: "",
    equipment_type: "split_system",
    equipment_location: "",
    make_model: "",
    serial_number: "",
    gas_type: "R32",
    leak_check_result: "pass",
    leak_check_method: "electronic",
    quantity_kg: "",
    next_leak_check_date: "",
    engineer_name: "",
    engineer_signature_url: "",
    notes: "",
  });

  const [gasForm, setGasForm] = useState({
    customer_id: "",
    property_address: "",
    property_type: "domestic",
    boiler_make: "",
    boiler_model: "",
    boiler_type: "combi",
    boiler_location: "",
    flue_type: "balanced",
    gas_supply_condition: "satisfactory",
    ventilation_condition: "satisfactory",
    safety_test_results: [{ appliance: "", test_result: "pass", defect_found: "No", action_required: "" }],
    gas_safe_registered_number: "",
    next_check_date: "",
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [fgasList, gasList, fgasExp, gasExp] = await Promise.all([
        fetch(`${API_BASE}/fgas/list`).then((r) => r.json()),
        fetch(`${API_BASE}/gas-safety/list`).then((r) => r.json()),
        fetch(`${API_BASE}/fgas/expiring`).then((r) => r.json()),
        fetch(`${API_BASE}/gas-safety/expiring`).then((r) => r.json()),
      ]);
      setFGasCerts(fgasList);
      setGasSafetyCerts(gasList);
      setExpiringFGas(fgasExp);
      setExpiringGas(gasExp);
    } catch (err) {
      console.error("Failed to fetch compliance data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleFGasSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/fgas/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...fgasForm,
          quantity_kg: parseFloat(fgasForm.quantity_kg),
        }),
      });
      if (res.ok) {
        setShowFGasForm(false);
        fetchData();
      }
    } catch (err) {
      console.error("Failed to create F-Gas certificate:", err);
    }
  };

  const handleGasSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/gas-safety/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(gasForm),
      });
      if (res.ok) {
        setShowGasForm(false);
        fetchData();
      }
    } catch (err) {
      console.error("Failed to create Gas Safety certificate:", err);
    }
  };

  const handleDownloadPDF = async (certId: string) => {
    try {
      const res = await fetch(`${API_BASE}/gas-safety/generate-pdf?cert_id=${certId}`, {
        method: "POST",
      });
      const data = await res.json();
      const byteChars = atob(data.pdf_base64);
      const byteArray = new Uint8Array(byteChars.length);
      for (let i = 0; i < byteChars.length; i++) {
        byteArray[i] = byteChars.charCodeAt(i);
      }
      const blob = new Blob([byteArray], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to download PDF:", err);
    }
  };

  const totalCerts = fgasCerts.length + gasSafetyCerts.length;
  const totalExpiring = expiringFGas.length + expiringGas.length;
  const totalExpired =
    fgasCerts.filter((c) => c.status === "expired").length +
    gasSafetyCerts.filter((c) => c.status === "expired").length;

  const addTestResult = () => {
    setGasForm({
      ...gasForm,
      safety_test_results: [
        ...gasForm.safety_test_results,
        { appliance: "", test_result: "pass", defect_found: "No", action_required: "" },
      ],
    });
  };

  const updateTestResult = (index: number, field: string, value: string) => {
    const updated = [...gasForm.safety_test_results];
    updated[index] = { ...updated[index], [field]: value };
    setGasForm({ ...gasForm, safety_test_results: updated });
  };

  const removeTestResult = (index: number) => {
    setGasForm({
      ...gasForm,
      safety_test_results: gasForm.safety_test_results.filter((_, i) => i !== index),
    });
  };

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <Shield className="w-6 h-6 text-blue-600" />
              Compliance Certificates
            </h1>
            <p className="text-slate-500 mt-1">
              UK F-Gas & Gas Safety (CP12) compliance management
            </p>
          </div>
          <Button variant="outline" onClick={fetchData} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="overview" className="flex items-center gap-2">
              <FileText className="w-4 h-4" />
              Overview
            </TabsTrigger>
            <TabsTrigger value="fgas" className="flex items-center gap-2">
              <Shield className="w-4 h-4" />
              F-Gas
            </TabsTrigger>
            <TabsTrigger value="gas-safety" className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4" />
              Gas Safety (CP12)
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-slate-500">Total Certificates</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold">{totalCerts}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-slate-500">F-Gas Certificates</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold text-blue-600">{fgasCerts.length}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-amber-600 flex items-center gap-1">
                    <Clock className="w-4 h-4" /> Expiring Soon
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold text-amber-600">{totalExpiring}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium text-red-600 flex items-center gap-1">
                    <AlertTriangle className="w-4 h-4" /> Overdue
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold text-red-600">{totalExpired}</div>
                </CardContent>
              </Card>
            </div>

            {expiringFGas.length > 0 && (
              <Card className="border-amber-200 bg-amber-50">
                <CardHeader>
                  <CardTitle className="text-amber-800 flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5" />
                    F-Gas Certificates Expiring Within 30 Days
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {expiringFGas.map((cert) => (
                      <div key={cert.id} className="flex items-center justify-between p-2 bg-white rounded border border-amber-100">
                        <div>
                          <span className="font-mono text-sm">{cert.certificate_number}</span>
                          <span className="text-slate-500 ml-2">{cert.property_address}</span>
                        </div>
                        <StatusBadge status={cert.status} />
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {expiringGas.length > 0 && (
              <Card className="border-amber-200 bg-amber-50">
                <CardHeader>
                  <CardTitle className="text-amber-800 flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5" />
                    Gas Safety Certificates Expiring Within 12 Months
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {expiringGas.map((cert) => (
                      <div key={cert.id} className="flex items-center justify-between p-2 bg-white rounded border border-amber-100">
                        <div>
                          <span className="font-mono text-sm">{cert.certificate_number}</span>
                          <span className="text-slate-500 ml-2">{cert.property_address}</span>
                        </div>
                        <StatusBadge status={cert.status} />
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {totalCerts === 0 && !loading && (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-12">
                  <Shield className="w-12 h-12 text-slate-300 mb-4" />
                  <p className="text-slate-500">No compliance certificates yet</p>
                  <p className="text-sm text-slate-400">Create your first F-Gas or Gas Safety certificate</p>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* F-Gas Tab */}
          <TabsContent value="fgas" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold">F-Gas Certificates</h2>
              <Dialog open={showFGasForm} onOpenChange={setShowFGasForm}>
                <DialogTrigger asChild>
                  <Button>
                    <Plus className="w-4 h-4 mr-2" />
                    New F-Gas Certificate
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle>Create F-Gas Certificate</DialogTitle>
                    <DialogDescription>
                      Record a fluorinated greenhouse gas leak check per UK F-Gas regulations
                    </DialogDescription>
                  </DialogHeader>
                  <form onSubmit={handleFGasSubmit} className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label>Customer ID</Label>
                        <Input
                          value={fgasForm.customer_id}
                          onChange={(e) => setFGasForm({ ...fgasForm, customer_id: e.target.value })}
                          required
                        />
                      </div>
                      <div>
                        <Label>Job ID</Label>
                        <Input
                          value={fgasForm.job_id}
                          onChange={(e) => setFGasForm({ ...fgasForm, job_id: e.target.value })}
                        />
                      </div>
                    </div>
                    <div>
                      <Label>Property Address</Label>
                      <Input
                        value={fgasForm.property_address}
                        onChange={(e) => setFGasForm({ ...fgasForm, property_address: e.target.value })}
                        required
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label>Equipment Type</Label>
                        <Select
                          value={fgasForm.equipment_type}
                          onValueChange={(v) => setFGasForm({ ...fgasForm, equipment_type: v })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="split_system">Split System</SelectItem>
                            <SelectItem value="multi_split">Multi Split</SelectItem>
                            <SelectItem value="vrf">VRF</SelectItem>
                            <SelectItem value="heat_pump">Heat Pump</SelectItem>
                            <SelectItem value="refrigeration">Refrigeration</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label>Gas Type</Label>
                        <Select
                          value={fgasForm.gas_type}
                          onValueChange={(v) => setFGasForm({ ...fgasForm, gas_type: v })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="R32">R32</SelectItem>
                            <SelectItem value="R410A">R410A</SelectItem>
                            <SelectItem value="R407C">R407C</SelectItem>
                            <SelectItem value="R134A">R134A</SelectItem>
                            <SelectItem value="R290">R290</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div>
                      <Label>Equipment Location</Label>
                      <Input
                        value={fgasForm.equipment_location}
                        onChange={(e) => setFGasForm({ ...fgasForm, equipment_location: e.target.value })}
                        required
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label>Make & Model</Label>
                        <Input
                          value={fgasForm.make_model}
                          onChange={(e) => setFGasForm({ ...fgasForm, make_model: e.target.value })}
                          required
                        />
                      </div>
                      <div>
                        <Label>Serial Number</Label>
                        <Input
                          value={fgasForm.serial_number}
                          onChange={(e) => setFGasForm({ ...fgasForm, serial_number: e.target.value })}
                          required
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <Label>Leak Check Result</Label>
                        <Select
                          value={fgasForm.leak_check_result}
                          onValueChange={(v) => setFGasForm({ ...fgasForm, leak_check_result: v })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="pass">Pass</SelectItem>
                            <SelectItem value="fail">Fail</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label>Leak Check Method</Label>
                        <Select
                          value={fgasForm.leak_check_method}
                          onValueChange={(v) => setFGasForm({ ...fgasForm, leak_check_method: v })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="electronic">Electronic</SelectItem>
                            <SelectItem value="visual">Visual</SelectItem>
                            <SelectItem value="bubble">Bubble</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label>Quantity (kg)</Label>
                        <Input
                          type="number"
                          step="0.01"
                          value={fgasForm.quantity_kg}
                          onChange={(e) => setFGasForm({ ...fgasForm, quantity_kg: e.target.value })}
                          required
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label>Next Leak Check Date</Label>
                        <Input
                          type="date"
                          value={fgasForm.next_leak_check_date}
                          onChange={(e) => setFGasForm({ ...fgasForm, next_leak_check_date: e.target.value })}
                          required
                        />
                      </div>
                      <div>
                        <Label>Engineer Name</Label>
                        <Input
                          value={fgasForm.engineer_name}
                          onChange={(e) => setFGasForm({ ...fgasForm, engineer_name: e.target.value })}
                          required
                        />
                      </div>
                    </div>
                    <div>
                      <Label>Notes</Label>
                      <Textarea
                        value={fgasForm.notes}
                        onChange={(e) => setFGasForm({ ...fgasForm, notes: e.target.value })}
                        rows={3}
                      />
                    </div>
                    <div className="flex justify-end gap-2">
                      <Button type="button" variant="outline" onClick={() => setShowFGasForm(false)}>
                        Cancel
                      </Button>
                      <Button type="submit">Create Certificate</Button>
                    </div>
                  </form>
                </DialogContent>
              </Dialog>
            </div>

            <Card>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-slate-50">
                        <th className="text-left p-3 font-medium text-slate-600">Certificate #</th>
                        <th className="text-left p-3 font-medium text-slate-600">Property</th>
                        <th className="text-left p-3 font-medium text-slate-600">Equipment</th>
                        <th className="text-left p-3 font-medium text-slate-600">Gas</th>
                        <th className="text-left p-3 font-medium text-slate-600">Leak Check</th>
                        <th className="text-left p-3 font-medium text-slate-600">Next Check</th>
                        <th className="text-left p-3 font-medium text-slate-600">Status</th>
                        <th className="text-left p-3 font-medium text-slate-600">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fgasCerts.map((cert) => (
                        <tr key={cert.id} className="border-b hover:bg-slate-50">
                          <td className="p-3 font-mono text-xs">{cert.certificate_number}</td>
                          <td className="p-3 max-w-[200px] truncate">{cert.property_address}</td>
                          <td className="p-3">{cert.equipment_type.replace("_", " ")}</td>
                          <td className="p-3">{cert.gas_type}</td>
                          <td className="p-3">
                            <Badge variant={cert.leak_check_result === "pass" ? "default" : "destructive"}>
                              {cert.leak_check_result.toUpperCase()}
                            </Badge>
                          </td>
                          <td className="p-3">{cert.next_leak_check_date}</td>
                          <td className="p-3">
                            <StatusBadge status={cert.status} />
                          </td>
                          <td className="p-3">
                            <Button variant="ghost" size="sm">
                              <Download className="w-4 h-4" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                      {fgasCerts.length === 0 && (
                        <tr>
                          <td colSpan={8} className="p-8 text-center text-slate-400">
                            No F-Gas certificates found
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Gas Safety Tab */}
          <TabsContent value="gas-safety" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold">Gas Safety Certificates (CP12)</h2>
              <Dialog open={showGasForm} onOpenChange={setShowGasForm}>
                <DialogTrigger asChild>
                  <Button>
                    <Plus className="w-4 h-4 mr-2" />
                    New CP12 Certificate
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle>Create Gas Safety Certificate (CP12)</DialogTitle>
                    <DialogDescription>
                      Record a gas safety inspection per UK Gas Safety regulations
                    </DialogDescription>
                  </DialogHeader>
                  <form onSubmit={handleGasSubmit} className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label>Customer ID</Label>
                        <Input
                          value={gasForm.customer_id}
                          onChange={(e) => setGasForm({ ...gasForm, customer_id: e.target.value })}
                          required
                        />
                      </div>
                      <div>
                        <Label>Property Type</Label>
                        <Select
                          value={gasForm.property_type}
                          onValueChange={(v) => setGasForm({ ...gasForm, property_type: v })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="domestic">Domestic</SelectItem>
                            <SelectItem value="commercial">Commercial</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div>
                      <Label>Property Address</Label>
                      <Input
                        value={gasForm.property_address}
                        onChange={(e) => setGasForm({ ...gasForm, property_address: e.target.value })}
                        required
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label>Boiler Make</Label>
                        <Input
                          value={gasForm.boiler_make}
                          onChange={(e) => setGasForm({ ...gasForm, boiler_make: e.target.value })}
                          required
                        />
                      </div>
                      <div>
                        <Label>Boiler Model</Label>
                        <Input
                          value={gasForm.boiler_model}
                          onChange={(e) => setGasForm({ ...gasForm, boiler_model: e.target.value })}
                          required
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <Label>Boiler Type</Label>
                        <Select
                          value={gasForm.boiler_type}
                          onValueChange={(v) => setGasForm({ ...gasForm, boiler_type: v })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="combi">Combi</SelectItem>
                            <SelectItem value="system">System</SelectItem>
                            <SelectItem value="regular">Regular</SelectItem>
                            <SelectItem value="back_boiler">Back Boiler</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label>Flue Type</Label>
                        <Select
                          value={gasForm.flue_type}
                          onValueChange={(v) => setGasForm({ ...gasForm, flue_type: v })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="balanced">Balanced</SelectItem>
                            <SelectItem value="open">Open</SelectItem>
                            <SelectItem value="room_sealed">Room Sealed</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label>Boiler Location</Label>
                        <Input
                          value={gasForm.boiler_location}
                          onChange={(e) => setGasForm({ ...gasForm, boiler_location: e.target.value })}
                          required
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <Label>Gas Supply</Label>
                        <Select
                          value={gasForm.gas_supply_condition}
                          onValueChange={(v) => setGasForm({ ...gasForm, gas_supply_condition: v })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="satisfactory">Satisfactory</SelectItem>
                            <SelectItem value="unsatisfactory">Unsatisfactory</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label>Ventilation</Label>
                        <Select
                          value={gasForm.ventilation_condition}
                          onValueChange={(v) => setGasForm({ ...gasForm, ventilation_condition: v })}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="satisfactory">Satisfactory</SelectItem>
                            <SelectItem value="unsatisfactory">Unsatisfactory</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label>Gas Safe Reg No.</Label>
                        <Input
                          value={gasForm.gas_safe_registered_number}
                          onChange={(e) =>
                            setGasForm({ ...gasForm, gas_safe_registered_number: e.target.value })
                          }
                          required
                        />
                      </div>
                    </div>
                    <div>
                      <Label>Next Check Date</Label>
                      <Input
                        type="date"
                        value={gasForm.next_check_date}
                        onChange={(e) => setGasForm({ ...gasForm, next_check_date: e.target.value })}
                        required
                      />
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <Label>Appliance Test Results</Label>
                        <Button type="button" variant="outline" size="sm" onClick={addTestResult}>
                          <Plus className="w-3 h-3 mr-1" /> Add Appliance
                        </Button>
                      </div>
                      <div className="space-y-3">
                        {gasForm.safety_test_results.map((test, i) => (
                          <div key={i} className="grid grid-cols-4 gap-2 p-3 bg-slate-50 rounded-lg relative">
                            <Input
                              placeholder="Appliance"
                              value={test.appliance}
                              onChange={(e) => updateTestResult(i, "appliance", e.target.value)}
                            />
                            <Select
                              value={test.test_result}
                              onValueChange={(v) => updateTestResult(i, "test_result", v)}
                            >
                              <SelectTrigger>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="pass">Pass</SelectItem>
                                <SelectItem value="fail">Fail</SelectItem>
                              </SelectContent>
                            </Select>
                            <Input
                              placeholder="Defect found"
                              value={test.defect_found}
                              onChange={(e) => updateTestResult(i, "defect_found", e.target.value)}
                            />
                            <div className="flex gap-1">
                              <Input
                                placeholder="Action required"
                                value={test.action_required}
                                onChange={(e) => updateTestResult(i, "action_required", e.target.value)}
                                className="flex-1"
                              />
                              {gasForm.safety_test_results.length > 1 && (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => removeTestResult(i)}
                                  className="text-red-500"
                                >
                                  ×
                                </Button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="flex justify-end gap-2">
                      <Button type="button" variant="outline" onClick={() => setShowGasForm(false)}>
                        Cancel
                      </Button>
                      <Button type="submit">Create Certificate</Button>
                    </div>
                  </form>
                </DialogContent>
              </Dialog>
            </div>

            <Card>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-slate-50">
                        <th className="text-left p-3 font-medium text-slate-600">Certificate #</th>
                        <th className="text-left p-3 font-medium text-slate-600">Property</th>
                        <th className="text-left p-3 font-medium text-slate-600">Boiler</th>
                        <th className="text-left p-3 font-medium text-slate-600">Gas Supply</th>
                        <th className="text-left p-3 font-medium text-slate-600">Ventilation</th>
                        <th className="text-left p-3 font-medium text-slate-600">Next Check</th>
                        <th className="text-left p-3 font-medium text-slate-600">Status</th>
                        <th className="text-left p-3 font-medium text-slate-600">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {gasSafetyCerts.map((cert) => (
                        <tr key={cert.id} className="border-b hover:bg-slate-50">
                          <td className="p-3 font-mono text-xs">{cert.certificate_number}</td>
                          <td className="p-3 max-w-[200px] truncate">{cert.property_address}</td>
                          <td className="p-3">
                            {cert.boiler_make} {cert.boiler_model}
                          </td>
                          <td className="p-3">
                            <Badge
                              variant={
                                cert.gas_supply_condition === "satisfactory" ? "default" : "destructive"
                              }
                            >
                              {cert.gas_supply_condition}
                            </Badge>
                          </td>
                          <td className="p-3">
                            <Badge
                              variant={
                                cert.ventilation_condition === "satisfactory" ? "default" : "destructive"
                              }
                            >
                              {cert.ventilation_condition}
                            </Badge>
                          </td>
                          <td className="p-3">{cert.next_check_date}</td>
                          <td className="p-3">
                            <StatusBadge status={cert.status} />
                          </td>
                          <td className="p-3">
                            <Button variant="ghost" size="sm" onClick={() => handleDownloadPDF(cert.id)}>
                              <Download className="w-4 h-4" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                      {gasSafetyCerts.length === 0 && (
                        <tr>
                          <td colSpan={8} className="p-8 text-center text-slate-400">
                            No Gas Safety certificates found
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
