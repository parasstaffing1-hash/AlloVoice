import { api } from "./api";
import {
  saveTable,
  addPendingSync,
  getPendingSync,
  clearPendingSync,
} from "./offline-db";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function isOnline(): boolean {
  return navigator.onLine;
}

export function onOnline(callback: () => void): () => void {
  window.addEventListener("online", callback);
  return () => window.removeEventListener("online", callback);
}

export function onOffline(callback: () => void): () => void {
  window.addEventListener("offline", callback);
  return () => window.removeEventListener("offline", callback);
}

export async function syncToServer(): Promise<number> {
  if (!isOnline()) return 0;

  const pending = await getPendingSync();
  let synced = 0;

  for (const op of pending) {
    try {
      const method =
        op.operation === "create"
          ? "POST"
          : op.operation === "update"
          ? "PUT"
          : "DELETE";

      const body =
        op.operation !== "delete" ? JSON.stringify(op.data) : undefined;

      const token = localStorage.getItem("token");
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const endpoint =
        op.operation === "delete"
          ? `${API_BASE}/api/${op.table}/${op.data.id}`
          : `${API_BASE}/api/${op.table}`;

      const response = await fetch(endpoint, {
        method,
        headers,
        body,
      });

      if (response.ok && op.id !== undefined) {
        await clearPendingSync(op.id);
        synced++;
      }
    } catch {
      // If any op fails, stop and retry later
      break;
    }
  }

  return synced;
}

export async function fetchAndCacheJobs(token: string): Promise<void> {
  try {
    const data: any = await api.jobs.list(token);
    const jobs = Array.isArray(data) ? data : data.items || [];
    await saveTable("jobs", jobs);
  } catch {
    // Offline or error — keep stale cache
  }
}

export async function fetchAndCacheCustomers(token: string): Promise<void> {
  try {
    const data: any = await api.customers.list(token);
    const customers = Array.isArray(data) ? data : data.items || [];
    await saveTable("customers", customers);
  } catch {
    // Offline or error — keep stale cache
  }
}

export async function queueOffline(
  table: string,
  operation: "create" | "update" | "delete",
  data: any
): Promise<void> {
  await addPendingSync(table, operation, data);
  // Notify service worker if available
  if ("serviceWorker" in navigator && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({
      type: "SYNC_QUEUED",
      table,
      operation,
    });
  }
}
