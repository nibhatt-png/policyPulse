"""CourtListener (Free Law Project): federal court opinions that cite a statute.

API docs (v4): https://wiki.free.law/c/courtlistener/help/api/rest/v4/overview

Things checked against the live API on 2026-11-07, not just the docs:
  - A free account gets 5 requests/minute, 50/hour and 125/day (see
    /api/rest/v4/api-usage/, which doesn't count against them).
  - Statutes must be searched as phrases in `q`. The citation lookup API only
    handles case citations. "42 U.S.C. § 5122" matches; "§5122" (no space)
    matches nothing, so the query is ("T U.S.C. § S" OR "T U.S.C. S").
  - `court=scotus ca1 ...` (space-separated) filters courts; case-law search
    returns published opinions only unless told otherwise.
  - `order_by=citeCount desc` and `dateFiled desc` both work.
  - The opinions endpoint has no filter for several ids at once, so each
    opinion's text costs one request. Texts are cached on disk so a dry run's
    downloads aren't paid for again by the real run.
  - The same case often appears as several clusters (from different sources);
    case_key() collapses them.

The API key goes only in the Authorization header, never in a URL or a log line.
"""
import html, json, os, re, time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import httpx
from dotenv import load_dotenv
load_dotenv()

BASE = "https://www.courtlistener.com/api/rest/v4"
SITE = "https://www.courtlistener.com"

# Supreme Court and the 13 federal courts of appeals
COURTS = ["scotus", "ca1", "ca2", "ca3", "ca4", "ca5", "ca6", "ca7", "ca8", "ca9",
          "ca10", "ca11", "cadc", "cafc"]
# "relevant" is CourtListener's BM25 score, which favors opinions that discuss
# the statute at length over landmark cases that mention it once
ORDER  = {"cited": "citeCount desc", "recent": "dateFiled desc", "relevant": "score desc"}

MIN_INTERVAL = 12.5      # seconds between requests: stays under 5/minute
MAX_WAIT     = 65 * 60   # wait out the hourly limit; stop the run for the daily one
ATTEMPTS     = 5
CACHE_DIR    = Path(__file__).resolve().parents[2] / ".cache" / "courtlistener"

TEXT_FIELDS = ["plain_text", "html_with_citations", "html", "html_lawbox",
               "html_columbia", "html_anon_2020", "xml_harvard"]
# The opinion that speaks for the court, best first. Search results label
# types "lead-opinion" etc.; the opinions endpoint uses codes like "020lead".
# A search result lists only the opinions that matched the query, so a case
# whose only match is a concurrence or dissent has none of these and is skipped:
# the court's own opinion doesn't cite the statute (verified on Mathis v. United States).
MAIN_OPINION_TYPES = ["combined-opinion", "010combined", "lead-opinion", "020lead",
                      "unanimous-opinion", "015unamimous", "015unanimous",
                      "plurality-opinion", "025plurality"]

class BudgetExhausted(Exception):
    """This run's request budget, or the account's quota, is used up."""

@dataclass
class Case:
    cluster_id: int
    case_name: str
    court: str              # e.g. "Court of Appeals for the Fifth Circuit"
    court_id: str
    date: str | None        # decision date
    docket_number: str
    cite_count: int
    url: str                # the case's page on CourtListener
    opinions: list[dict] = field(default_factory=list)   # [{"id", "type"}]

    @property
    def key(self) -> str:
        return case_key(self.court, self.date, self.docket_number, self.case_name)

    @property
    def keys(self) -> set[str]:
        return case_keys(self.court, self.date, self.docket_number, self.case_name)

    def main_opinion_id(self) -> int | None:
        """The court's opinion, if it's among the matches (None: only a separate opinion cites the statute)."""
        for t in MAIN_OPINION_TYPES:
            for o in self.opinions:
                if o.get("type") == t:
                    return o["id"]
        return None

def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def case_key(court: str, date, docket_number: str | None, case_name: str | None) -> str:
    """One key for a case, used to collapse duplicates within a search."""
    return f"{court}|{date}|{_norm(docket_number) or _norm(case_name)[:40]}"

def case_keys(court: str, date, docket_number: str | None, case_name: str | None) -> set[str]:
    """Keys that identify a case across CourtListener's duplicate clusters:
    same court and decision date, plus the same docket number OR the same
    name. Either alone misses some: duplicates can have differently written
    docket numbers ("361" vs "Docket No. 03-9062-CV", Gulino v. NYSED) or
    different names (In re World Trade Center vs McCue, same docket)."""
    keys = {f"{court}|{date}|name:{_norm(case_name)[:40]}"} if _norm(case_name) else set()
    if _norm(docket_number):
        keys.add(f"{court}|{date}|docket:{_norm(docket_number)}")
    return keys

def clean_case_name(name: str) -> str:
    """Drop reporter citations some clusters put before the name
    ("16 Fair empl.prac.cas. 894, 16 Empl. Prac. Dec. P 8115 Richard Jerome Johnson v. ...")
    and shorten very long captions."""
    name = re.sub(r"^(?:\d+\s+[A-Za-z][A-Za-z.'\s&]*?\s+(?:P\s+)?\d+,?\s+)+", "", name.strip())
    if len(name) > 120:
        cut = name[:120].rsplit(",", 1)[0] if " v. " in name[:120] else name[:120].rsplit(" ", 1)[0]
        name = cut.rstrip(" ,") + "…"
    return name

def statute_query(statute: str) -> str:
    """'42 U.S.C. § 5122' -> ("42 U.S.C. § 5122" OR "42 U.S.C. 5122")"""
    bare = statute.replace("§ ", "")
    return f'("{statute}" OR "{bare}")'

class Client:
    def __init__(self, max_requests: int | None = None):
        key = os.getenv("COURTLISTENER_API_KEY")
        if not key:
            raise SystemExit("COURTLISTENER_API_KEY isn't set in .env")
        self._http = httpx.Client(headers={"Authorization": f"Token {key}"},
                                  timeout=60, follow_redirects=True)
        self.max_requests = max_requests
        self.requests = 0
        self._last = 0.0

    # ---- quota

    def usage(self) -> list[dict]:
        """The account's rate-limit scopes, e.g. {"scope": "user", "rate": "125/day", "remaining": 120, ...}.
        Has its own (separate) limit, so it's only called at the start and after a 429."""
        resp = self._http.get(f"{BASE}/api-usage/")
        resp.raise_for_status()
        return resp.json().get("current_usage", [])

    def remaining_today(self) -> int | None:
        for s in self.usage():
            if s.get("scope") == "user" and s.get("window_seconds") == 86400:
                return s.get("remaining")
        return None

    def _throttle_wait(self, resp: httpx.Response) -> float:
        """Seconds until the limit that rejected us resets."""
        retry_after = resp.headers.get("retry-after", "")
        if retry_after.isdigit():
            return float(retry_after)
        try:
            now = datetime.now(timezone.utc)
            resets = [datetime.fromisoformat(s["reset_at"]) for s in self.usage()
                      if s.get("scope") == "user" and s.get("blocked") and s.get("reset_at")]
            if resets:
                return max((r - now).total_seconds() for r in resets) + 5
        except Exception:
            pass
        return 60.0

    # ---- requests

    def get(self, path_or_url: str, params: dict | None = None) -> dict:
        url = path_or_url if path_or_url.startswith("http") else f"{BASE}{path_or_url}"
        for attempt in range(1, ATTEMPTS + 1):
            if self.max_requests is not None and self.requests >= self.max_requests:
                raise BudgetExhausted(f"used this run's budget of {self.max_requests} requests")
            time.sleep(max(0.0, self._last + MIN_INTERVAL - time.time()))
            self._last = time.time()
            self.requests += 1
            try:
                resp = self._http.get(url, params=params)
            except httpx.TransportError as e:   # includes timeouts
                if attempt == ATTEMPTS:
                    raise
                print(f"    network error ({type(e).__name__}); retrying", flush=True)
                time.sleep(10 * 2 ** attempt)
                continue

            if resp.status_code == 429:
                wait = self._throttle_wait(resp)
                if wait > MAX_WAIT:
                    raise BudgetExhausted(f"CourtListener's daily limit is reached; it resets in {wait / 3600:.1f} hours")
                print(f"    rate limited; waiting {wait / 60:.0f} min", flush=True)
                time.sleep(wait)
                continue
            if resp.status_code >= 500 and attempt < ATTEMPTS:
                time.sleep(10 * 2 ** attempt)
                continue
            if resp.status_code >= 400:
                detail = resp.text[:200].replace("\n", " ")
                raise RuntimeError(f"CourtListener returned {resp.status_code} for {resp.url.path}: {detail}")
            return resp.json()
        raise RuntimeError("unreachable")

    def search_statute(self, statute: str, order: str = "cited", cap: int = 10,
                       max_pages: int = 3) -> tuple[int, list[Case], int]:
        """(total matching opinions, up to `cap` distinct cases whose court opinion
        cites the statute, number skipped because only a concurrence or dissent does)."""
        params = {"q": statute_query(statute), "type": "o", "court": " ".join(COURTS),
                  "order_by": ORDER[order]}
        cases: list[Case] = []
        seen: dict[str, Case] = {}            # every key of every case taken
        separate_only: list[set[str]] = []
        data = self.get("/search/", params)
        total = data.get("count") or 0
        for _ in range(max_pages):
            for r in data.get("results", []):
                c = to_case(r)
                if not c:
                    continue
                if not c.main_opinion_id():
                    separate_only.append(c.keys)
                    continue
                dup = next((seen[k] for k in c.keys if k in seen), None)
                if dup:
                    if is_better_name(c.case_name, dup.case_name):
                        dup.case_name = c.case_name
                    seen.update({k: dup for k in c.keys})
                    continue
                cases.append(c)
                seen.update({k: c for k in c.keys})
            if len(cases) >= cap or not data.get("next"):
                break
            data = self.get(data["next"])
        skipped = sum(1 for ks in separate_only if not ks & seen.keys())
        return total, cases[:cap], skipped

    def opinion_text(self, opinion_id: int) -> tuple[str, str]:
        """(cleaned text, the opinion's API URL). Cached on disk."""
        api_url = f"{BASE}/opinions/{opinion_id}/"
        cache = CACHE_DIR / f"{opinion_id}.json"
        if cache.exists():
            # re-cleaned, so cleaning fixes reach texts cached before them
            return clean_plain(json.loads(cache.read_text())["text"]), api_url
        data = self.get(api_url, {"fields": ",".join(["id", "type"] + TEXT_FIELDS)})
        text = best_text(data)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"id": opinion_id, "text": text}))
        return text, api_url

# ---- parsing

def to_case(r: dict) -> Case | None:
    if not r.get("cluster_id") or not r.get("absolute_url"):
        return None
    return Case(
        cluster_id=r["cluster_id"],
        case_name=clean_case_name(r.get("caseName") or r.get("caseNameFull") or ""),
        court=r.get("court") or r.get("court_id") or "",
        court_id=r.get("court_id") or "",
        date=r.get("dateFiled"),
        docket_number=r.get("docketNumber") or "",
        cite_count=r.get("citeCount") or 0,
        url=SITE + r["absolute_url"],
        opinions=[{"id": o["id"], "type": o.get("type")} for o in r.get("opinions", []) if o.get("id")],
    )

def is_better_name(new: str, old: str) -> bool:
    """Some duplicate clusters are named after a reporter, e.g.
    "98 Cal. Daily Op. Serv. 5539, ..." instead of "Graham v. FEMA"."""
    looks_bad = lambda s: not s or bool(re.match(r"^\d", s))
    return looks_bad(old) and not looks_bad(new)

def best_text(opinion: dict) -> str:
    """Plain text when the opinion has it, otherwise the HTML versions as text."""
    plain = clean_plain(opinion.get("plain_text") or "")
    if len(plain.split()) >= 50:
        return plain
    for f in TEXT_FIELDS[1:]:
        text = html_to_text(opinion.get(f) or "")
        if len(text.split()) >= 50:
            return text
    return plain

def clean_plain(text: str) -> str:
    text = re.sub(r"(\w)-\n\s*(\w)", r"\1\2", text)   # words hyphenated across lines
    text = re.sub(r"(?<![\w*])\*\d{1,5}\b", " ", text)  # page markers like *2258
    return re.sub(r"\s+", " ", text).strip()

def html_to_text(markup: str) -> str:
    # page markers like *312 inside the text
    markup = re.sub(r'<span class="star-pagination">.*?</span>', " ", markup, flags=re.S)
    markup = re.sub(r"<page-number[^>]*>.*?</page-number>", " ", markup, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    return re.sub(r"\s+", " ", text).strip()
