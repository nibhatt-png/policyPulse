"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Markdown from "../Markdown";
import SiteHeader from "../SiteHeader";
import Link from "next/link";
import { API, CongressBadge, RulingBadge, billPageHref, congressGovUrl, formatDate, getJSON, isRuling } from "../bills";

type RelatedItem = {
  url: string;
  title: string | null;
  bill_number: string | null;
  source_name: string | null;
  date: string | null;
  latest_action: string | null;
  latest_action_date: string | null;
  shared: string[];   // U.S. Code sections this item and the page's document both involve
};
type RelatedResponse = { kind: "ruling" | "legislation" | null; items: RelatedItem[] };

function StatuteChip({ statute }: { statute: string }) {
  return (
    <span className="px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 text-[11px] font-medium whitespace-nowrap">
      {statute}
    </span>
  );
}

// Bills and rulings are linked through the U.S. Code sections they share: the
// sections a bill cites (mostly ones it amends) and the ones a ruling interprets.
function Related({ url, isRulingPage }: { url: string; isRulingPage: boolean }) {
  const [data, setData] = useState<{ url: string; res: RelatedResponse } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getJSON<RelatedResponse>(`/related?url=${encodeURIComponent(url)}`)
      .then((res) => { if (!cancelled) setData({ url, res }); })
      .catch(() => { /* optional section: leave it out if it fails */ });
    return () => { cancelled = true; };
  }, [url]);

  const res = data?.url === url ? data.res : null;
  if (!res || !res.kind) return null;   // loading, failed, or nothing to link on

  const heading = isRulingPage ? "Bills that would change this law" : "How courts have read the laws this bill changes";
  const note = isRulingPage
    ? "Current bills that cite the statutes this ruling interprets."
    : "Federal court rulings on U.S. Code sections this bill cites. They describe the law as it stands; the bill would change it.";

  return (
    <section className="mt-8 pt-6 border-t border-gray-200">
      <h2 className="text-lg font-bold text-gray-900">{heading}</h2>
      <p className="text-sm text-gray-500 mt-1 mb-4">{note}</p>
      {res.items.length === 0 ? (
        <p className="text-sm text-gray-500">
          {isRulingPage
            ? "No current bills in PolicyPulse cite these statutes."
            : "PolicyPulse doesn't have court rulings on these laws yet. More are added every day."}
        </p>
      ) : (
        <ul className="space-y-2">
          {res.items.map((it) => (
            <li key={it.url} className={`rounded-xl border px-4 py-3 ${isRulingPage ? "border-gray-200" : "border-indigo-100 border-l-4 border-l-indigo-400"}`}>
              <Link href={billPageHref(it.url)} className={`font-semibold text-[14px] leading-snug text-gray-900 hover:underline ${isRulingPage ? "" : "italic"}`}>
                {isRulingPage ? [it.bill_number, it.title].filter(Boolean).join(": ") : it.title}
              </Link>
              <p className="text-xs text-gray-500 mt-0.5">
                {isRulingPage
                  ? it.latest_action_date ? `Latest action ${formatDate(it.latest_action_date)}: ${it.latest_action ?? ""}` : it.latest_action
                  : `${it.source_name ?? ""}${it.date ? ` · Decided ${formatDate(it.date)}` : ""}`}
              </p>
              <div className="flex flex-wrap items-center gap-1 mt-1.5">
                <span className="text-[11px] text-gray-500">{isRulingPage ? "Cites" : "Interprets"}</span>
                {it.shared.slice(0, 4).map((t) => <StatuteChip key={t} statute={t} />)}
                {it.shared.length > 4 && <span className="text-[11px] text-gray-400">+{it.shared.length - 4} more</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

type BillDetail = {
  summary: string;
  source_name: string;
  doc_type: string;
  date: string;
  url: string;
  chunks: number;
  title: string | null;
  bill_number: string | null;
  congress: number | null;
  latest_action: string | null;
  latest_action_date: string | null;
  statutes?: string[];   // for a ruling: the U.S. Code sections it interprets
};

export default function BillPage() {
  const params  = useSearchParams();
  const billUrl = params.get("url");

  const [bill, setBill]       = useState<BillDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");

  useEffect(() => {
    if (!billUrl) return;
    fetch(`${API}/bill?url=${encodeURIComponent(billUrl)}`)
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail ?? `Server error (${r.status}).`);
        return data;
      })
      .then((data) => {
        if (data.error) setError(data.error);
        else setBill(data);
      })
      .catch((err) => {
        setError(err instanceof TypeError ? "Couldn't reach the API. Is it running on port 8000?" : err.message);
      })
      .finally(() => setLoading(false));
  }, [billUrl]);

  if (loading) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-center">
        <div className="text-4xl mb-4">🌿</div>
        <p className="text-gray-500">Generating plain English summary...</p>
      </div>
    </div>
  );

  if (error) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <p className="text-red-500">{error}</p>
    </div>
  );

  if (!bill) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      <SiteHeader />

      <div className="max-w-3xl mx-auto px-4 py-8">
        <div className="bg-white rounded-2xl border shadow-sm p-8">
          {bill.bill_number && (
            <p className="text-sm font-semibold text-emerald-700 mb-1">{bill.bill_number}</p>
          )}
          {bill.title && (
            <h1 className="text-2xl font-bold text-gray-900 leading-tight mb-3">{bill.title}</h1>
          )}
          <div className="flex items-center gap-2 mb-4">
            {isRuling(bill) ? <RulingBadge date={bill.date} /> : <CongressBadge congress={bill.congress} />}
            <span className="text-gray-400 text-xs">
              {bill.source_name}
              {isRuling(bill) && bill.date ? ` · decided ${formatDate(bill.date)}` : ""}
            </span>
          </div>
          {isRuling(bill) && bill.statutes && bill.statutes.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 mb-6">
              <span className="text-xs text-gray-500">Interprets</span>
              {bill.statutes.map((t) => <StatuteChip key={t} statute={t} />)}
            </div>
          )}
          {bill.latest_action && (
            <div className="mb-6 rounded-xl bg-gray-50 border border-gray-200 px-4 py-3 text-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">
                Latest action{bill.latest_action_date ? ` · ${formatDate(bill.latest_action_date)}` : ""}
              </p>
              <p className="text-gray-700">{bill.latest_action}</p>
            </div>
          )}

          <div className="text-sm text-gray-700 leading-relaxed">
            <Markdown>{bill.summary}</Markdown>
          </div>

          <div className="mt-8 pt-6 border-t">
            <a
              href={congressGovUrl(bill.url)}
              target="_blank"
              rel="noreferrer"
              className="text-green-600 text-sm hover:underline"
            >
              {isRuling(bill) ? "Read the full opinion on CourtListener" : "View original bill on Congress.gov"}
            </a>
          </div>

          <Related url={bill.url} isRulingPage={isRuling(bill)} />
        </div>
      </div>
    </div>
  );
}