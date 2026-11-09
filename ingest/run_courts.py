"""Ingest federal appellate and Supreme Court opinions that cite a statute the
stored bills amend, into documents (doc_type = 'ruling').

    venv/bin/python -m ingest.run_courts --statutes-only          # step 1 only: the statute set
    venv/bin/python -m ingest.run_courts --dry-run --limit 3      # search and fetch; store nothing
    venv/bin/python -m ingest.run_courts --limit 10               # store opinions for 10 statutes

Bills are proposals and courts cite enacted law, so the link is the U.S. Code
sections the bills cite (mostly the sections they amend). Statutes are
processed in order of how many stored bills cite them.

Free CourtListener accounts get 125 requests a day: one search per statute,
then one request per new opinion. So a run stops cleanly when the budget
runs out, and re-running continues where it left off:
  - statutes already searched (court_searches) are skipped (--force redoes them)
  - cases already stored (by URL, or as a duplicate of a stored case) are not
    fetched again; they just get the new statute added to issue_tags
  - opinion texts are cached in .cache/courtlistener/, so a dry run's
    downloads are reused by the real run
"""
from dotenv import load_dotenv
load_dotenv()
import argparse, os, re, psycopg2
from collections import Counter, defaultdict
from ingest.schema import ensure_schema
from ingest.chunk import chunk_document
from ingest.embed import embed_and_store
from ingest.sources.courtlistener import Client, BudgetExhausted, Case, case_keys
from ingest.statutes import citations_in
from rag import db

DEFAULT_CAP        = 10    # cases per statute
DEFAULT_MAX_CHUNKS = 6     # ~4,300 words: the syllabus/opening, facts and holding of most opinions
MIN_WORDS          = 300   # shorter texts are usually one-line orders ("AFFIRMED.")

# ---- step 1: the statute set

def build_statute_set() -> list[tuple[str, int, int]]:
    """[(statute, bills citing it, times cited)], most-cited by bills first."""
    def q(cur):
        cur.execute(r"""select url, content from documents
                        where doc_type = 'legislation'
                          and (content ~ 'U\.\s?S\.\s?C\.' or content ~* 'United States Code')""")
        return cur.fetchall()
    bills, times = defaultdict(set), Counter()
    for url, content in db.run(q):
        for c in citations_in(content):
            bills[c].add(url)
            times[c] += 1      # chunks overlap, so this double-counts a little; bills don't
    return sorted(((s, len(bills[s]), times[s]) for s in bills), key=lambda r: (-r[1], -r[2], r[0]))

# ---- storage helpers

def stored_rulings() -> tuple[dict[str, set], dict[str, str]]:
    """(url -> its statute tags, case key -> url; see case_keys) for rulings already stored."""
    def q(cur):
        cur.execute("""select url, max(source_name), max(date)::text, max(docket_number), max(title),
                              array_agg(distinct t) filter (where t is not null)
                       from documents left join lateral unnest(issue_tags) t on true
                       where doc_type = 'ruling' group by url""")
        return cur.fetchall()
    tags, keys = {}, {}
    for url, court, date, docket, title, t in db.run(q):
        tags[url] = set(t or [])
        for k in case_keys(court, date, docket, title):
            keys[k] = url
    return tags, keys

def searched_statutes() -> set[str]:
    return {r[0] for r in db.run(lambda cur: (cur.execute("select statute from court_searches"), cur.fetchall())[1])}

def add_tag(url: str, statute: str) -> None:
    db.run(lambda cur: cur.execute(
        "update documents set issue_tags = array_append(issue_tags, %s) "
        "where url = %s and not (%s = any(issue_tags))", [statute, url, statute]))

def record_search(statute: str, results: int, new: int, tagged: int) -> None:
    db.run(lambda cur: cur.execute("""
        insert into court_searches (statute, results, stored, tagged) values (%s, %s, %s, %s)
        on conflict (statute) do update set searched_at = now(), results = excluded.results,
            stored = excluded.stored, tagged = excluded.tagged""", [statute, results, new, tagged]))

def table_size() -> tuple[int, int]:
    """(bytes, rows) of documents, including its indexes."""
    return db.run(lambda cur: (cur.execute(
        "select pg_total_relation_size('documents'), count(*) from documents"), cur.fetchone())[1])

def ruling_chunks(case: Case, text: str, api_url: str, statute: str, max_chunks: int) -> list[dict]:
    return chunk_document(text, {
        "title":         case.case_name,
        "source_name":   case.court,
        "doc_type":      "ruling",
        "url":           case.url,
        "date":          case.date,
        "jurisdiction":  "federal",
        "issue_tags":    [statute],
        "text_url":      api_url,
        "docket_number": case.docket_number or None,
    })[:max_chunks]

# ---- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0, help="statutes to search this run (0 = until the budget runs out)")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP, help="cases per statute")
    ap.add_argument("--max-chunks", type=int, default=DEFAULT_MAX_CHUNKS, help="chunks kept per opinion")
    ap.add_argument("--order", choices=["cited", "recent", "relevant"], default="cited",
                    help="which cases fill the cap: most-cited, most recent, or most about the statute")
    ap.add_argument("--min-bills", type=int, default=1, help="only statutes cited by at least this many bills")
    ap.add_argument("--max-requests", type=int, default=0,
                    help="CourtListener requests this run (0 = what's left of today's quota)")
    ap.add_argument("--statute", action="append", help="search these statutes instead, e.g. '42 U.S.C. § 5122'")
    ap.add_argument("--force", action="store_true", help="re-search statutes already searched")
    ap.add_argument("--dry-run", action="store_true", help="search and fetch texts, but store nothing")
    ap.add_argument("--statutes-only", action="store_true", help="print the statute set and stop")
    args = ap.parse_args()

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    ensure_schema(conn)
    conn.close()

    statutes = build_statute_set()
    print(f"{len(statutes)} distinct U.S. Code sections cited by stored bills; most cited:")
    for s, nbills, ntimes in statutes[:20]:
        print(f"  {s:<24} {nbills:>4} bills  {ntimes:>5} citations")
    if args.statutes_only:
        return

    queue = [s for s, nbills, _ in statutes if nbills >= args.min_bills]
    if args.statute:
        queue = args.statute
    done = set() if args.force else searched_statutes()
    queue = [s for s in queue if s not in done]
    if args.limit:
        queue = queue[:args.limit]

    client = Client()
    left = client.remaining_today()
    client.max_requests = args.max_requests or left
    print(f"\n{len(done)} statutes already searched; {len(queue)} to search this run. "
          f"CourtListener requests left today: {left}; budget for this run: {client.max_requests}"
          f"{'  (DRY RUN: nothing will be stored)' if args.dry_run else ''}\n", flush=True)

    tags, keys = stored_rulings()
    size_before, rows_before = table_size()
    bytes_per_chunk = size_before / rows_before if rows_before else 11_000
    totals = Counter()
    stop_reason = None

    for n, statute in enumerate(queue, 1):
        try:
            found, cases, separate_only = client.search_statute(statute, order=args.order, cap=args.cap)
        except BudgetExhausted as e:
            stop_reason = str(e)
            break
        print(f"[{n}/{len(queue)}] {statute}: {found} opinions; taking {len(cases)} cases"
              + (f" (skipped {separate_only} cited only in a concurrence or dissent)" if separate_only else ""), flush=True)
        totals["separate opinion only"] += separate_only
        totals["statutes searched"] += 1
        totals["opinions found"] += found
        new = tagged = 0
        try:
            for c in cases:
                label = f"{c.case_name[:60]} ({c.court_id}, {c.date}, cited {c.cite_count}x)"
                url = c.url if c.url in tags else next((keys[k] for k in c.keys if k in keys), None)
                if url:
                    if statute not in tags[url]:
                        if not args.dry_run:
                            add_tag(url, statute)
                        tags[url].add(statute)
                        tagged += 1
                    print(f"    already stored     {label}")
                    continue
                text, api_url = client.opinion_text(c.main_opinion_id())
                words = len(text.split())
                if words < MIN_WORDS:
                    print(f"    too short ({words}w)  {label}")
                    totals["too short"] += 1
                    continue
                chunks = ruling_chunks(c, text, api_url, statute, args.max_chunks)
                if not args.dry_run:
                    embed_and_store(chunks)
                tags[c.url] = {statute}
                keys.update({k: c.url for k in c.keys})
                new += 1
                totals["opinions stored"] += 1
                totals["chunks stored"] += len(chunks)
                capped = " (capped)" if len(chunks) == args.max_chunks and words > 700 * args.max_chunks else ""
                print(f"    {'would store' if args.dry_run else 'stored'} {len(chunks)} chunk{'s' if len(chunks) != 1 else ''}"
                      f"{capped:<9} {label}  [{words:,} words]", flush=True)
        except BudgetExhausted as e:
            stop_reason = str(e) + f" (partway through {statute}; it will be redone next run)"
            break
        totals["tagged existing"] += tagged
        if not args.dry_run:
            record_search(statute, found, new, tagged)

    estimate = totals["chunks stored"] * bytes_per_chunk
    print(f"\n{'DRY RUN, nothing stored. ' if args.dry_run else ''}Summary")
    for k in ["statutes searched", "opinions found", "opinions stored", "chunks stored", "tagged existing", "too short", "separate opinion only"]:
        print(f"  {k + (' (would be)' if args.dry_run and k.endswith('stored') else ''):<31} {totals[k]:,}")
    print(f"  CourtListener requests used: {client.requests}")
    print(f"  estimated storage {'needed' if args.dry_run else 'added'}: {estimate / 1e6:.1f} MB "
          f"(at {bytes_per_chunk / 1000:.1f} KB per chunk, the current average incl. indexes)")
    if not args.dry_run and totals["chunks stored"]:
        size_after, _ = table_size()
        print(f"  documents table: {size_before / 1e6:.0f} MB -> {size_after / 1e6:.0f} MB")
    if stop_reason:
        print(f"\nStopped early: {stop_reason}. Re-run to continue.")

if __name__ == "__main__":
    main()
