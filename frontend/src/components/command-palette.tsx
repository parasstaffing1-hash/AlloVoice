"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  Users,
  Briefcase,
  Receipt,
  FileText,
  Plus,
  CalendarDays,
  BarChart3,
  Loader2,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/store";

interface SearchItem {
  id: string;
  title: string;
  subtitle?: string;
}

interface GroupedResults {
  customers: SearchItem[];
  jobs: SearchItem[];
  invoices: SearchItem[];
  quotes: SearchItem[];
}

const EMPTY_RESULTS: GroupedResults = {
  customers: [],
  jobs: [],
  invoices: [],
  quotes: [],
};

const GROUP_META: {
  key: keyof GroupedResults;
  label: string;
  route: string;
  Icon: typeof Users;
}[] = [
  { key: "customers", label: "Customers", route: "/customers", Icon: Users },
  { key: "jobs", label: "Jobs", route: "/jobs", Icon: Briefcase },
  { key: "invoices", label: "Invoices", route: "/invoices", Icon: Receipt },
  { key: "quotes", label: "Quotes", route: "/quotes", Icon: FileText },
];

function normalizeResults(raw: any): GroupedResults {
  const grouped: GroupedResults = {
    customers: [],
    jobs: [],
    invoices: [],
    quotes: [],
  };
  if (!raw) return grouped;

  // Flat shape: { results: [{ type, id, title, subtitle }] }
  const flat: any[] = Array.isArray(raw?.results) ? raw.results : [];
  for (const item of flat) {
    const type = String(item?.type ?? "").toLowerCase();
    const entry: SearchItem = {
      id: String(item?.id ?? ""),
      title: String(item?.title ?? "Untitled"),
      subtitle: item?.subtitle ? String(item.subtitle) : undefined,
    };
    if (!entry.id) continue;
    if (type === "customer" || type === "customers") grouped.customers.push(entry);
    else if (type === "job" || type === "jobs") grouped.jobs.push(entry);
    else if (type === "invoice" || type === "invoices") grouped.invoices.push(entry);
    else if (type === "quote" || type === "quotes") grouped.quotes.push(entry);
  }

  // Grouped shape: { customers: [...], jobs: [...], invoices: [...], quotes: [...] }
  for (const key of ["customers", "jobs", "invoices", "quotes"] as const) {
    const arr = raw?.[key];
    if (Array.isArray(arr)) {
      for (const item of arr) {
        if (item === null || item === undefined) continue;
        if (typeof item === "string") {
          grouped[key].push({ id: item, title: item });
        } else {
          const id = String(item?.id ?? item?.uuid ?? "");
          if (!id) continue;
          grouped[key].push({
            id,
            title: String(
              item?.title ?? item?.name ?? item?.full_name ?? item?.invoice_number ?? "Untitled"
            ),
            subtitle:
              item?.subtitle ?? item?.company ?? item?.phone ?? item?.status
                ? String(item?.subtitle ?? item?.company ?? item?.phone ?? item?.status)
                : undefined,
          });
        }
      }
    }
  }

  return grouped;
}

const QUICK_LINKS = [
  { label: "New Job", href: "/jobs/new", Icon: Plus },
  { label: "Schedule", href: "/schedule", Icon: CalendarDays },
  { label: "Reports", href: "/reports", Icon: BarChart3 },
];

function getItemHref(key: keyof GroupedResults, id: string): string {
  if (key === "jobs") return `/jobs/${id}/complete`;
  if (key === "quotes") return `/quotes/${id}/present`;
  if (key === "customers") return "/customers";
  if (key === "invoices") return "/invoices";
  return `/${key}/${id}`;
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GroupedResults>(EMPTY_RESULTS);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { token } = useAuth();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const runSearch = useCallback(
    (q: string) => {
      if (!token) return;
      const trimmed = q.trim();
      if (trimmed.length < 2) {
        setResults(EMPTY_RESULTS);
        setLoading(false);
        return;
      }
      setLoading(true);
      const requestId = ++requestIdRef.current;
      api.search
        .global(trimmed, token)
        .then((r: any) => {
          if (requestIdRef.current !== requestId) return;
          setResults(normalizeResults(r));
          setLoading(false);
        })
        .catch((e: any) => {
          if (requestIdRef.current !== requestId) return;
          void e;
          setResults(EMPTY_RESULTS);
          setLoading(false);
        });
    },
    [token]
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runSearch(query), 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, runSearch]);

  // Reset state when closed
  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults(EMPTY_RESULTS);
      setLoading(false);
    }
  }, [open ]);

  const navigate = useCallback(
    (href: string) => {
      setOpen(false);
      router.push(href);
    },
    [router]
  );

  const totalCount = useMemo(
    () =>
      results.customers.length +
      results.jobs.length +
      results.invoices.length +
      results.quotes.length,
    [results]
  );

  const showQuickLinks = query.trim().length < 2;

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Global Command Menu"
      className="fixed left-1/2 top-[20vh] z-[100] w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 shadow-2xl"
      overlayClassName="fixed inset-0 z-[99] bg-black/70 backdrop-blur-sm"
    >
      <div className="flex items-center gap-2 border-b border-zinc-800 px-4">
        <Command.Input
          value={query}
          onValueChange={setQuery}
          placeholder="Search customers, jobs, invoices, quotes…"
          className="h-12 w-full bg-transparent text-sm text-zinc-100 placeholder:text-zinc-500 focus:outline-none"
        />
        {loading && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-zinc-500" />}
        <kbd className="shrink-0 rounded border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">
          ESC
        </kbd>
      </div>

      <Command.List className="max-h-[320px] overflow-y-auto p-2">
        {!token ? (
          <div className="px-4 py-8 text-center text-sm text-zinc-400">
            Sign in to search
          </div>
        ) : showQuickLinks ? (
          <>
            <Command.Group heading="Quick links">
              {QUICK_LINKS.map(({ label, href, Icon }) => (
                <Command.Item
                  key={href + label}
                  value={`${label} ${href}`}
                  onSelect={() => navigate(href)}
                  className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-zinc-200 aria-selected:bg-zinc-800"
                >
                  <Icon className="h-4 w-4 shrink-0 text-zinc-500" />
                  <span>{label}</span>
                  <span className="ml-auto text-xs text-zinc-600">{href}</span>
                </Command.Item>
              ))}
            </Command.Group>
            <Command.Empty />
          </>
        ) : totalCount === 0 && !loading ? (
          <Command.Empty className="px-4 py-8 text-center text-sm text-zinc-500">
            No results found.
          </Command.Empty>
        ) : (
          <>
            {GROUP_META.map(({ key, label, route, Icon }) =>
              results[key].length > 0 ? (
                <Command.Group key={key} heading={label}>
                  {results[key].map((item) => (
                    <Command.Item
                      key={`${key}-${item.id}`}
                      value={`${label} ${item.title} ${item.subtitle ?? ""} ${item.id}`}
                      onSelect={() => navigate(getItemHref(key, item.id))}
                      className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-zinc-200 aria-selected:bg-zinc-800"
                    >
                      <Icon className="h-4 w-4 shrink-0 text-zinc-500" />
                      <span className="min-w-0 flex-1 truncate">{item.title}</span>
                      {item.subtitle && (
                        <span className="max-w-[40%] truncate text-xs text-zinc-500">
                          {item.subtitle}
                        </span>
                      )}
                    </Command.Item>
                  ))}
                </Command.Group>
              ) : null
            )}
            <Command.Empty />
          </>
        )}
      </Command.List>

      <div className="border-t border-zinc-800 px-4 py-2.5 text-xs text-zinc-500">
        Type to search customers, jobs, invoices, quotes
      </div>
    </Command.Dialog>
  );
}
