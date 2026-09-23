"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Wrench,
  Droplets,
  Zap,
  Flame,
  AlertTriangle,
  Upload,
  MapPin,
  Calendar,
  Clock,
  CheckCircle2,
  ArrowLeft,
  ArrowRight,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/store";
import { COUNTRIES } from "@/lib/money";

interface Service {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}

interface AddressResult {
  line_1: string;
  line_2?: string;
  town: string;
  county?: string;
  postcode: string;
}

interface PostcodeSuggestion {
  postcode: string;
}

interface TimeSlot {
  time: string;
  available: boolean;
}

interface BookingData {
  service: string;
  description: string;
  photos: string[];
  country: string;
  postcode: string;
  address: AddressResult | null;
  date: string;
  time: string;
  name: string;
  phone: string;
  email: string;
  referralSource: string;
}

const SERVICES: Service[] = [
  { id: "boiler", label: "Boiler Repair", icon: Flame, color: "text-red-400" },
  { id: "plumbing", label: "Plumbing", icon: Droplets, color: "text-blue-400" },
  { id: "electrical", label: "Electrical", icon: Zap, color: "text-yellow-400" },
  { id: "heating", label: "Heating", icon: Wrench, color: "text-orange-400" },
  { id: "emergency", label: "Emergency", icon: AlertTriangle, color: "text-pink-400" },
];

const REFERRAL_OPTIONS = ["Google Search", "Friend / Family", "Social Media", "Previous Customer", "Other"];
const DRAFT_KEY = "voicefield_booking_draft";

function getStoredDraft(): Partial<BookingData> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveDraft(data: BookingData) {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(data));
  } catch {}
}

function clearDraft() {
  localStorage.removeItem(DRAFT_KEY);
}

function generateWeekdays(fromDate: Date, weeks = 4): Date[] {
  const dates: Date[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(fromDate);
  start.setHours(0, 0, 0, 0);

  const current = new Date(start);
  const end = new Date(today);
  end.setDate(end.getDate() + weeks * 7);

  while (current <= end && dates.length < weeks * 5) {
    const day = current.getDay();
    if (day !== 0 && day !== 6) {
      dates.push(new Date(current));
    }
    current.setDate(current.getDate() + 1);
  }
  return dates;
}

function generateTimeSlots(): TimeSlot[] {
  const slots: TimeSlot[] = [];
  for (let h = 8; h < 18; h++) {
    slots.push({ time: `${String(h).padStart(2, "0")}:00`, available: true });
    if (h < 17) slots.push({ time: `${String(h).padStart(2, "0")}:30`, available: true });
  }
  return slots;
}

function formatUKDate(d: Date): string {
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

export default function BookingPage() {
  const draft = getStoredDraft();
  const { token } = useAuth();
  const [step, setStep] = useState(0);
  const [data, setData] = useState<BookingData>({
    service: draft?.service || "",
    description: draft?.description || "",
    photos: draft?.photos || [],
    country: draft?.country || "GB",
    postcode: draft?.postcode || "",
    address: draft?.address || null,
    date: draft?.date || "",
    time: draft?.time || "",
    name: draft?.name || "",
    phone: draft?.phone || "",
    email: draft?.email || "",
    referralSource: draft?.referralSource || "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submittedId, setSubmittedId] = useState("");

  // Postcode lookup
  const [postcodeQuery, setPostcodeQuery] = useState(draft?.postcode || "");
  const [postcodeSuggestions, setPostcodeSuggestions] = useState<PostcodeSuggestion[]>([]);
  const [lookingUp, setLookingUp] = useState(false);

  // Live availability: GET /api/scheduling/availability?start_date=X&end_date=Y
  // (auth required). Returns { slots: [{ date, available_hours, booked_hours,
  // utilization_pct }]} — daily granularity. Public/demo visitors have no token
  // or the backend is unreachable → graceful fallback to all-available.
  const [availabilityByDate, setAvailabilityByDate] = useState<Record<string, any>>({});
  const [availLoading, setAvailLoading] = useState(false);

  const baseSlots = generateTimeSlots();
  const availableDates = generateWeekdays(new Date());

  useEffect(() => {
    if (availableDates.length === 0 || !token) return;
    const start = availableDates[0].toISOString().split("T")[0];
    const end = availableDates[availableDates.length - 1].toISOString().split("T")[0];
    setAvailLoading(true);
    api.scheduling
      .availability(start, end, token)
      .then((r: any) => {
        const slots = Array.isArray((r as any)?.slots) ? (r as any).slots : [];
        const map: Record<string, any> = {};
        slots.forEach((s: any) => {
          const key = String(s?.date ?? "").split("T")[0];
          if (key) map[key] = s;
        });
        setAvailabilityByDate(map);
      })
      .catch(() => setAvailabilityByDate({}))
      .finally(() => setAvailLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Merge live daily utilization into per-slot availability. Backend has no
  // per-hour slots, so a fully-booked day disables all slots; a partially
  // booked day disables the earliest N slots proportional to utilization.
  const timeSlots: TimeSlot[] = (() => {
    const dayInfo = data.date ? availabilityByDate[data.date] : null;
    if (!dayInfo) return baseSlots;
    const total = baseSlots.length;
    const utilization = Number(dayInfo?.utilization_pct ?? 0);
    const availableHours = Number(dayInfo?.available_hours ?? total);
    if (availableHours <= 0 || utilization >= 100) {
      return baseSlots.map((s) => ({ ...s, available: false }));
    }
    if (utilization <= 0) return baseSlots;
    const bookedCount = Math.min(total, Math.round((utilization / 100) * total));
    return baseSlots.map((s, i) => ({ ...s, available: i >= bookedCount }));
  })();

  useEffect(() => {
    if (step >= 0) saveDraft(data);
  }, [data, step]);

  // If live availability marks the chosen time unavailable, clear it so the
  // user must pick a genuinely free slot.
  useEffect(() => {
    if (!data.date || !data.time) return;
    const slot = timeSlots.find((s) => s.time === data.time);
    if (slot && !slot.available) {
      setData((prev) => ({ ...prev, time: "" }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.date, availabilityByDate]);

  const update = <K extends keyof BookingData>(key: K, value: BookingData[K]) => {
    setData((prev) => ({ ...prev, [key]: value }));
  };

  const isGB = (data.country || "GB") === "GB";

  const handleCountryChange = (code: string) => {
    setPostcodeSuggestions([]);
    setData((prev) => ({
      ...prev,
      country: code,
      address:
        code === "GB"
          ? prev.address
          : prev.address ?? { line_1: "", line_2: "", town: "", county: "", postcode: "" },
    }));
  };

  const fetchPostcodeSuggestions = useCallback(async (q: string) => {
    if (q.length < 3) {
      setPostcodeSuggestions([]);
      return;
    }
    try {
      const res = await api.postcodes.autocomplete(q);
      setPostcodeSuggestions((res as any).suggestions || []);
    } catch {
      setPostcodeSuggestions([]);
    }
  }, []);

  const lookupPostcode = async (postcode: string) => {
    setLookingUp(true);
    try {
      const res = await api.postcodes.lookup(postcode);
      const result = (res as any).result;
      if (result) {
        setData((prev) => ({
          ...prev,
          postcode,
          address: {
            line_1: result.line_1 || "",
            line_2: result.line_2 || "",
            town: result.town || "",
            county: result.county || "",
            postcode: result.postcode || postcode,
          },
        }));
      }
    } catch {
    } finally {
      setLookingUp(false);
    }
  };

  const handlePostcodeSelect = (pc: string) => {
    setPostcodeQuery(pc);
    setPostcodeSuggestions([]);
    lookupPostcode(pc);
  };

  const handlePhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    const readers: Promise<string>[] = [];
    for (let i = 0; i < files.length; i++) {
      readers.push(
        new Promise((resolve) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.readAsDataURL(files[i]);
        })
      );
    }
    Promise.all(readers).then((results) => {
      setData((prev) => ({ ...prev, photos: [...prev.photos, ...results] }));
    });
  };

  const removePhoto = (idx: number) => {
    setData((prev) => ({ ...prev, photos: prev.photos.filter((_, i) => i !== idx) }));
  };

  const steps = [
    { title: "Select Service", icon: Wrench },
    { title: "Describe Issue", icon: AlertTriangle },
    { title: "Property Details", icon: MapPin },
    { title: "Select Date/Time", icon: Calendar },
    { title: "Contact Details", icon: Clock },
    { title: "Review & Confirm", icon: CheckCircle2 },
  ];

  const canNext = (): boolean => {
    switch (step) {
      case 0: return !!data.service;
      case 1: return data.description.trim().length > 0;
      case 2: return isGB ? (!!data.postcode && !!data.address) : (!!data.address?.line_1?.trim() && !!data.address?.town?.trim());
      case 3: return !!data.date && !!data.time;
      case 4: return !!data.name && !!data.phone && !!data.email;
      default: return true;
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const res = await fetch("/api/book", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const json = await res.json();
      setSubmittedId(json.id);
      setSubmitted(true);
      clearDraft();
    } catch {
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md text-center">
          <CardContent className="pt-8 pb-8">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-500/10">
              <CheckCircle2 className="h-8 w-8 text-green-500" />
            </div>
            <h2 className="text-2xl font-bold mb-2">Booking Confirmed</h2>
            <p className="text-muted-foreground mb-4">
              Your booking request has been received. We&apos;ll be in touch shortly.
            </p>
            <Badge variant="secondary" className="text-lg px-4 py-1 mb-6">
              Ref: {submittedId}
            </Badge>
            <p className="text-sm text-muted-foreground">
              You&apos;ll receive a confirmation email and a call from our team to confirm your appointment.
            </p>
            <Button variant="outline" className="mt-6" onClick={() => { setSubmitted(false); setStep(0); setData({ service: "", description: "", photos: [], country: "GB", postcode: "", address: null, date: "", time: "", name: "", phone: "", email: "", referralSource: "" }); }}>
              Book Another
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border/50 bg-background/80 backdrop-blur-xl sticky top-0 z-50">
        <div className="mx-auto max-w-2xl px-4 py-4">
          <h1 className="text-xl font-bold text-center mb-4">Book a Job</h1>
          {/* Step indicator */}
          <div className="flex items-center justify-center gap-2">
            {steps.map((s, i) => (
              <div key={s.title} className="flex items-center gap-2">
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium transition-colors ${
                    i === step
                      ? "bg-primary text-primary-foreground"
                      : i < step
                      ? "bg-primary/20 text-primary"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  {i < step ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
                </div>
                {i < steps.length - 1 && (
                  <div className={`hidden sm:block h-px w-8 ${i < step ? "bg-primary/30" : "bg-muted"}`} />
                )}
              </div>
            ))}
          </div>
          <p className="text-center text-sm text-muted-foreground mt-2">{steps[step].title}</p>
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-2xl px-4 py-8">
        <Card>
          <CardContent className="p-6">
            {/* Step 0: Select Service */}
            {step === 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {SERVICES.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => update("service", s.id)}
                    className={`flex flex-col items-center gap-3 rounded-xl border p-6 text-center transition-all hover:border-primary/50 ${
                      data.service === s.id
                        ? "border-primary bg-primary/10 shadow-sm"
                        : "border-border/50 bg-background hover:bg-muted/50"
                    }`}
                  >
                    <s.icon className={`h-8 w-8 ${s.color}`} />
                    <span className="text-sm font-medium">{s.label}</span>
                  </button>
                ))}
              </div>
            )}

            {/* Step 1: Describe Issue */}
            {step === 1 && (
              <div className="space-y-4">
                <Textarea
                  placeholder="Please describe the issue... e.g. 'My boiler is making a banging noise and not heating water'"
                  className="min-h-[140px] text-base"
                  value={data.description}
                  onChange={(e) => update("description", e.target.value)}
                />
                <div>
                  <label className="block text-sm font-medium mb-2">
                    Photos <span className="text-muted-foreground">(optional)</span>
                  </label>
                  <div className="flex flex-wrap gap-3">
                    {data.photos.map((photo, idx) => (
                      <div key={idx} className="relative h-24 w-24 rounded-lg overflow-hidden border">
                        <img src={photo} alt={`Photo ${idx + 1}`} className="h-full w-full object-cover" />
                        <button
                          onClick={() => removePhoto(idx)}
                          className="absolute top-1 right-1 h-5 w-5 rounded-full bg-destructive text-destructive-foreground flex items-center justify-center text-xs"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                    <label className="flex h-24 w-24 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed hover:bg-muted/50 transition-colors">
                      <Upload className="h-5 w-5 text-muted-foreground mb-1" />
                      <span className="text-[10px] text-muted-foreground">Add Photo</span>
                      <input
                        type="file"
                        accept="image/*"
                        multiple
                        className="hidden"
                        onChange={handlePhotoUpload}
                      />
                    </label>
                  </div>
                </div>
              </div>
            )}

            {/* Step 2: Property Details */}
            {step === 2 && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Country</label>
                  <select
                    value={data.country || "GB"}
                    onChange={(e) => handleCountryChange(e.target.value)}
                    className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                  >
                    {COUNTRIES.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </div>
                {!isGB && (
                  <p className="text-xs text-muted-foreground">
                    Postcode lookup is only available for UK addresses. Please enter your address manually below.
                  </p>
                )}
                {isGB && (
                <div>
                  <label className="block text-sm font-medium mb-2">Postcode</label>
                  <div className="relative">
                    <Input
                      placeholder="e.g. M1 1AA"
                      value={postcodeQuery}
                      onChange={(e) => {
                        setPostcodeQuery(e.target.value);
                        fetchPostcodeSuggestions(e.target.value);
                      }}
                      onBlur={() => setTimeout(() => setPostcodeSuggestions([]), 200)}
                    />
                    {postcodeSuggestions.length > 0 && (
                      <div className="absolute top-full left-0 right-0 z-10 mt-1 rounded-lg border bg-popover shadow-md max-h-48 overflow-auto">
                        {postcodeSuggestions.map((s) => (
                          <button
                            key={s.postcode}
                            className="w-full px-3 py-2 text-left text-sm hover:bg-accent transition-colors"
                            onMouseDown={() => handlePostcodeSelect(s.postcode)}
                          >
                            <MapPin className="h-3 w-3 inline mr-2 text-muted-foreground" />
                            {s.postcode}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                )}
                {data.address && (
                  <div className="rounded-xl bg-muted/50 p-4 space-y-3">
                    <p className="text-sm font-medium flex items-center gap-2">
                      <MapPin className="h-4 w-4 text-primary" />
                      {isGB ? "Address Found" : "Address"}
                    </p>
                    <div className="space-y-2">
                      <Input
                        placeholder="Address Line 1"
                        value={data.address.line_1}
                        onChange={(e) => update("address", { ...data.address!, line_1: e.target.value })}
                      />
                      <Input
                        placeholder="Address Line 2 (optional)"
                        value={data.address.line_2 || ""}
                        onChange={(e) => update("address", { ...data.address!, line_2: e.target.value })}
                      />
                      <div className="grid grid-cols-2 gap-2">
                        <Input
                          placeholder="Town / City"
                          value={data.address.town}
                          onChange={(e) => update("address", { ...data.address!, town: e.target.value })}
                        />
                        <Input
                          placeholder="County"
                          value={data.address.county || ""}
                          onChange={(e) => update("address", { ...data.address!, county: e.target.value })}
                        />
                      </div>
                      <Input
                        placeholder={isGB ? "Postcode" : "Postcode / ZIP"}
                        value={data.address.postcode}
                        onChange={(e) => update("address", { ...data.address!, postcode: e.target.value })}
                      />
                    </div>
                  </div>
                )}
                {lookingUp && (
                  <p className="text-sm text-muted-foreground text-center">Looking up postcode...</p>
                )}
              </div>
            )}

            {/* Step 3: Select Date/Time */}
            {step === 3 && (
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium mb-3">Select a Date</label>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[300px] overflow-y-auto pr-1">
                    {availableDates.map((d) => {
                      const dateStr = d.toISOString().split("T")[0];
                      const isSelected = data.date === dateStr;
                      return (
                        <button
                          key={dateStr}
                          onClick={() => update("date", dateStr)}
                          className={`rounded-lg border p-3 text-left text-sm transition-all ${
                            isSelected
                              ? "border-primary bg-primary/10 text-foreground"
                              : "border-border/50 hover:border-primary/30 text-foreground"
                          }`}
                        >
                          <div className="font-medium">{formatUKDate(d)}</div>
                          <div className="text-xs text-muted-foreground">{dateStr}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {data.date && (
                  <div>
                    <label className="block text-sm font-medium mb-3">
                      Select a Time{availLoading ? " (checking live availability…)" : ""}
                    </label>
                    <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                      {timeSlots.map((slot) => (
                        <button
                          key={slot.time}
                          onClick={() => update("time", slot.time)}
                          disabled={!slot.available}
                          className={`rounded-lg border p-2.5 text-sm font-medium transition-all ${
                            data.time === slot.time
                              ? "border-primary bg-primary/10 text-foreground"
                              : slot.available
                              ? "border-border/50 hover:border-primary/30 text-foreground"
                              : "border-border/20 text-muted-foreground opacity-50 cursor-not-allowed"
                          }`}
                        >
                          {slot.time}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Step 4: Contact Details */}
            {step === 4 && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Full Name</label>
                  <Input
                    placeholder="John Smith"
                    value={data.name}
                    onChange={(e) => update("name", e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Phone Number</label>
                  <div className="flex">
                    <span className="inline-flex items-center rounded-l-lg border border-r-0 bg-muted px-3 text-sm text-muted-foreground">
                      +44
                    </span>
                    <Input
                      placeholder="7700 900000"
                      value={data.phone}
                      onChange={(e) => update("phone", e.target.value)}
                      className="rounded-l-none"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Email</label>
                  <Input
                    type="email"
                    placeholder="john@example.co.uk"
                    value={data.email}
                    onChange={(e) => update("email", e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">
                    How did you hear about us? <span className="text-muted-foreground">(optional)</span>
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {REFERRAL_OPTIONS.map((opt) => (
                      <button
                        key={opt}
                        onClick={() => update("referralSource", opt)}
                        className={`rounded-full border px-3 py-1.5 text-sm transition-all ${
                          data.referralSource === opt
                            ? "border-primary bg-primary/10 text-foreground"
                            : "border-border/50 hover:border-primary/30 text-foreground"
                        }`}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Step 5: Review & Confirm */}
            {step === 5 && (
              <div className="space-y-5">
                <div className="rounded-xl bg-muted/50 p-4 space-y-3">
                  <h3 className="font-semibold">Booking Summary</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Service</span>
                      <span>{SERVICES.find((s) => s.id === data.service)?.label}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Issue</span>
                      <span className="text-right max-w-[60%]">{data.description}</span>
                    </div>
                    {data.photos.length > 0 && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Photos</span>
                        <span>{data.photos.length} attached</span>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Address</span>
                      <span className="text-right max-w-[60%]">
                        {data.address?.line_1}, {data.address?.town} {data.address?.postcode}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Date</span>
                      <span>{formatUKDate(new Date(data.date + "T00:00:00"))}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Time</span>
                      <span>{data.time}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Name</span>
                      <span>{data.name}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Phone</span>
                      <span>+44{data.phone}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Email</span>
                      <span>{data.email}</span>
                    </div>
                    {data.referralSource && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Referral</span>
                        <span>{data.referralSource}</span>
                      </div>
                    )}
                  </div>
                </div>
                <label className="flex items-start gap-3 text-sm">
                  <input
                    type="checkbox"
                    id="terms"
                    className="mt-0.5 h-4 w-4 rounded border-input accent-primary"
                  />
                  <span className="text-muted-foreground">
                    I agree to the{" "}
                    <span className="text-primary cursor-pointer">terms and conditions</span> and consent to being
                    contacted about my booking. Your data will be processed in accordance with our{" "}
                    <span className="text-primary cursor-pointer">privacy policy</span>.
                  </span>
                </label>
              </div>
            )}
          </CardContent>

          {/* Navigation */}
          <CardFooter className="flex items-center justify-between px-6 pb-6 pt-0">
            {step > 0 ? (
              <Button variant="outline" onClick={() => setStep(step - 1)} className="gap-2">
                <ArrowLeft className="h-4 w-4" />
                Back
              </Button>
            ) : (
              <div />
            )}
            {step < steps.length - 1 ? (
              <Button onClick={() => setStep(step + 1)} disabled={!canNext()} className="gap-2">
                Next
                <ArrowRight className="h-4 w-4" />
              </Button>
            ) : (
              <Button onClick={handleSubmit} disabled={submitting} className="gap-2">
                {submitting ? "Submitting..." : "Confirm Booking"}
                {!submitting && <CheckCircle2 className="h-4 w-4" />}
              </Button>
            )}
          </CardFooter>
        </Card>

        {/* Save draft indicator */}
        <p className="text-center text-xs text-muted-foreground mt-4">
          Your progress is saved automatically. You can close this page and come back later.
        </p>
      </div>
    </div>
  );
}
