// Shared display helpers for bills.

export function ordinal(n: number) {
  const s = n % 100 >= 10 && n % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${s}`;
}

// Each Congress starts January 3 of an odd year; the 1st began in 1789.
export function currentCongress(today = new Date()) {
  const beforeJan3 = today.getMonth() === 0 && today.getDate() < 3;
  const year = today.getFullYear() - (beforeJan3 ? 1 : 0);
  const startYear = year % 2 === 1 ? year : year - 1;
  return Math.floor((startYear - 1789) / 2) + 1;
}

// "2026-10-29" -> "Oct 29, 2026" (parsed as a calendar date, not shifted by time zone)
export function formatDate(iso: string | null | undefined) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function CongressBadge({ congress }: { congress: number | null | undefined }) {
  if (!congress) return null;
  const current = congress === currentCongress();
  return (
    <span
      title={current ? "Current Congress" : "Past Congress: bills that didn't become law are no longer active"}
      className={
        "px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide " +
        (current ? "bg-emerald-50 text-emerald-700" : "bg-gray-100 text-gray-500")
      }
    >
      {ordinal(congress)} Congress
    </span>
  );
}
