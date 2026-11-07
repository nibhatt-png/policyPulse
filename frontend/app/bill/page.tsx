"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import Markdown from "../Markdown";
import { CongressBadge, formatDate } from "../bills";

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
};

export default function BillPage() {
  const params  = useSearchParams();
  const billUrl = params.get("url");

  const [bill, setBill]       = useState<BillDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");

  useEffect(() => {
    if (!billUrl) return;
    fetch(`http://localhost:8000/bill?url=${encodeURIComponent(billUrl)}`)
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
      <header className="bg-white border-b px-6 py-4 flex items-center gap-3">
        <Link href="/" className="text-green-600 text-sm hover:underline">
          Back to PolicyPulse
        </Link>
      </header>

      <div className="max-w-3xl mx-auto px-4 py-8">
        <div className="bg-white rounded-2xl border shadow-sm p-8">
          {bill.bill_number && (
            <p className="text-sm font-semibold text-emerald-700 mb-1">{bill.bill_number}</p>
          )}
          {bill.title && (
            <h1 className="text-2xl font-bold text-gray-900 leading-tight mb-3">{bill.title}</h1>
          )}
          <div className="flex items-center gap-2 mb-4">
            <CongressBadge congress={bill.congress} />
            <span className="text-gray-400 text-xs">{bill.source_name}</span>
          </div>
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
              href={bill.url}
              target="_blank"
              className="text-green-600 text-sm hover:underline"
            >
              View original bill on Congress.gov
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}