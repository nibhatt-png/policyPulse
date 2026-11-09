"use client";
// Shared display helpers for bills.
import { useEffect, useState } from "react";
import Link from "next/link";
import Markdown from "./Markdown";

export function ordinal(n: number) {
  const s = n % 100 >= 10 && n % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${s}`;
}

// Each Congress starts January 3 of an odd year; the 1st began in 1789.
export function currentCongress(today = new Date()) {
  const beforeJan3 = today.getMonth() === 0 && today.getDate() < 3;
  const year = today.getFullYear() - (beforeJan3 ? 1 : 0);
  const startYear = year % 2 === 1 ? year : year - 1;
  return Math.floor((startYear - 1789) / 2) + 1;
}

// "2026-10-29" -> "Oct 29, 2026" (parsed as a calendar date, not shifted by time zone)
export function formatDate(iso: string | null | undefined) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// Federal court opinions from CourtListener (ingest/run_courts.py), stored alongside bills
export function isRuling(s: { doc_type?: string | null }) {
  return s.doc_type === "ruling";
}

export function RulingBadge({ date }: { date?: string | null }) {
  return (
    <span
      title="A federal court decision interpreting a law that bills would change"
      className="px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide bg-indigo-50 text-indigo-700"
    >
      Court ruling{date ? ` · ${date.slice(0, 4)}` : ""}
    </span>
  );
}

export function CongressBadge({ congress }: { congress: number | null | undefined }) {
  if (!congress) return null;
  const current = congress === currentCongress();
  return (
    <span
      title={current ? "Current Congress" : "Past Congress: bills that didn't become law are no longer active"}
      className={
        "px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide " +
        (current ? "bg-emerald-50 text-emerald-700" : "bg-gray-100 text-gray-500")
      }
    >
      {ordinal(congress)} Congress
    </span>
  );
}

// ---- API ------------------------------------------------------------------

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// GET an API path, turning failures into readable messages.
export async function getJSON<T>(path: string): Promise<T> {
  let r: Response;
  try {
    r = await fetch(API + path);
  } catch {
    throw new Error("Couldn't reach the API. Is it running on port 8000?");
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail ?? `Server error (${r.status}).`);
  return data as T;
}

// ---- Bills ----------------------------------------------------------------

export type BillSummary = {
  url: string;
  bill_number: string | null;
  title: string | null;
  latest_action: string | null;
  latest_action_date: string | null;
  introduced_date: string | null;
  policy_area: string | null;
  status: number;
  status_label: string;
};

// Stored URLs are API URLs (api.congress.gov/v3/bill/119/hr/144?format=json),
// which need an API key; link people to the public page instead.
const BILL_PATHS: Record<string, string> = {
  hr: "house-bill", s: "senate-bill",
  hjres: "house-joint-resolution", sjres: "senate-joint-resolution",
  hres: "house-resolution", sres: "senate-resolution",
  hconres: "house-concurrent-resolution", sconres: "senate-concurrent-resolution",
};
export function congressGovUrl(apiUrl: string) {
  const m = apiUrl.match(/\/bill\/(\d+)\/([a-z]+)\/(\d+)/);
  if (!m || !BILL_PATHS[m[2]]) return apiUrl;
  return `https://www.congress.gov/bill/${ordinal(Number(m[1]))}-congress/${BILL_PATHS[m[2]]}/${m[3]}`;
}

export function billPageHref(apiUrl: string) {
  return "/bill?url=" + encodeURIComponent(apiUrl);
}

const STATUS_STYLES: Record<number, string> = {
  5: "bg-emerald-100 text-emerald-800",
  4: "bg-teal-100 text-teal-800",
  3: "bg-sky-100 text-sky-800",
  2: "bg-amber-100 text-amber-800",
  1: "bg-gray-100 text-gray-600",
};

export function StatusPill({ status, label }: { status: number; label: string }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide whitespace-nowrap ${STATUS_STYLES[status] ?? STATUS_STYLES[1]}`}>
      {label}
    </span>
  );
}

export function BillCard({ b, showStatus = true }: { b: BillSummary; showStatus?: boolean }) {
  return (
    <div className="p-4 rounded-2xl border border-gray-200 bg-white hover:border-emerald-300 hover:shadow-sm transition">
      <div className="flex items-start justify-between gap-3 mb-1.5">
        <Link href={billPageHref(b.url)} className="font-semibold text-gray-900 text-[14px] leading-snug hover:text-emerald-700">
          {b.bill_number && <span className="text-emerald-700">{b.bill_number}</span>}
          {b.bill_number && b.title ? ": " : ""}
          {b.title}
        </Link>
        {showStatus && <StatusPill status={b.status} label={b.status_label} />}
      </div>
      {b.latest_action && (
        <p className="text-xs text-gray-600 leading-relaxed line-clamp-2">
          <span className="font-medium text-gray-700">
            {b.latest_action_date ? formatDate(b.latest_action_date) : "Latest action"}:
          </span>{" "}
          {b.latest_action}
        </p>
      )}
      <div className="mt-2 flex items-center gap-4 text-xs">
        <Link href={billPageHref(b.url)} className="text-emerald-600 hover:underline font-medium">
          Plain-English summary →
        </Link>
        <a href={congressGovUrl(b.url)} target="_blank" rel="noreferrer" className="text-gray-400 hover:text-emerald-600 hover:underline">
          Congress.gov ↗
        </a>
      </div>
    </div>
  );
}

// A list that shows the first few bills and expands on request.
export function BillList({ bills, initial = 6, showStatus = true }: { bills: BillSummary[]; initial?: number; showStatus?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? bills : bills.slice(0, initial);
  return (
    <div className="space-y-2">
      {shown.map((b) => <BillCard key={b.url} b={b} showStatus={showStatus} />)}
      {bills.length > initial && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50 rounded-xl transition"
        >
          {expanded ? "Show fewer" : `Show all ${bills.length}`}
        </button>
      )}
    </div>
  );
}

// A cached AI summary paragraph, loaded separately so the bills show first.
export function SummaryParagraph({ path, label = "Summary" }: { path: string; label?: string }) {
  const [attempt, setAttempt] = useState(0);
  // tagged with the request it answers, so a new path or retry shows the loading state
  const key = `${path}#${attempt}`;
  const [result, setResult] = useState<{ key: string; summary?: string; error?: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getJSON<{ summary: string }>(path)
      .then((d) => { if (!cancelled) setResult({ key, summary: d.summary }); })
      .catch((e) => { if (!cancelled) setResult({ key, error: e.message }); });
    return () => { cancelled = true; };
  }, [path, key]);

  const current = result?.key === key ? result : null;
  const summary = current?.summary ?? "";
  const error = current?.error ?? "";

  return (
    <div className="rounded-2xl bg-emerald-50/60 border border-emerald-100 px-5 py-4">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700 mb-2">{label} · AI-generated</p>
      {summary ? (
        <div className="text-[15px] text-gray-800 leading-relaxed"><Markdown>{summary}</Markdown></div>
      ) : error ? (
        <p className="text-sm text-gray-600">
          Couldn&apos;t load the summary. {error}{" "}
          <button onClick={() => setAttempt(attempt + 1)} className="text-emerald-700 font-medium hover:underline">Try again</button>
        </p>
      ) : (
        <div className="space-y-2 animate-pulse" aria-label="Loading summary">
          <div className="h-3 bg-emerald-100 rounded w-full" />
          <div className="h-3 bg-emerald-100 rounded w-11/12" />
          <div className="h-3 bg-emerald-100 rounded w-4/5" />
        </div>
      )}
    </div>
  );
}
