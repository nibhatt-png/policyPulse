"""Fill bill metadata (title, bill number, Congress, latest action, ...) for rows
stored before those columns existed.

Safe to re-run: only rows with a missing congress or title are updated.

    venv/bin/python -m ingest.backfill_titles
"""
from dotenv import load_dotenv
load_dotenv()
import os, psycopg2
from psycopg2.extras import execute_values
from ingest.schema import ensure_schema
from ingest.sources.congress import fetch_all_bills
from ingest.bill_meta import bill_number_from_url

FIELDS = ["title", "bill_number", "congress", "introduced_date", "latest_action", "latest_action_date"]

def canonical(url: str) -> str:
    return url.split("?")[0].rstrip("/")

def main():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    ensure_schema(conn)
    cur = conn.cursor()

    cur.execute("select distinct url from documents where doc_type = 'legislation' and (congress is null or title is null) and url is not null")
    urls = [r[0] for r in cur.fetchall()]
    print(f"{len(urls)} bills need metadata")
    if not urls:
        return

    # page through only the bill lists we need (one per Congress + bill type)
    needed = set()
    for u in urls:
        parts = canonical(u).split("/")
        i = parts.index("bill")
        needed.add((int(parts[i + 1]), parts[i + 2]))

    listed: dict[str, dict] = {}
    for congress, bill_type in sorted(needed):
        print(f"fetching {congress}/{bill_type} list...")
        for b in fetch_all_bills(congress, bill_type):
            listed[canonical(b["url"])] = b

    rows, missing = [], []
    for u in urls:
        b = listed.get(canonical(u))
        if b is None:
            missing.append(u)
            parts = canonical(u).split("/")
            b = {"bill_number": bill_number_from_url(u), "congress": int(parts[parts.index("bill") + 1])}
        rows.append((u, *[b.get(f) for f in FIELDS]))

    print(f"updating {len(rows)} bills...")
    execute_values(cur, f"""
        update documents d
           set {', '.join(f'{f} = coalesce(v.{f}, d.{f})' for f in FIELDS)}
          from (values %s) as v(url, {', '.join(FIELDS)})
         where d.url = v.url
    """, rows, page_size=500,
       template="(%s, %s, %s, %s::int, %s::date, %s, %s::date)")
    conn.commit()

    cur.execute("select count(*), count(title), count(congress), count(latest_action) from documents")
    total, t, c, a = cur.fetchone()
    print(f"done: of {total} rows, {t} have a title, {c} a congress, {a} a latest action")
    if missing:
        print(f"{len(missing)} bills were not in the API list (number/congress set from URL), e.g. {missing[:3]}")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
