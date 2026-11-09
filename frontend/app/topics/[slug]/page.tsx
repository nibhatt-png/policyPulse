"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import SiteHeader from "../../SiteHeader";
import { BillList, SummaryParagraph, formatDate, getJSON, type BillSummary } from "../../bills";

type Group = { status: number; label: string; bills: BillSummary[] };
type Topic = {
  slug: string;
  name: string;
  icon: string;
  description: string;
  as_of: string | null;
  total: number;
  groups: Group[];
};

const GROUP_NOTES: Record<number, string> = {
  5: "Signed into law.",
  4: "Passed both chambers; waiting for the President.",
  3: "Approved by the House or the Senate, and waiting on the other.",
  2: "Approved by a committee or scheduled for a floor vote.",
  1: "Proposed in the last 4 months. Most bills never get a vote.",
};

export default function TopicPage() {
  const { slug } = useParams<{ slug: string }>();
  const [topic, setTopic] = useState<Topic | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getJSON<Topic>(`/topics/${slug}`)
      .then(setTopic)
      .catch((e) => setError(e.message));
  }, [slug]);

  return (
    <div className="min-h-screen bg-gray-50">
      <SiteHeader />
      <main className="max-w-3xl mx-auto px-4 py-8">
        <Link href="/topics" className="text-sm text-emerald-700 hover:underline">← All topics</Link>

        {error && <p className="text-red-500 mt-6">{error}</p>}
        {!topic && !error && <p className="text-gray-400 mt-6">Loading…</p>}

        {topic && (
          <>
            <div className="flex items-start gap-4 mt-4 mb-6">
              <span className="text-4xl leading-none" aria-hidden>{topic.icon}</span>
              <div>
                <h1 className="text-3xl font-bold text-gray-900">{topic.name}</h1>
                <p className="text-gray-500 mt-1">{topic.description}</p>
              </div>
            </div>

            {topic.total > 0 ? (
              <>
                <div className="mb-8">
                  <SummaryParagraph path={`/topics/${topic.slug}/summary`} label="Where things stand" />
                </div>
                <div className="space-y-8">
                  {topic.groups.map((g) => (
                    <section key={g.status}>
                      <div className="flex items-baseline gap-2 mb-1">
                        <h2 className="text-lg font-bold text-gray-900">{g.label}</h2>
                        <span className="text-sm text-gray-400">{g.bills.length}</span>
                      </div>
                      <p className="text-sm text-gray-500 mb-3">{GROUP_NOTES[g.status]}</p>
                      <BillList bills={g.bills} initial={g.status >= 3 ? 8 : 5} showStatus={false} />
                    </section>
                  ))}
                </div>
                <p className="mt-10 text-xs text-gray-400">
                  {`${topic.total} current bills, grouped by Congress.gov's policy areas` +
                    (topic.as_of ? `, as of ${formatDate(topic.as_of)}` : "") +
                    ". Bills from the last few weeks appear once the Congressional Research Service assigns their policy area."}
                </p>
              </>
            ) : (
              <p className="text-gray-600">No current bills on this topic yet.</p>
            )}
          </>
        )}
      </main>
    </div>
  );
}
