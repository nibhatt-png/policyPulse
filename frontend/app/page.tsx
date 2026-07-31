"use client";
import { useState, useRef, useEffect } from "react";

type Source = {
  source: string;
  doc_type: string;
  date: string;
  content: string;
  url: string;
  similarity: number;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
};

function Logo({ className = "w-9 h-9 text-lg" }: { className?: string }) {
  return (
    <div
      className={`shrink-0 rounded-2xl bg-linear-to-br from-emerald-500 to-teal-600 shadow-sm shadow-emerald-500/30 flex items-center justify-center transition-transform hover:rotate-6 hover:scale-105 ${className}`}
    >
      <span className="leading-none">🌿</span>
    </div>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4">
      <path
        d="M12 19V5M12 5L6 11M12 5L18 11"
        stroke="currentColor"
        strokeWidth={2.25}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ChevronIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={`w-3.5 h-3.5 ${className}`}>
      <path
        d="M9 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ExternalLinkIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-3 h-3">
      <path
        d="M7 17L17 7M17 7H9M17 7V15"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="w-3.5 h-3.5">
      <path
        d="M7 3.5h7l4 4V20a1 1 0 01-1 1H7a1 1 0 01-1-1V4.5a1 1 0 011-1z"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinejoin="round"
      />
      <path d="M14 3.5V8h4" stroke="currentColor" strokeWidth={1.75} strokeLinejoin="round" />
    </svg>
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

    const history = newMessages.slice(-6).map((m) => ({
      role: m.role,
      content: m.content,
    }));

    const resp = await fetch("http://localhost:8000/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
    });
    const data = await resp.json();

    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: data.answer, sources: data.sources },
    ]);
    setLoading(false);
  }

  const suggestions = [
    "What bills address climate change?",
    "What does Congress say about student loans?",
    "How is Congress handling gun control?",
    "What legislation exists for healthcare costs?",
  ];

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-10 backdrop-blur-md bg-card/70 border-b border-card-border px-6 py-3.5 flex items-center gap-3">
        <Logo />
        <div>
          <h1 className="font-heading text-base font-bold tracking-tight text-foreground leading-none">
            PolicyPulse
          </h1>
          <p className="text-xs text-foreground/60 mt-1">
            Ask anything about US legislation 🍃
          </p>
        </div>
      </header>

      <div className="chat-scroll flex-1 overflow-y-auto px-4 py-8">
        <div className="max-w-3xl mx-auto w-full h-full flex flex-col">
          {messages.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center py-10">
              <Logo className="w-16 h-16 text-3xl mb-5 rounded-3xl" />
              <p className="font-heading text-3xl font-bold tracking-tight text-foreground mb-2">
                What do you want to know? <span className="inline-block">✨</span>
              </p>
              <p className="text-foreground/60 mb-10 italic">
                Ask about any US legislation in plain English.
              </p>
              <div className="grid sm:grid-cols-2 gap-3 w-full max-w-xl">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => setInput(s)}
                    className="group text-left p-4 rounded-2xl border border-card-border bg-card/80 hover:border-emerald-400 hover:bg-emerald-50/60 hover:-translate-y-0.5 hover:shadow-md hover:shadow-emerald-500/10 transition-all duration-200 text-sm text-foreground/80 flex items-center justify-between gap-2"
                  >
                    <span>{s}</span>
                    <ChevronIcon className="shrink-0 text-emerald-500 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200" />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex items-start gap-3 ${
                    msg.role === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  {msg.role === "assistant" && <Logo className="w-7 h-7 text-sm mt-0.5 rounded-xl" />}

                  <div className="max-w-2xl min-w-0">
                    <div
                      className={`px-4 py-3 rounded-3xl text-[15px] leading-relaxed whitespace-pre-wrap ${
                        msg.role === "user"
                          ? "bg-linear-to-br from-emerald-600 to-teal-600 text-white shadow-sm shadow-emerald-600/20 rounded-br-md"
                          : "bg-card border border-card-border text-foreground/90 shadow-sm rounded-bl-md"
                      }`}
                    >
                      {msg.content}
                    </div>

                    {msg.sources && msg.sources.length > 0 && (
                      <details className="mt-2 group/src">
                        <summary className="inline-flex items-center gap-1.5 font-heading text-xs font-medium text-foreground/50 hover:text-emerald-600 cursor-pointer transition ml-1 select-none">
                          <DocIcon />
                          {msg.sources.length} source
                          {msg.sources.length > 1 ? "s" : ""}
                          <ChevronIcon className="transition-transform group-open/src:rotate-90" />
                        </summary>
                        <div className="mt-2 space-y-2">
                          {msg.sources.map((s, j) => (
                            <div
                              key={j}
                              className="p-3 rounded-2xl border border-card-border bg-card hover:border-emerald-300 hover:shadow-sm transition text-xs"
                            >
                              <div className="flex items-center justify-between gap-2 mb-1.5">
                                <p className="font-heading font-semibold text-foreground/80 truncate">
                                  {s.source}
                                </p>
                                <span className="shrink-0 text-foreground/40 text-[11px]">
                                  {s.date}
                                </span>
                              </div>
                              <span className="inline-block mb-2 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-heading font-medium uppercase tracking-wide">
                                {s.doc_type}
                              </span>
                              <p className="text-foreground/60 leading-relaxed">
                                {s.content.slice(0, 250)}...
                              </p>
                              <a
                                href={s.url}
                                target="_blank"
                                className="mt-2 inline-flex items-center gap-1 text-emerald-600 hover:underline font-heading font-medium"
                              >
                                View source
                                <ExternalLinkIcon />
                              </a>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex items-start gap-3 justify-start">
                  <Logo className="w-7 h-7 text-sm mt-0.5 rounded-xl" />
                  <div className="bg-card border border-card-border rounded-3xl rounded-bl-md px-4 py-3.5 shadow-sm">
                    <div className="flex gap-1">
                      <span
                        className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce"
                        style={{ animationDelay: "0ms" }}
                      />
                      <span
                        className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce"
                        style={{ animationDelay: "150ms" }}
                      />
                      <span
                        className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce"
                        style={{ animationDelay: "300ms" }}
                      />
                    </div>
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </div>

      <div className="sticky bottom-0 border-t border-card-border bg-card/80 backdrop-blur-md px-4 py-4">
        <div className="max-w-3xl mx-auto flex items-center gap-1.5 bg-card border border-card-border rounded-full shadow-sm focus-within:ring-2 focus-within:ring-emerald-500/40 focus-within:border-emerald-400 transition pl-5 pr-1.5 py-1.5">
          <input
            className="flex-1 min-w-0 bg-transparent text-[15px] py-2 focus:outline-none placeholder:text-foreground/40 text-foreground"
            placeholder="Ask about any legislation..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
          />
          <button
            onClick={ask}
            disabled={loading || !input.trim()}
            aria-label="Send"
            className="shrink-0 w-9 h-9 rounded-full bg-linear-to-br from-emerald-600 to-teal-600 text-white flex items-center justify-center hover:brightness-110 active:scale-95 disabled:opacity-40 disabled:pointer-events-none transition shadow-sm shadow-emerald-600/20"
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  );
}
