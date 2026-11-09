"""Fill in policy_area for stored bills that don't have one yet.

    venv/bin/python -m ingest.backfill_policy_areas

The ingest records it for every bill it stores or updates, but CRS assigns it
a few weeks after introduction, so new bills start without one. Re-running
this (or the daily ingest, once Congress.gov marks the bill updated) fills
them in.
"""
from dotenv import load_dotenv
load_dotenv()
import os, psycopg2
from concurrent.futures import ThreadPoolExecutor
from ingest.schema import ensure_schema
from ingest.sources.congress import fetch_policy_area
from rag import db

def main():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    ensure_schema(conn)
    with conn.cursor() as cur:
        cur.execute("select distinct url from documents where doc_type = 'legislation' and policy_area is null")
        urls = [r[0] for r in cur.fetchall()]
    conn.close()
    print(f"{len(urls)} bills without a policy area", flush=True)

    def fill(url):
        area = fetch_policy_area(url)
        if area:
            db.run(lambda cur: cur.execute("update documents set policy_area = %s where url = %s", [area, url]))
        return area

    with ThreadPoolExecutor(4) as pool:
        areas = list(pool.map(fill, urls))
    print(f"filled {sum(a is not None for a in areas)}; "
          f"{sum(a is None for a in areas)} not assigned yet (usually bills from the last few weeks)")

if __name__ == "__main__":
    main()
