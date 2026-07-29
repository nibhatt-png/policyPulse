"use client";
import { useState } from "react";

type Source = {
  source: string;
  doc_type: string;
  date: string;
  content: string;
  url: string;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
};

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);

  async function ask() {
    if (!input.trim()) return;
    const question = input;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    const resp = await fetch("http://localhost:8000/ask", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ question }),
    });
    const data = await resp.json();

    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: data.answer, sources: data.sources },
    ]);
    setLoading(false);
  }

  return (
    <main className="max-w-3xl mx-auto p-6 min-h-screen flex flex-col">
      <h1 className="text-3xl font-bold mb-1">🌿 PolicyPulse</h1>
      <p className="text-gray-500 mb-6">Ask questions about environmental legislation.</p>

      <div className="flex-1 space-y-4 mb-6">
        {messages.map((msg, i) => (
          <div key={i}>
            <div className={`p-4 rounded-lg ${msg.role === "user" ? "bg-blue-50 ml-8" : "bg-gray-50 mr-8"}`}>
              <p className="text-sm font-semibold mb-1">{msg.role === "user" ? "You" : "PolicyPulse"}</p>
              <p className="whitespace-pre-wrap">{msg.content}</p>
            </div>
            {msg.sources && msg.sources.length > 0 && (
              <details className="mt-2 mr-8">
                <summary className="text-sm text-gray-500 cursor-pointer">
                  📄 {msg.sources.length} sources
                </summary>
                <div className="mt-2 space-y-2">
                  {msg.sources.map((s, j) => (
                    <div key={j} className="p-3 bg-white border rounded text-sm">
                      <p className="font-medium">{s.source} — {s.doc_type} — {s.date}</p>
                      <p className="text-gray-600 mt-1">{s.content.slice(0, 200)}...</p>
                      <a href={s.url} target="_blank" className="text-blue-500 text-xs mt-1 block">
                        View source →
                      </a>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        ))}
        {loading && (
          <div className="bg-gray-50 p-4 rounded-lg mr-8">
            <p className="text-gray-400">Searching documents...</p>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <input
          className="flex-1 border rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-green-500"
          placeholder="Ask about environmental policy..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
        />
        <button
          onClick={ask}
          className="bg-green-600 text-white px-6 py-3 rounded-lg hover:bg-green-700"
        >
          Ask
        </button>
      </div>
    </main>
  );
}