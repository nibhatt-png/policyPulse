"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import SiteHeader from "../SiteHeader";
import { getJSON } from "../bills";

type TopicCard = {
  slug: string;
  name: string;
  icon: string;
  description: string;
  bills: number;
  passed: number;
  laws: number;
};

export default function TopicsPage() {
  const [topics, setTopics] = useState<TopicCard[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getJSON<{ topics: TopicCard[] }>("/topics")
      .then((d) => setTopics(d.topics))
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <SiteHeader />
      <main className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900">Browse by topic</h1>
        <p className="text-gray-500 mt-1 mb-8">See what Congress is working on, without needing to know what to ask.</p>

        {error && <p className="text-red-500">{error}</p>}
        {!topics && !error && <p className="text-gray-400">Loading…</p>}

        {topics && (
          <div className="grid sm:grid-cols-2 gap-3">
            {topics.map((t) => (
              <Link
                key={t.slug}
                href={`/topics/${t.slug}`}
                className="group p-5 rounded-2xl border border-gray-200 bg-white hover:border-emerald-400 hover:shadow-sm transition flex gap-4"
              >
                <span className="text-2xl leading-none mt-0.5" aria-hidden>{t.icon}</span>
                <div className="min-w-0">
                  <p className="font-semibold text-gray-900 group-hover:text-emerald-700">{t.name}</p>
                  <p className="text-sm text-gray-500 leading-snug mt-0.5">{t.description}</p>
                  <p className="text-xs text-gray-400 mt-2">
                    {t.bills} bill{t.bills === 1 ? "" : "s"}
                    {t.passed > 0 && ` · ${t.passed} passed a chamber`}
                    {t.laws > 0 && ` · ${t.laws} became law`}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
