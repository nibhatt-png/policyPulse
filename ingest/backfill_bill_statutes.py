"""Record the U.S. Code sections each stored bill cites, in issue_tags.

    venv/bin/python -m ingest.backfill_bill_statutes

New and re-embedded bills get them during the ingest (ingest/run_ingest.py);
this fills in bills stored before that. Safe to re-run: it recomputes the
tags from the stored text and overwrites them.
"""
from dotenv import load_dotenv
load_dotenv()
import os, psycopg2
from collections import defaultdict
from psycopg2.extras import execute_values
from ingest.schema import ensure_schema
from ingest.statutes import statutes_in
from rag import db

def main():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    ensure_schema(conn)
    conn.close()

    rows = db.run(lambda cur: (cur.execute(
        "select url, content, issue_tags from documents where doc_type = 'legislation' order by url, id"),
        cur.fetchall())[1])
    texts, current = defaultdict(list), {}
    for url, content, tags in rows:
        texts[url].append(content)
        current[url] = sorted(tags or [])

    # the whole bill at once: bare references depend on its long title (see statutes_in)
    values = [(url, statutes_in(" ".join(parts))) for url, parts in texts.items()]
    # only rewrite rows whose tags change; every rewrite leaves a dead row version behind
    changed = [(url, t) for url, t in values if t != current[url]]
    print(f"{len(changed)} of {len(values)} bills' statutes changed", flush=True)
    if changed:
        db.run(lambda cur: execute_values(cur, """
        update documents d set issue_tags = v.tags
        from (values %s) as v(url, tags)
        where d.url = v.url and d.doc_type = 'legislation'
    """, changed, template="(%s, %s::text[])", page_size=500))
    with_tags = sum(1 for _, t in values if t)
    print(f"{len(values)} bills: {with_tags} cite at least one U.S. Code section "
          f"({sum(len(t) for _, t in values):,} bill-section pairs)")

if __name__ == "__main__":
    main()
