import { format, formatDistanceToNow, addDays, parseISO, isValid } from "date-fns";

const FALLBACK = "—";

function toDate(input: unknown): Date | null {
  if (input === null || input === undefined) return null;
  try {
    const d = typeof input === "string" ? parseISO(input) : new Date(input as string | number | Date);
    return isValid(d) ? d : null;
  } catch {
    return null;
  }
}

export function formatGBP(n: number): string {
  if (n === null || n === undefined || typeof n !== "number" || Number.isNaN(n) || !Number.isFinite(n)) {
    return FALLBACK;
  }
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(n);
  } catch {
    return FALLBACK;
  }
}

export function formatDateGB(iso: string): string {
  const d = toDate(iso);
  if (!d) return FALLBACK;
  try {
    return format(d, "d MMM yyyy");
  } catch {
    return FALLBACK;
  }
}

export function formatDateTimeGB(iso: string): string {
  const d = toDate(iso);
  if (!d) return FALLBACK;
  try {
    return format(d, "d MMM yyyy, HH:mm");
  } catch {
    return FALLBACK;
  }
}

export function timeAgo(iso: string): string {
  const d = toDate(iso);
  if (!d) return FALLBACK;
  try {
    return formatDistanceToNow(d, { addSuffix: true });
  } catch {
    return FALLBACK;
  }
}

export function todayISO(): string {
  try {
    return new Date().toISOString();
  } catch {
    return FALLBACK;
  }
}

export function addDaysISO(iso: string, days: number): string {
  const d = toDate(iso);
  if (!d || typeof days !== "number" || Number.isNaN(days)) return FALLBACK;
  try {
    return addDays(d, days).toISOString();
  } catch {
    return FALLBACK;
  }
}
