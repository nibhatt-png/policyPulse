"""Delete bills that never passed a chamber and are past the grace period.

    venv/bin/python -m ingest.prune

The same job runs weekly inside Postgres via pg_cron (see ingest/schema.py);
this is for running it by hand.
"""
from rag import db
from ingest.policy import GRACE_MONTHS, grace_cutoff

def main():
    def prune(cur):
        cur.execute("select prune_stale_bills(%s::interval)", [f"{GRACE_MONTHS} months"])
        return cur.fetchone()[0]
    print(f"deleted {db.run(prune)} bills introduced before {grace_cutoff()} that never passed a chamber")

if __name__ == "__main__":
    main()
