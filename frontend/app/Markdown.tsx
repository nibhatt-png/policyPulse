"use client";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  h1: ({ children }) => <h2 className="text-lg font-bold text-gray-900 mt-5 mb-2 first:mt-0">{children}</h2>,
  h2: ({ children }) => <h2 className="text-lg font-bold text-gray-900 mt-5 mb-2 first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="text-base font-semibold text-gray-900 mt-4 mb-1.5 first:mt-0">{children}</h3>,
  h4: ({ children }) => <h4 className="font-semibold text-gray-900 mt-3 mb-1 first:mt-0">{children}</h4>,
  p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-5 mb-3 space-y-1 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 mb-3 space-y-1 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-emerald-600 hover:underline">
      {children}
    </a>
  ),
  hr: () => <hr className="my-4 border-gray-200" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-emerald-300 pl-3 text-gray-600 mb-3">{children}</blockquote>
  ),
  code: ({ children }) => <code className="px-1 py-0.5 rounded bg-gray-100 text-[0.9em]">{children}</code>,
  table: ({ children }) => (
    <div className="overflow-x-auto mb-3 last:mb-0 rounded-xl border border-gray-200">
      <table className="w-full text-left border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-gray-50">{children}</thead>,
  th: ({ children }) => <th className="px-3 py-2 font-semibold text-gray-900 border-b border-gray-200 align-top">{children}</th>,
  td: ({ children }) => <td className="px-3 py-2 border-b border-gray-100 align-top">{children}</td>,
};

export default function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  );
}
