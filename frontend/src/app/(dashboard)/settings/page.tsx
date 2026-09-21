"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import {
  SUPPORTED_CURRENCIES,
  TAX_NAMES,
  COUNTRIES,
  TIMEZONES,
  LOCALE_DEFAULTS,
  getStoredLocale,
  storeLocale,
} from "@/lib/money";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSeparator,
  InputOTPSlot,
} from "@/components/ui/input-otp";
import {
  Settings, CreditCard, Link2, Shield, Bell, Users, Building,
  Globe, Key, CheckCircle2, AlertCircle, ExternalLink,
} from "lucide-react";

export default function SettingsPage() {
  const { token } = useAuth();
  const [activeTab, setActiveTab] = useState("general");
  const [xeroStatus, setXeroStatus] = useState<any>(null);
  const [calendarStatus, setCalendarStatus] = useState<any>(null);
  const [mfaStatus, setMfaStatus] = useState<any>(null);
  const [mfaSetup, setMfaSetup] = useState<any>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [mfaLoading, setMfaLoading] = useState(false);
  const [mfaMessage, setMfaMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [business, setBusiness] = useState<any>(null);
  const [currency, setCurrency] = useState(LOCALE_DEFAULTS.currency);
  const [country, setCountry] = useState(LOCALE_DEFAULTS.country);
  const [timezone, setTimezone] = useState(LOCALE_DEFAULTS.timezone);
  const [taxName, setTaxName] = useState(LOCALE_DEFAULTS.taxName);
  const [taxRate, setTaxRate] = useState<number>(LOCALE_DEFAULTS.taxRate);
  const [localeSaving, setLocaleSaving] = useState(false);
  const [localeMessage, setLocaleMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    if (!token) return;
    api.xero.status(token).then((r: any) => setXeroStatus(r)).catch(() => {});
    api.calendar.status(token).then((r: any) => setCalendarStatus(r)).catch(() => {});
    api.mfa.status(token).then((r: any) => setMfaStatus(r)).catch(() => {});
    api.auth.getBusiness(token)
      .then((r: any) => {
        setBusiness(r);
        const stored = getStoredLocale();
        if (typeof r?.currency === "string" && r.currency) setCurrency(r.currency);
        else if (typeof stored.currency === "string" && stored.currency) setCurrency(stored.currency);
        if (typeof r?.country === "string" && r.country) setCountry(r.country);
        else if (typeof stored.country === "string" && stored.country) setCountry(stored.country);
        if (typeof r?.timezone === "string" && r.timezone) setTimezone(r.timezone);
        else if (typeof stored.timezone === "string" && stored.timezone) setTimezone(stored.timezone);
        if (typeof r?.vat_rate === "number" && isFinite(r.vat_rate)) setTaxRate(r.vat_rate);
        else if (typeof stored.taxRate === "number" && isFinite(stored.taxRate)) setTaxRate(stored.taxRate);
        if (typeof stored.taxName === "string" && stored.taxName) setTaxName(stored.taxName);
      })
      .catch(() => {
        const stored = getStoredLocale();
        if (typeof stored.currency === "string" && stored.currency) setCurrency(stored.currency);
        if (typeof stored.country === "string" && stored.country) setCountry(stored.country);
        if (typeof stored.timezone === "string" && stored.timezone) setTimezone(stored.timezone);
        if (typeof stored.taxName === "string" && stored.taxName) setTaxName(stored.taxName);
        if (typeof stored.taxRate === "number" && isFinite(stored.taxRate)) setTaxRate(stored.taxRate);
      });
  }, [token]);

  const handleMfaSetup = () => {
    if (!token) return;
    setMfaLoading(true);
    setMfaMessage(null);
    api.mfa.setup(token)
      .then((r: any) => setMfaSetup(r))
      .catch((e: any) => setMfaMessage({ type: "err", text: e?.message || "Failed to start 2FA setup" }))
      .finally(() => setMfaLoading(false));
  };

  const handleMfaVerify = () => {
    if (!token) return;
    setMfaLoading(true);
    setMfaMessage(null);
    api.mfa.verify(mfaCode, token)
      .then((r: any) => {
        setMfaMessage({ type: "ok", text: "Two-factor authentication enabled" });
        setMfaSetup(null);
        setMfaCode("");
        setMfaStatus(r);
      })
      .catch((e: any) => setMfaMessage({ type: "err", text: e?.message || "Invalid code" }))
      .finally(() => setMfaLoading(false));
  };

  const tabs = [
    { id: "general", label: "General", icon: Settings },
    { id: "locale", label: "Locale", icon: Globe },
    { id: "billing", label: "Billing", icon: CreditCard },
    { id: "integrations", label: "Integrations", icon: Link2 },
    { id: "security", label: "Security", icon: Shield },
    { id: "team", label: "Team", icon: Users },
    { id: "locations", label: "Locations", icon: Building },
  ];

  const handleLocaleSave = () => {
    if (!token) return;
    setLocaleSaving(true);
    setLocaleMessage(null);
    storeLocale({ currency, country, timezone, taxName, taxRate });
    api.auth.createBusiness(
      {
        ...(business || {}),
        name: business?.name || "My Business",
        slug: business?.slug || "my-business",
        currency,
        country,
        timezone,
        vat_rate: taxRate,
      },
      token
    )
      .then((r: any) => {
        setBusiness(r);
        setLocaleMessage({ type: "ok", text: "Locale settings saved — applies to new quotes & invoices." });
      })
      .catch((e: any) => setLocaleMessage({ type: "err", text: e?.message || "Failed to save locale settings" }))
      .finally(() => setLocaleSaving(false));
  };

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Settings</h1>

      <div className="flex gap-2 overflow-x-auto pb-2">
        {tabs.map((tab) => (
          <Button
            key={tab.id}
            variant={activeTab === tab.id ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveTab(tab.id)}
            className="gap-2 shrink-0"
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </Button>
        ))}
      </div>

      {activeTab === "general" && (
        <Card>
          <CardHeader><CardTitle>Business Details</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div><label className="text-sm font-medium">Business Name</label><Input /></div>
              <div><label className="text-sm font-medium">Phone</label><Input /></div>
              <div><label className="text-sm font-medium">Email</label><Input type="email" /></div>
              <div><label className="text-sm font-medium">Website</label><Input /></div>
              <div><label className="text-sm font-medium">Address Line 1</label><Input /></div>
              <div><label className="text-sm font-medium">City</label><Input /></div>
              <div><label className="text-sm font-medium">Postcode</label><Input /></div>
              <div><label className="text-sm font-medium">VAT Rate (%)</label><Input type="number" defaultValue="20" /></div>
            </div>
            <Button>Save Changes</Button>
          </CardContent>
        </Card>
      )}

      {activeTab === "locale" && (
        <Card>
          <CardHeader><CardTitle>Locale & Currency</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="text-sm font-medium">Currency</label>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                >
                  {SUPPORTED_CURRENCIES.map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.code} ({c.symbol}) — {c.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium">Country</label>
                <select
                  value={country}
                  onChange={(e) => setCountry(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                >
                  {COUNTRIES.map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium">Timezone</label>
                <select
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                >
                  {TIMEZONES.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium">Tax Name</label>
                <select
                  value={taxName}
                  onChange={(e) => setTaxName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                >
                  {TAX_NAMES.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium">Tax Rate (%)</label>
                <Input
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={taxRate}
                  onChange={(e) => setTaxRate(Number(e.target.value))}
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              These settings apply to new quotes & invoices.
            </p>
            {localeMessage && (
              <p
                className={`flex items-center gap-1.5 text-sm ${
                  localeMessage.type === "ok" ? "text-green-400" : "text-red-400"
                }`}
              >
                {localeMessage.type === "ok" ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <AlertCircle className="h-4 w-4" />
                )}
                {localeMessage.text}
              </p>
            )}
            <Button onClick={handleLocaleSave} disabled={localeSaving || !token}>
              {localeSaving ? "Saving..." : "Save Changes"}
            </Button>
          </CardContent>
        </Card>
      )}

      {activeTab === "billing" && (
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Stripe Payments</CardTitle></CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <CreditCard className="h-8 w-8 text-purple-400" />
                  <div>
                    <p className="font-medium">Accept Card Payments</p>
                    <p className="text-sm text-muted-foreground">Accept Visa, Mastercard, Amex via Stripe</p>
                  </div>
                </div>
                <Button variant="outline" className="gap-2">
                  Connect Stripe
                  <ExternalLink className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>GoCardless Direct Debit</CardTitle></CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Globe className="h-8 w-8 text-blue-400" />
                  <div>
                    <p className="font-medium">UK Direct Debit</p>
                    <p className="text-sm text-muted-foreground">Accept Bacs Direct Debit for recurring payments</p>
                  </div>
                </div>
                <Button variant="outline" className="gap-2">
                  Connect GoCardless
                  <ExternalLink className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "integrations" && (
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Xero Accounting</CardTitle></CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Link2 className="h-8 w-8 text-green-400" />
                  <div>
                    <p className="font-medium">Xero Integration</p>
                    <p className="text-sm text-muted-foreground">Sync invoices, contacts, and payments</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {xeroStatus?.connected ? (
                    <Badge className="bg-green-500/20 text-green-400"><CheckCircle2 className="h-3.5 w-3.5 mr-1" />Connected</Badge>
                  ) : (
                    <Button variant="outline" className="gap-2">Connect Xero<ExternalLink className="h-3.5 w-3.5" /></Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Calendar Sync</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Globe className="h-6 w-6" />
                  <span>Google Calendar</span>
                </div>
                {calendarStatus?.google ? (
                  <Badge className="bg-green-500/20 text-green-400">Connected</Badge>
                ) : (
                  <Button variant="outline" size="sm">Connect</Button>
                )}
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Globe className="h-6 w-6" />
                  <span>Microsoft Outlook</span>
                </div>
                {calendarStatus?.outlook ? (
                  <Badge className="bg-green-500/20 text-green-400">Connected</Badge>
                ) : (
                  <Button variant="outline" size="sm">Connect</Button>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "security" && (
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Two-Factor Authentication</CardTitle></CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Shield className="h-8 w-8 text-yellow-400" />
                  <div>
                    <p className="font-medium">TOTP Authentication</p>
                    <p className="text-sm text-muted-foreground">Use an authenticator app for 2FA</p>
                  </div>
                </div>
                {mfaStatus?.enabled ? (
                  <Badge className="bg-green-500/20 text-green-400"><CheckCircle2 className="h-3.5 w-3.5 mr-1" />Enabled</Badge>
                ) : (
                  <Button variant="outline" onClick={handleMfaSetup} disabled={mfaLoading}>
                    {mfaLoading ? "Starting..." : "Enable 2FA"}
                  </Button>
                )}
              </div>
              {mfaSetup && !mfaStatus?.enabled && (
                <div className="mt-4 space-y-4 border-t pt-4">
                  {typeof mfaSetup.secret === "string" && (
                    <div className="space-y-1">
                      <p className="text-sm font-medium">Setup key</p>
                      <p className="text-sm text-muted-foreground">
                        Scan the QR code in your authenticator app, or enter this key manually:
                      </p>
                      <code className="block rounded-lg bg-muted px-3 py-2 text-sm break-all">
                        {mfaSetup.secret}
                      </code>
                    </div>
                  )}
                  <div className="space-y-2">
                    <p className="text-sm font-medium">Enter the 6-digit code from your authenticator app</p>
                    <InputOTP
                      maxLength={6}
                      value={mfaCode}
                      onChange={(value: string) => setMfaCode(value)}
                    >
                      <InputOTPGroup>
                        <InputOTPSlot index={0} />
                        <InputOTPSlot index={1} />
                        <InputOTPSlot index={2} />
                      </InputOTPGroup>
                      <InputOTPSeparator />
                      <InputOTPGroup>
                        <InputOTPSlot index={3} />
                        <InputOTPSlot index={4} />
                        <InputOTPSlot index={5} />
                      </InputOTPGroup>
                    </InputOTP>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      onClick={handleMfaVerify}
                      disabled={mfaLoading || mfaCode.length !== 6}
                    >
                      {mfaLoading ? "Verifying..." : "Verify & Enable"}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setMfaSetup(null);
                        setMfaCode("");
                        setMfaMessage(null);
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                  {mfaMessage && (
                    <p
                      className={`flex items-center gap-1.5 text-sm ${
                        mfaMessage.type === "ok" ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {mfaMessage.type === "ok" ? (
                        <CheckCircle2 className="h-4 w-4" />
                      ) : (
                        <AlertCircle className="h-4 w-4" />
                      )}
                      {mfaMessage.text}
                    </p>
                  )}
                </div>
              )}
              {mfaMessage && (mfaStatus?.enabled || !mfaSetup) && (
                <p
                  className={`mt-3 flex items-center gap-1.5 text-sm ${
                    mfaMessage.type === "ok" ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {mfaMessage.type === "ok" ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <AlertCircle className="h-4 w-4" />
                  )}
                  {mfaMessage.text}
                </p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>API Keys</CardTitle></CardHeader>
            <CardContent>
              <div className="flex items-center justify-between mb-4">
                <p className="text-sm text-muted-foreground">Manage API keys for third-party integrations</p>
                <Button size="sm" className="gap-1"><Key className="h-3.5 w-3.5" />Create Key</Button>
              </div>
              <p className="text-sm text-muted-foreground">No API keys created yet.</p>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "team" && (
        <Card>
          <CardHeader><CardTitle>Team Members</CardTitle></CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">Manage who has access to your Allo account.</p>
            <Button className="gap-1"><Users className="h-3.5 w-3.5" />Invite Team Member</Button>
          </CardContent>
        </Card>
      )}

      {activeTab === "locations" && (
        <Card>
          <CardHeader><CardTitle>Business Locations</CardTitle></CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">Manage multiple depots or branch offices.</p>
            <Button className="gap-1"><Building className="h-3.5 w-3.5" />Add Location</Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
