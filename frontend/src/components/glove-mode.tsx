"use client";

import { useLayoutEffect, useState } from "react";
import { Hand } from "lucide-react";
import { cn } from "@/lib/utils";

const KEY = "vf_glove_mode";

export function useGloveMode() {
  const [enabled, setEnabled] = useState(false);

  useLayoutEffect(() => {
    try {
      if (localStorage.getItem(KEY) === "1") {
        setEnabled(true);
        document.documentElement.classList.add("glove-mode");
      }
    } catch {}
  }, []);

  const toggle = () => {
    setEnabled((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(KEY, next ? "1" : "0");
      } catch {}
      document.documentElement.classList.toggle("glove-mode", next);
      return next;
    });
  };

  return { enabled, toggle };
}

export function GloveToggle() {
  const { enabled, toggle } = useGloveMode();
  return (
    <button
      onClick={toggle}
      aria-pressed={enabled}
      title="Glove mode — big buttons for site work"
      className={cn(
        "fixed bottom-20 left-4 z-50 flex items-center gap-2 rounded-full border px-4 py-3 text-sm font-medium backdrop-blur-xl transition-all",
        enabled
          ? "border-amber-400 bg-amber-400/20 text-amber-300"
          : "border-border bg-card/80 text-muted-foreground hover:text-foreground"
      )}
    >
      <Hand className="h-5 w-5" />
      Glove {enabled ? "ON" : "OFF"}
    </button>
  );
}
