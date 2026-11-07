"use client";
import { useState, useRef, useEffect } from "react";
import Markdown from "./Markdown";
import { CongressBadge, formatDate } from "./bills";

type Source = {
  source: string;
  doc_type: string;
  date: string;
  content: string;
  url: string;
  similarity: number;
  title: string | null;
  bill_number: string | null;
  congress: number | null;
  latest_action: string | null;
  latest_action_date: string | null;
};

// "H.R. 132: Protecting Local Communities from Harmful Algal Blooms Act"
function billLabel(s: { title: string | null; bill_number: string | null; source: string }) {
  return [s.bill_number, s.title].filter(Boolean).join(": ") || s.source;
}

// Drop the "118TH CONGRESS 2D SESSION H. R. 132" header every bill's text starts with.
// Bill text opens with procedural boilerplate ("118TH CONGRESS H. R. 132",
// "____ IN THE SENATE OF THE UNITED STATES Received; read twice...",
// "[Page 140 STAT. 1162]"). The useful part is the purpose line ("To provide
// for..."), so start the excerpt there when it's near the top.
function excerpt(content: string, max = 220) {
  let text = content
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/\[Page [^\]]*\]/g, " ")
    .replace(/<<NOTE:[^>]*>>/g, " ")
    .replace(/_{3,}/g, " ")
    .replace(/^\s*\d+(ST|ND|RD|TH) CONGRESS\s+(\d+(ST|ND|RD|TH|D) SESSION\s+)?/i, "")
    .replace(/^(H|S)\.\s?([A-Z]+\.\s?)*\d+\s+/i, "")
    .replace(/\s+/g, " ")
    .trim();
  const purpose = text.slice(0, 600).search(/\bTo [a-z]/);
  if (purpose > 0) text = text.slice(purpose);
  return text.length > max ? text.slice(0, max).trimEnd() + "…" : text;
}

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
};

function Logo({ className = "w-9 h-9 text-lg" }: { className?: string }) {
  return (
    <div className={`shrink-0 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 shadow-sm flex items-center justify-center ${className}`}>
      <span className="leading-none">🌿</span>
    </div>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4">
      <path d="M12 19V5M12 5L6 11M12 5L18 11" stroke="currentColor" strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={`w-3.5 h-3.5 ${className}`}>
      <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ExternalLinkIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-3 h-3">
      <path d="M7 17L17 7M17 7H9M17 7V15" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-3.5 h-3.5">
      <path d="M7 3.5h7l4 4V20a1 1 0 01-1 1H7a1 1 0 01-1-1V4.5a1 1 0 011-1z" stroke="currentColor" strokeWidth={1.75} strokeLinejoin="round" />
      <path d="M14 3.5V8h4" stroke="currentColor" strokeWidth={1.75} strokeLinejoin="round" />
    </svg>
  );
}

function SourceCard({ s }: { s: Source }) {
  return (
    <div className="p-3 rounded-2xl border border-gray-200 bg-white hover:border-emerald-300 hover:shadow-sm transition text-xs">
      <p className="font-semibold text-gray-800 text-[13px] leading-snug mb-1.5">{billLabel(s)}</p>
      <div className="flex items-center gap-2 mb-2 text-[11px] text-gray-400">
        <CongressBadge congress={s.congress} />
        <span>{s.source}</span>
      </div>
      {s.latest_action && (
        <p className="text-gray-600 leading-relaxed mb-1.5 line-clamp-2">
          <span className="font-medium text-gray-700">Latest action{s.latest_action_date ? ` (${formatDate(s.latest_action_date)})` : ""}:</span>{" "}
          {s.latest_action}
        </p>
      )}
      <p className="text-gray-500 leading-relaxed line-clamp-2">{excerpt(s.content)}</p>
      <div className="mt-2 flex items-center gap-3">
        <a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-emerald-600 hover:underline font-medium">
          View source <ExternalLinkIcon />
        </a>
        <a href={"/bill?url=" + encodeURIComponent(s.url)} className="inline-flex items-center gap-1 text-emerald-600 hover:underline font-medium">
          Learn more <ChevronIcon />
        </a>
      </div>
    </div>
  );
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function ask() {
    if (!input.trim() || loading) return;
    const question = input;
    setInput("");

    const newMessages: Message[] = [...messages, { role: "user", content: question }];
    setMessages(newMessages);
    setLoading(true);

    const history = newMessages.slice(-6).map((m) => ({ role: m.role, content: m.content }));

    try {
      const resp = await fetch("http://localhost:8000/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail ?? `Server error (${resp.status}).`);
      setMessages((prev) => [...prev, { role: "assistant", content: data.answer, sources: data.sources }]);
    } catch (err) {
      const reason =
        err instanceof TypeError
          ? "Couldn't reach the API. Is it running on port 8000?"
          : err instanceof Error
            ? err.message
            : "Unknown error.";
      setMessages((prev) => [...prev, { role: "assistant", content: `Sorry, I couldn't get an answer. ${reason}` }]);
    } finally {
      setLoading(false);
    }
  }

  const suggestions = [
    "What is Congress doing right now?",
    "What does Congress say about student loans?",
    "How is Congress handling gun control?",
    "What legislation exists for healthcare costs?",
  ];

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <header className="sticky top-0 z-10 bg-white border-b px-6 py-3.5 flex items-center gap-3">
        <Logo className="w-9 h-9 text-lg" />
        <div>
          <h1 className="text-base font-bold text-gray-900">PolicyPulse</h1>
          <p className="text-xs text-gray-500">Ask anything about US legislation</p>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-8">
        <div className="max-w-3xl mx-auto w-full h-full flex flex-col">
          {messages.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center py-10">
              <Logo className="w-16 h-16 text-3xl mb-5 rounded-3xl" />
              <p className="text-3xl font-bold text-gray-800 mb-2">What do you want to know?</p>
              <p className="text-gray-500 mb-10">Ask about any US legislation in plain English.</p>
              <div className="grid sm:grid-cols-2 gap-3 w-full max-w-xl">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => setInput(s)}
                    className="text-left p-4 rounded-2xl border border-gray-200 bg-white hover:border-emerald-400 hover:bg-emerald-50 transition text-sm text-gray-700"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map((msg, i) => (
                <div key={i} className={"flex items-start gap-3 " + (msg.role === "user" ? "justify-end" : "justify-start")}>
                  {msg.role === "assistant" && <Logo className="w-7 h-7 text-sm mt-0.5 rounded-xl" />}
                  <div className="max-w-2xl min-w-0">
                    <div className={"px-4 py-3 rounded-3xl text-sm leading-relaxed " + (msg.role === "user" ? "bg-emerald-600 text-white rounded-br-md whitespace-pre-wrap" : "bg-white border text-gray-800 shadow-sm rounded-bl-md")}>
                      {msg.role === "assistant" ? <Markdown>{msg.content}</Markdown> : msg.content}
                    </div>
                    {msg.sources && msg.sources.length > 0 && (
                      <details className="mt-2">
                        <summary className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-400 hover:text-emerald-600 cursor-pointer transition ml-1 select-none">
                          <DocIcon />
                          {msg.sources.length} source{msg.sources.length > 1 ? "s" : ""}
                        </summary>
                        <div className="mt-2 space-y-2">
                          {msg.sources.map((s, j) => <SourceCard key={j} s={s} />)}
                        </div>
                      </details>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex items-start gap-3">
                  <Logo className="w-7 h-7 text-sm mt-0.5 rounded-xl" />
                  <div className="bg-white border rounded-3xl rounded-bl-md px-4 py-3.5 shadow-sm">
                    <div className="flex gap-1">
                      <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </div>

      <div className="sticky bottom-0 border-t bg-white px-4 py-4">
        <div className="max-w-3xl mx-auto flex items-center gap-2">
          <input
            className="flex-1 border rounded-full px-5 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            placeholder="Ask about any legislation..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
          />
          <button
            onClick={ask}
            disabled={loading || !input.trim()}
            className="w-10 h-10 rounded-full bg-emerald-600 text-white flex items-center justify-center hover:bg-emerald-700 disabled:opacity-40 transition"
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  );
}