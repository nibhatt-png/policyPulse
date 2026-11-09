"use client";
import { useEffect, useState } from "react";
import SiteHeader from "../SiteHeader";
import { BillList, SummaryParagraph, formatDate, getJSON, type BillSummary } from "../bills";

type Section = { key: string; label: string; description: string; bills: BillSummary[] };
type WhatsNew = { start: string | null; end: string | null; days: number; sections: Section[] };

const PERIODS = [
  { days: 7, label: "This week" },
  { days: 30, label: "Last 30 days" },
];

export default function WhatsNewPage() {
  const [days, setDays] = useState(7);
  // results are tagged with the period they're for, so switching periods
  // shows "Loading" until the new one arrives
  const [result, setResult] = useState<{ days: number; data?: WhatsNew; error?: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getJSON<WhatsNew>(`/whats-new?days=${days}`)
      .then((data) => { if (!cancelled) setResult({ days, data }); })
      .catch((e) => { if (!cancelled) setResult({ days, error: e.message }); });
    return () => { cancelled = true; };
  }, [days]);

  const current = result?.days === days ? result : null;
  const data = current?.data ?? null;
  const error = current?.error ?? "";

  const total = data?.sections.reduce((n, s) => n + s.bills.length, 0) ?? 0;

  return (
    <div className="min-h-screen bg-gray-50">
      <SiteHeader />
      <main className="max-w-3xl mx-auto px-4 py-8">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">What&apos;s new in Congress</h1>
            <p className="text-gray-500 mt-1">
              {data?.start && data?.end
                ? `${formatDate(data.start)} – ${formatDate(data.end)}`
                : "New laws, votes and bills"}
            </p>
          </div>
          <div className="flex rounded-full bg-white border p-1 text-sm">
            {PERIODS.map((p) => (
              <button
                key={p.days}
                onClick={() => setDays(p.days)}
                className={
                  "px-3 py-1 rounded-full font-medium transition " +
                  (days === p.days ? "bg-emerald-600 text-white" : "text-gray-600 hover:text-gray-900")
                }
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {error && <p className="text-red-500">{error}</p>}
        {!data && !error && <p className="text-gray-400">Loading…</p>}

        {data && (
          <>
            {total > 0 && (
              <div className="mb-8">
                <SummaryParagraph path={`/whats-new/summary?days=${days}`} label={days === 7 ? "The week in brief" : "The month in brief"} />
              </div>
            )}
            {total === 0 && (
              <p className="text-gray-600 mb-8">
                No bills moved in this period. Congress may be in recess; try the last 30 days.
              </p>
            )}
            <div className="space-y-8">
              {data.sections.map((s) => (
                <section key={s.key}>
                  <div className="flex items-baseline gap-2 mb-1">
                    <h2 className="text-lg font-bold text-gray-900">{s.label}</h2>
                    <span className="text-sm text-gray-400">{s.bills.length}</span>
                  </div>
                  <p className="text-sm text-gray-500 mb-3">{s.description}</p>
                  {s.bills.length ? (
                    <BillList bills={s.bills} initial={s.key === "introduced" ? 6 : 10} showStatus={false} />
                  ) : (
                    <p className="text-sm text-gray-400 italic">None in this period.</p>
                  )}
                </section>
              ))}
            </div>
            <p className="mt-10 text-xs text-gray-400">
              Based on each bill&apos;s latest action on Congress.gov, up to {formatDate(data.end)}. Committee
              activity isn&apos;t listed, since the database only keeps bills that passed a chamber or were
              introduced in the last 4 months.
            </p>
          </>
        )}
      </main>
    </div>
  );
}
