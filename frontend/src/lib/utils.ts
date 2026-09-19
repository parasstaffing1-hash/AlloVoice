import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, currency = "GBP"): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatDate(date: Date | string): string {
  return new Date(date).toLocaleDateString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(date: Date | string): string {
  return new Date(date).toLocaleDateString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    quote_requested: "bg-yellow-500/20 text-yellow-400",
    quote_sent: "bg-blue-500/20 text-blue-400",
    quote_approved: "bg-green-500/20 text-green-400",
    scheduled: "bg-purple-500/20 text-purple-400",
    in_progress: "bg-orange-500/20 text-orange-400",
    completed: "bg-emerald-500/20 text-emerald-400",
    invoiced: "bg-cyan-500/20 text-cyan-400",
    paid: "bg-green-500/20 text-green-400",
    cancelled: "bg-red-500/20 text-red-400",
    pending: "bg-yellow-500/20 text-yellow-400",
    overdue: "bg-red-500/20 text-red-400",
  };
  return colors[status] || "bg-gray-500/20 text-gray-400";
}

export function getStatusLabel(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}
