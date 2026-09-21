"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  Palette,
  ImagePlus,
  Eye,
  RotateCcw,
  Save,
  Globe,
  Type,
} from "lucide-react";

type BrandTab = "brand" | "colours" | "logo";

const FONT_OPTIONS = ["Inter", "System", "Georgia"];

const HEX_RE = /^#([0-9a-fA-F]{6})$/;

const DEFAULT_KIT = {
  brand_name: "Allo",
  logo_url: "",
  primary_color: "#4f46e5",
  secondary_color: "#0f172a",
  accent_color: "#22c55e",
  font_family: "Inter",
  email_footer: "Thanks,\nThe Allo Team",
  portal_subdomain: "",
  custom_domain: "",
  favicon_url: "",
  powered_by_visible: true,
};

export default function BrandingPage() {
  const { token } = useAuth();
  const [tab, setTab] = useState<BrandTab>("brand");
  const [kit, setKit] = useState<any>({ ...DEFAULT_KIT });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [colorErrors, setColorErrors] = useState<Record<string, string>>({});
  const [uploading, setUploading] = useState(false);
  const [previewFile, setPreviewFile] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const loadKit = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError("");
    api.branding
      .get(token)
      .then((r: any) => {
        const k = r.brand_kit || r.kit || r;
        setKit({ ...DEFAULT_KIT, ...k });
      })
      .catch((e: any) => setError(e?.message || "Failed to load brand kit"))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    loadKit();
  }, [token, loadKit]);

  const set = (field: string, value: any) => {
    setKit((prev: any) => ({ ...prev, [field]: value }));
    setMsg("");
  };

  const validateColors = () => {
    const errs: Record<string, string> = {};
    (["primary_color", "secondary_color", "accent_color"] as const).forEach((f) => {
      if (!HEX_RE.test(kit[f] || "")) errs[f] = "Must be a valid hex colour, e.g. #4f46e5";
    });
    setColorErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSave = (fields?: Record<string, any>) => {
    if (!token) return;
    if (tab === "colours" && !validateColors()) return;
    setSaving(true);
    setMsg("");
    setError("");
    const data = fields || kit;
    api.branding
      .update(data, token)
      .then((r: any) => {
        const k = r.brand_kit || r.kit || r;
        if (k && typeof k === "object") setKit((prev: any) => ({ ...prev, ...k }));
        setMsg("Brand kit saved.");
      })
      .catch((e: any) => setError(e?.message || "Failed to save brand kit"))
      .finally(() => setSaving(false));
  };

  const handleSaveColors = () => {
    if (!validateColors()) return;
    handleSave({
      primary_color: kit.primary_color,
      secondary_color: kit.secondary_color,
      accent_color: kit.accent_color,
    });
  };

  const handleReset = () => {
    if (!token) return;
    if (!window.confirm("Reset brand kit to defaults?")) return;
    setSaving(true);
    setMsg("");
    setError("");
    api.branding
      .reset(token)
      .then((r: any) => {
        const k = r.brand_kit || r.kit || r;
        setKit({ ...DEFAULT_KIT, ...(k || {}) });
        setMsg("Brand kit reset to defaults.");
      })
      .catch((e: any) => setError(e?.message || "Failed to reset brand kit"))
      .finally(() => setSaving(false));
  };

  const handleFile = (file: File | undefined) => {
    if (!file || !token) return;
    setError("");
    setMsg("");
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      setPreviewFile(dataUrl);
      const base64 = dataUrl.includes(",") ? dataUrl.split(",")[1] : dataUrl;
      setUploading(true);
      api.branding
        .uploadLogo(base64, file.name, token)
        .then((r: any) => {
          const url = r.logo_url || r.url || dataUrl;
          set("logo_url", url);
          setMsg("Logo uploaded.");
        })
        .catch((e: any) => setError(e?.message || "Logo upload failed"))
        .finally(() => setUploading(false));
    };
    reader.onerror = () => setError("Could not read file.");
    reader.readAsDataURL(file);
  };

  const fontStack =
    kit.font_family === "Georgia"
      ? "Georgia, serif"
      : kit.font_family === "System"
        ? "system-ui, sans-serif"
        : "Inter, system-ui, sans-serif";

  const tabs: { id: BrandTab; label: string }[] = [
    { id: "brand", label: "Brand" },
    { id: "colours", label: "Colours" },
    { id: "logo", label: "Logo" },
  ];

  const colorFields = [
    { key: "primary_color", label: "Primary" },
    { key: "secondary_color", label: "Secondary" },
    { key: "accent_color", label: "Accent" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Palette className="h-8 w-8 text-violet-400" />
            Brand Kit
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            White-label your customer portal, emails and invoices
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="gap-2" onClick={handleReset} disabled={saving}>
            <RotateCcw className="h-4 w-4" /> Reset
          </Button>
          <Button className="gap-2" onClick={() => handleSave()} disabled={saving}>
            <Save className="h-4 w-4" /> {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      {error && (
        <p className="text-sm text-red-400 rounded-lg border border-red-500/40 bg-red-950/40 p-3">
          {error}
        </p>
      )}
      {msg && (
        <p className="text-sm text-green-400 rounded-lg border border-green-500/40 bg-green-950/30 p-3">
          {msg}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          <div className="flex gap-2 border-b border-zinc-800 pb-2">
            {tabs.map((t) => (
              <Button
                key={t.id}
                variant={tab === t.id ? "default" : "ghost"}
                size="sm"
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </Button>
            ))}
          </div>

          {loading ? (
            <p className="text-sm text-muted-foreground">Loading brand kit…</p>
          ) : (
            <>
              {tab === "brand" && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Type className="h-5 w-5" /> Brand Details
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <label className="text-sm font-medium">Brand name</label>
                      <Input
                        className="mt-1"
                        value={kit.brand_name || ""}
                        onChange={(e) => set("brand_name", e.target.value)}
                        placeholder="Acme Heating Ltd"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="text-sm font-medium flex items-center gap-1">
                          <Globe className="h-3 w-3" /> Portal subdomain
                        </label>
                        <Input
                          className="mt-1"
                          value={kit.portal_subdomain || ""}
                          onChange={(e) => set("portal_subdomain", e.target.value)}
                          placeholder="acme"
                        />
                        <p className="text-xs text-muted-foreground mt-1">
                          {(kit.portal_subdomain || "your-brand")}.voicefield.co.uk
                        </p>
                      </div>
                      <div>
                        <label className="text-sm font-medium flex items-center gap-1">
                          <Globe className="h-3 w-3" /> Custom domain
                        </label>
                        <Input
                          className="mt-1"
                          value={kit.custom_domain || ""}
                          onChange={(e) => set("custom_domain", e.target.value)}
                          placeholder="portal.acme.co.uk"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-sm font-medium">Font family</label>
                      <select
                        className="mt-1 flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                        value={kit.font_family || "Inter"}
                        onChange={(e) => set("font_family", e.target.value)}
                      >
                        {FONT_OPTIONS.map((f) => (
                          <option key={f} value={f}>
                            {f}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-sm font-medium">Email footer</label>
                      <textarea
                        className="mt-1 flex min-h-[90px] w-full rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        value={kit.email_footer || ""}
                        onChange={(e) => set("email_footer", e.target.value)}
                        placeholder={"Thanks,\nThe team at …"}
                      />
                    </div>
                    <label className="flex items-center justify-between rounded-lg border border-zinc-800 p-3 text-sm cursor-pointer">
                      <span>
                        <span className="font-medium">“Powered by” badge</span>
                        <span className="block text-xs text-muted-foreground">
                          Show “Powered by Allo” on your portal
                        </span>
                      </span>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={Boolean(kit.powered_by_visible)}
                        onClick={() => set("powered_by_visible", !kit.powered_by_visible)}
                        className={`relative h-6 w-11 rounded-full transition-colors ${kit.powered_by_visible ? "bg-green-500" : "bg-zinc-700"}`}
                      >
                        <span
                          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${kit.powered_by_visible ? "left-[22px]" : "left-0.5"}`}
                        />
                      </button>
                    </label>
                    <Button className="gap-2" onClick={() => handleSave()} disabled={saving}>
                      <Save className="h-4 w-4" /> {saving ? "Saving…" : "Save Brand"}
                    </Button>
                  </CardContent>
                </Card>
              )}

              {tab === "colours" && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Palette className="h-5 w-5" /> Colours
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {colorFields.map((f) => (
                      <div key={f.key} className="flex items-center gap-3">
                        <input
                          type="color"
                          value={HEX_RE.test(kit[f.key] || "") ? kit[f.key] : "#000000"}
                          onChange={(e) => {
                            set(f.key, e.target.value);
                            setColorErrors((prev) => ({ ...prev, [f.key]: "" }));
                          }}
                          className="h-10 w-14 cursor-pointer rounded-lg border border-zinc-700 bg-transparent"
                          aria-label={`${f.label} colour picker`}
                        />
                        <div className="flex-1">
                          <label className="text-sm font-medium">{f.label}</label>
                          <Input
                            className="mt-1 font-mono"
                            value={kit[f.key] || ""}
                            onChange={(e) => {
                              set(f.key, e.target.value);
                              setColorErrors((prev) => ({ ...prev, [f.key]: "" }));
                            }}
                            placeholder="#000000"
                            maxLength={7}
                          />
                          {colorErrors[f.key] && (
                            <p className="text-xs text-red-400 mt-1">{colorErrors[f.key]}</p>
                          )}
                        </div>
                        <div
                          className="h-10 w-10 rounded-lg border border-zinc-700"
                          style={{ backgroundColor: kit[f.key] }}
                        />
                      </div>
                    ))}
                    <div className="flex items-center gap-3 rounded-lg border border-zinc-800 p-3">
                      {[kit.primary_color, kit.secondary_color, kit.accent_color].map(
                        (c: string, i: number) => (
                          <div key={i} className="flex-1">
                            <div
                              className="h-12 rounded-lg"
                              style={{ backgroundColor: c }}
                            />
                            <p className="text-xs font-mono text-muted-foreground mt-1 text-center">
                              {c}
                            </p>
                          </div>
                        )
                      )}
                    </div>
                    <Button className="gap-2" onClick={handleSaveColors} disabled={saving}>
                      <Save className="h-4 w-4" /> {saving ? "Saving…" : "Save Colours"}
                    </Button>
                  </CardContent>
                </Card>
              )}

              {tab === "logo" && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <ImagePlus className="h-5 w-5" /> Logo
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <input
                      ref={fileRef}
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => handleFile(e.target.files?.[0])}
                    />
                    <Button
                      variant="outline"
                      className="gap-2"
                      onClick={() => fileRef.current?.click()}
                      disabled={uploading}
                    >
                      <ImagePlus className="h-4 w-4" />
                      {uploading ? "Uploading…" : "Upload logo"}
                    </Button>
                    {(previewFile || kit.logo_url) && (
                      <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
                        <p className="text-xs text-muted-foreground mb-2">Current logo</p>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={previewFile || kit.logo_url}
                          alt="Brand logo"
                          className="max-h-24 object-contain"
                        />
                      </div>
                    )}
                    <div>
                      <label className="text-sm font-medium">Logo URL</label>
                      <Input
                        className="mt-1 font-mono text-xs"
                        value={kit.logo_url || ""}
                        onChange={(e) => set("logo_url", e.target.value)}
                        placeholder="https://…"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Favicon URL</label>
                      <Input
                        className="mt-1 font-mono text-xs"
                        value={kit.favicon_url || ""}
                        onChange={(e) => set("favicon_url", e.target.value)}
                        placeholder="https://…/favicon.ico"
                      />
                    </div>
                    <Button className="gap-2" onClick={() => handleSave()} disabled={saving}>
                      <Save className="h-4 w-4" /> {saving ? "Saving…" : "Save Logo"}
                    </Button>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>

        {/* Live preview */}
        <div className="space-y-4">
          <Card className="sticky top-4">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Eye className="h-5 w-5" /> Live Preview
                <Badge className="ml-auto bg-green-500/20 text-green-400">live</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Mock customer portal */}
              <div
                className="overflow-hidden rounded-xl border border-zinc-800"
                style={{ fontFamily: fontStack }}
              >
                <div
                  className="flex items-center gap-2 px-4 py-3"
                  style={{ backgroundColor: kit.secondary_color || "#0f172a" }}
                >
                  {kit.logo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={kit.logo_url} alt="logo" className="h-7 w-7 object-contain rounded" />
                  ) : (
                    <div
                      className="flex h-7 w-7 items-center justify-center rounded text-xs font-bold text-white"
                      style={{ backgroundColor: kit.primary_color }}
                    >
                      {(kit.brand_name || "A").charAt(0).toUpperCase()}
                    </div>
                  )}
                  <span className="font-semibold text-white text-sm">
                    {kit.brand_name || "Your Brand"}
                  </span>
                  <span className="ml-auto text-[11px] text-white/60">
                    {(kit.portal_subdomain || "your-brand")}.voicefield.co.uk
                  </span>
                </div>
                <div className="bg-zinc-950 px-4 py-4 space-y-3">
                  <p className="text-sm font-medium text-zinc-100">
                    Welcome back — book your next visit
                  </p>
                  <div className="flex gap-2">
                    <button
                      className="rounded-lg px-4 py-2 text-sm font-medium text-white"
                      style={{ backgroundColor: kit.primary_color }}
                    >
                      Book a job
                    </button>
                    <button
                      className="rounded-lg px-4 py-2 text-sm font-medium text-white border"
                      style={{
                        borderColor: kit.accent_color,
                        color: kit.accent_color,
                      }}
                    >
                      Pay invoice
                    </button>
                  </div>
                  <div
                    className="rounded-lg p-3 text-xs"
                    style={{
                      backgroundColor: `${kit.accent_color || "#22c55e"}1a`,
                      border: `1px solid ${kit.accent_color || "#22c55e"}55`,
                      color: kit.accent_color || "#22c55e",
                    }}
                  >
                    Your engineer arrives tomorrow, 9:00–11:00.
                  </div>
                </div>
              </div>

              {/* Mock email */}
              <div
                className="rounded-xl border border-zinc-800 bg-zinc-950 p-4"
                style={{ fontFamily: fontStack }}
              >
                <div
                  className="h-1.5 rounded-full mb-3"
                  style={{ backgroundColor: kit.primary_color }}
                />
                <p className="text-sm font-medium">Invoice #INV-2041 is ready</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Hi Sarah — thanks for choosing {kit.brand_name || "us"}.
                </p>
                <div
                  className="mt-3 border-t border-zinc-800 pt-2 text-[11px] text-muted-foreground whitespace-pre-line"
                >
                  {kit.email_footer || "—"}
                </div>
              </div>

              {kit.powered_by_visible && (
                <p className="text-center text-[11px] text-muted-foreground">
                  Powered by Allo
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
