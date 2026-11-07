"""Ingest bills for one Congress into documents.

    venv/bin/python -m ingest.run_ingest                     # backfill: 119th, House + Senate
    venv/bin/python -m ingest.run_ingest --since-days 3      # daily: only recently updated bills
    venv/bin/python -m ingest.run_ingest --types hr --limit 20

Which bills are kept is decided in ingest/policy.py: a bill is stored if it
passed at least one chamber (its newest text) or was introduced within the
grace period (its earliest text, usually the introduced draft). Everything
else is skipped; the weekly prune deletes stored bills that age out.

Re-running is safe and is how the data stays current:
  - bills not updated since they were stored are skipped without any API call
  - updated bills are re-checked: a bill that has since passed gets its passed
    text, a bill with newer passed text (e.g. the public law) is re-embedded,
    and otherwise only its latest-action fields are updated
"""
from dotenv import load_dotenv
load_dotenv()
import argparse, os, sys, time, psycopg2
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from ingest.schema import ensure_schema
from ingest.policy import passed_a_chamber, in_grace_period, is_ceremonial, grace_cutoff
from ingest.sources.congress import (fetch_all_bills, fetch_text_versions, newest_version,
                                     earliest_version, version_text_url)
from ingest.parse import url_to_text, clean_text
from ingest.chunk import chunk_document
from ingest.embed import embed_and_store
from rag import db

# Abort instead of racing through the whole list when something systemic is
# wrong (e.g. sustained rate limiting); failed bills aren't stored, so a re-run resumes.
MAX_FAILURES_IN_A_ROW = 25

META_FIELDS = ["title", "bill_number", "congress", "date", "introduced_date",
               "latest_action", "latest_action_date", "passed_chamber"]

def stored_bills(conn, congress: int) -> dict[str, tuple]:
    """url -> (stored update date, stored text_url, passed_chamber) for bills already ingested."""
    with conn.cursor() as cur:
        cur.execute("""
            select url, max(date)::text, max(text_url), bool_or(passed_chamber)
            from documents
            where url like %s
            group by url
        """, [f"%/bill/{congress}/%"])
        return {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}

def update_metadata(bill: dict) -> None:
    db.run(lambda cur: cur.execute(
        f"update documents set {', '.join(f + ' = %s' for f in META_FIELDS)} where url = %s",
        [bill.get(f) for f in META_FIELDS] + [bill["url"]],
    ))

def process(bill: dict, stored: tuple | None) -> str:
    versions = fetch_text_versions(bill["url"])
    if not versions:
        return "no text yet"
    passed = passed_a_chamber([v.get("type") for v in versions],
                              bill["origin_chamber"], bill["latest_action"])
    if not passed and not in_grace_period(bill["introduced_date"]):
        return "skipped (not passed, past grace period)"

    # passed: its most final text; still in the grace period: its first draft
    text_url = version_text_url(newest_version(versions) if passed else earliest_version(versions))
    if not text_url:
        return "no text yet"
    bill = {**bill, "passed_chamber": passed, "text_url": text_url}
    if stored and stored[1] == text_url:
        update_metadata(bill)
        return "actions updated"

    text   = clean_text(url_to_text(text_url))
    chunks = chunk_document(text, bill)
    ids    = embed_and_store(chunks)
    return f"{'re-embedded' if stored else 'stored'} {len(ids)} chunks ({'passed' if passed else 'draft'})"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--congress", type=int, default=119)
    ap.add_argument("--types", nargs="+", default=["hr", "s"])
    ap.add_argument("--workers", type=int, default=4, help=f"at most {db.MAX_CONN} (the pool size)")
    ap.add_argument("--limit", type=int, default=0, help="max bills per type (0 = all)")
    ap.add_argument("--since-days", type=int, default=0,
                    help="only look at bills updated in the last N days (0 = all; daily runs use a few days)")
    args = ap.parse_args()
    args.workers = min(args.workers, db.MAX_CONN)
    since = str(date.today() - timedelta(days=args.since_days)) if args.since_days else None

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    ensure_schema(conn)
    stored = stored_bills(conn, args.congress)
    conn.close()
    print(f"keeping bills that passed a chamber, or were introduced on/after {grace_cutoff()}", flush=True)

    for bill_type in args.types:
        print(f"\n=== {args.congress}th Congress / {bill_type}"
              f"{f' / updated since {since}' if since else ''} ===", flush=True)
        bills = fetch_all_bills(args.congress, bill_type, since=since)
        ceremonial = [b for b in bills if is_ceremonial(b["title"])]
        bills = [b for b in bills if not is_ceremonial(b["title"])]
        print(f"{len(bills) + len(ceremonial)} bills listed, {len(ceremonial)} ceremonial namings skipped, "
              f"{sum(b['url'] in stored for b in bills)} already stored", flush=True)

        # skip bills that haven't changed since they were stored (rows with a
        # null passed_chamber predate the keep rule, so those are redone)
        todo = [b for b in bills
                if b["url"] not in stored
                or stored[b["url"]][2] is None
                or (b["date"] or "") > (stored[b["url"]][0] or "")]
        if args.limit:
            todo = todo[:args.limit]
        print(f"{len(todo)} new or updated bills to check (most recently updated first)", flush=True)

        start, done, counts, failures_in_a_row = time.time(), 0, {}, 0
        with ThreadPoolExecutor(args.workers) as pool:
            futures = {pool.submit(process, b, stored.get(b["url"])): b for b in todo}
            for fut in as_completed(futures):
                bill = futures.pop(fut)  # drop finished futures so their results are freed
                done += 1
                try:
                    result = fut.result()
                    failures_in_a_row = 0
                except Exception as e:
                    result = f"error: {e}"
                    failures_in_a_row += 1
                if failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
                    print(f"\nSTOPPING: {failures_in_a_row} bills failed in a row (last: {result}). "
                          "Nothing after this was stored; re-run later to resume.", flush=True)
                    for f in futures:
                        f.cancel()
                    sys.exit(1)
                kind = result.split(" (")[0].split(" ")[0] if not result.startswith("no text") else "no-text"
                if kind in ("stored", "re-embedded"):
                    kind += " passed" if "(passed)" in result else " draft"
                counts[kind] = counts.get(kind, 0) + 1
                rate = done / (time.time() - start)
                eta  = (len(todo) - done) / rate / 60 if rate else 0
                print(f"[{done}/{len(todo)} · {eta:.0f} min left] {bill['bill_number']} "
                      f"{bill['title'][:50]} — {result}", flush=True)
        print(f"finished {bill_type}: {counts}", flush=True)

if __name__ == "__main__":
    main()
