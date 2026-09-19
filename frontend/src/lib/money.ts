export const SUPPORTED_CURRENCIES = [
  { code: "GBP", symbol: "£", label: "British Pound" },
  { code: "USD", symbol: "$", label: "US Dollar" },
  { code: "EUR", symbol: "€", label: "Euro" },
  { code: "INR", symbol: "₹", label: "Indian Rupee" },
  { code: "AED", symbol: "د.إ", label: "UAE Dirham" },
  { code: "AUD", symbol: "A$", label: "Australian Dollar" },
  { code: "CAD", symbol: "CA$", label: "Canadian Dollar" },
  { code: "SGD", symbol: "S$", label: "Singapore Dollar" },
];

const LOCALE_MAP: Record<string, string> = {
  GBP: "en-GB",
  USD: "en-US",
  EUR: "de-DE",
  INR: "en-IN",
  AED: "ar-AE-u-nu-latn",
  AUD: "en-AU",
  CAD: "en-CA",
  SGD: "en-SG",
};

export function formatMoney(amount: number, currency = "GBP"): string {
  try {
    if (typeof amount !== "number" || !isFinite(amount)) return "—";
    const supported = SUPPORTED_CURRENCIES.some((c) => c.code === currency);
    const code = supported ? currency : "GBP";
    return new Intl.NumberFormat(LOCALE_MAP[code] || "en-GB", {
      style: "currency",
      currency: code,
    }).format(amount);
  } catch {
    return "—";
  }
}

export const TAX_NAMES = [
  { id: "VAT", label: "VAT" },
  { id: "GST", label: "GST" },
  { id: "Sales Tax", label: "Sales Tax" },
  { id: "None", label: "None" },
];

export const COUNTRIES = [
  { code: "GB", label: "United Kingdom" },
  { code: "US", label: "United States" },
  { code: "IN", label: "India" },
  { code: "AE", label: "United Arab Emirates" },
  { code: "AU", label: "Australia" },
  { code: "CA", label: "Canada" },
  { code: "IE", label: "Ireland" },
  { code: "SG", label: "Singapore" },
  { code: "DE", label: "Germany" },
  { code: "FR", label: "France" },
];

export const TIMEZONES = [
  "Europe/London",
  "Europe/Dublin",
  "Europe/Paris",
  "Europe/Berlin",
  "America/New_York",
  "America/Chicago",
  "America/Los_Angeles",
  "America/Toronto",
  "Asia/Dubai",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Australia/Sydney",
];

export interface LocaleSettings {
  currency: string;
  country: string;
  timezone: string;
  taxName: string;
  taxRate: number;
}

export const LOCALE_DEFAULTS: LocaleSettings = {
  currency: "GBP",
  country: "GB",
  timezone: "Europe/London",
  taxName: "VAT",
  taxRate: 20,
};

const LOCALE_STORAGE_KEY = "voicefield_locale";

export function getStoredLocale(): Partial<LocaleSettings> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Partial<LocaleSettings>) : {};
  } catch {
    return {};
  }
}

export function storeLocale(settings: LocaleSettings): void {
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, JSON.stringify(settings));
  } catch {
    /* storage unavailable */
  }
}

export function resolveCurrency(business: any): string {
  const stored = getStoredLocale();
  const code =
    (typeof business?.currency === "string" && business.currency) ||
    (typeof stored.currency === "string" && stored.currency) ||
    LOCALE_DEFAULTS.currency;
  return SUPPORTED_CURRENCIES.some((c) => c.code === code) ? code : "GBP";
}
