"use client";

import { useEffect, useState } from "react";
import {
  isOnline,
  onOnline,
  onOffline,
  syncToServer,
} from "@/lib/sync-service";
import { getPendingSync } from "@/lib/offline-db";

export default function OfflineIndicator() {
  const [online, setOnline] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    setOnline(isOnline());
    refreshCount();

    const unsubOnline = onOnline(async () => {
      setOnline(true);
      setSyncing(true);
      await syncToServer();
      setSyncing(false);
      refreshCount();
    });

    const unsubOffline = onOffline(() => {
      setOnline(false);
    });

    return () => {
      unsubOnline();
      unsubOffline();
    };
  }, []);

  async function refreshCount() {
    const pending = await getPendingSync();
    setPendingCount(pending.length);
  }

  if (online && pendingCount === 0 && !syncing) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <div
        className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium shadow-lg transition-colors ${
          syncing
            ? "bg-amber-500 text-white"
            : online
            ? "bg-emerald-500 text-white"
            : "bg-red-500 text-white"
        }`}
      >
        {syncing ? (
          <>
            <svg
              className="h-4 w-4 animate-spin"
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            Syncing…
          </>
        ) : online ? (
          "Online"
        ) : (
          <>
            Offline
            {pendingCount > 0 && (
              <span className="ml-1 inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-white/20 px-1.5 text-xs">
                {pendingCount}
              </span>
            )}
          </>
        )}
      </div>
    </div>
  );
}
