"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export function Logo({ className = "w-9 h-9 text-lg" }: { className?: string }) {
  return (
    <div className={`shrink-0 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 shadow-sm flex items-center justify-center ${className}`}>
      <span className="leading-none">🌿</span>
    </div>
  );
}

const NAV = [
  { href: "/", label: "Ask" },
  { href: "/new", label: "What's new" },
  { href: "/topics", label: "Topics" },
];

export default function SiteHeader() {
  const path = usePathname();
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));
  return (
    <header className="sticky top-0 z-10 bg-white border-b border-gray-200 px-4 sm:px-6 py-3 flex items-center gap-3">
      <Link href="/" className="flex items-center gap-3 min-w-0">
        <Logo className="w-9 h-9 text-lg" />
        <div className="hidden sm:block">
          <p className="text-base font-bold text-gray-900 leading-tight">PolicyPulse</p>
          <p className="text-xs text-gray-500">US legislation in plain English</p>
        </div>
      </Link>
      <nav className="ml-auto flex items-center gap-1">
        {NAV.map((n) => (
          <Link
            key={n.href}
            href={n.href}
            className={
              "px-3 py-1.5 rounded-full text-sm font-medium transition " +
              (active(n.href) ? "bg-emerald-50 text-emerald-700" : "text-gray-600 hover:text-gray-900 hover:bg-gray-50")
            }
          >
            {n.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
