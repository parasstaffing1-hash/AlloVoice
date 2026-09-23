"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const STORAGE_KEY = "allo_cookie_consent";

type Consent = {
  necessary: true;
  analytics: boolean;
  marketing: boolean;
  ts: number;
};

function readConsent(): Consent | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Consent>;
    if (typeof parsed.analytics !== "boolean" || typeof parsed.marketing !== "boolean") return null;
    return { necessary: true, analytics: parsed.analytics, marketing: parsed.marketing, ts: Number(parsed.ts) || Date.now() };
  } catch {
    return null;
  }
}

export function CookieBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (!readConsent()) setVisible(true);
    } catch {
      setVisible(true);
    }
  }, []);

  function save(analytics: boolean, marketing: boolean) {
    const consent: Consent = { necessary: true, analytics, marketing, ts: Date.now() };
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(consent));
    } catch {
      // storage unavailable (private mode) — just dismiss for this session
    }
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-live="polite"
      aria-label="Cookie consent"
      className="fixed inset-x-0 bottom-0 z-[60] px-4 pb-4 sm:px-6 sm:pb-6"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-4 rounded-2xl border border-border/60 bg-card/95 p-5 shadow-2xl backdrop-blur-xl sm:flex-row sm:items-center">
        <p className="flex-1 text-sm leading-relaxed text-muted-foreground">
          We use essential cookies to run Allo, plus optional analytics and marketing cookies if you allow them.{" "}
          <Link href="/privacy" className="underline underline-offset-4 hover:text-primary">
            See our Privacy Notice
          </Link>
          .
        </p>
        <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
          <button
            type="button"
            onClick={() => save(false, false)}
            className="rounded-xl border border-border/70 bg-secondary px-4 py-2.5 text-sm font-medium text-secondary-foreground transition-colors hover:bg-accent"
          >
            Accept essential-only
          </button>
          <button
            type="button"
            onClick={() => save(true, true)}
            className="rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            Accept all
          </button>
        </div>
      </div>
    </div>
  );
}

export default CookieBanner;
