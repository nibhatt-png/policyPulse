"""Schema for the documents table, from an empty database onward.

All statements are idempotent, so this runs at the start of every ingest.
The HNSW vector index is built separately (ingest/create_vector_index.py)
after a bulk load, since building it once is much cheaper than maintaining
it during tens of thousands of inserts.
"""
from ingest.policy import GRACE_MONTHS

MIGRATIONS = [
    "create extension if not exists vector with schema extensions",
    """create table if not exists documents (
        id           bigserial primary key,
        content      text not null,
        embedding    vector(768),          -- nomic-embed-text
        source_name  text,
        doc_type     text,
        url          text,
        date         date,                 -- last update to the bill or its text
        jurisdiction text,
        issue_tags   text[] default '{}'
    )""",
    # Supabase exposes public tables through its REST API using the public
    # (anon) key; with RLS on and no policies, only the owner role the app
    # connects as can read or write.
    "alter table documents enable row level security",
    "alter table documents add column if not exists title text",
    "alter table documents add column if not exists bill_number text",
    "alter table documents add column if not exists congress int",
    "alter table documents add column if not exists introduced_date date",
    "alter table documents add column if not exists latest_action text",
    "alter table documents add column if not exists latest_action_date date",
    # which text version was embedded, so re-runs can tell when a bill's text changed
    "alter table documents add column if not exists text_url text",
    # passed at least one chamber (see ingest/policy.py); null = stored before this existed
    "alter table documents add column if not exists passed_chamber boolean",
    "create index if not exists documents_url_idx on documents (url)",
    # "recent activity" lookups by Congress + latest action date
    "create index if not exists documents_recent_idx on documents (congress, latest_action_date)",
    # The keep rule from ingest/policy.py, in SQL: delete bills that never
    # passed a chamber and were introduced before the grace period. Returns
    # the number of bills deleted.
    """create or replace function prune_stale_bills(grace interval)
    returns integer language sql as $$
        with gone as (
            delete from documents
            where passed_chamber is not true
              and introduced_date < current_date - grace
            returning url
        )
        select count(distinct url)::int from gone
    $$""",
    # Supabase would otherwise let anyone call it through the REST API
    "revoke execute on function prune_stale_bills(interval) from public, anon, authenticated",
]

PRUNE_JOB      = "prune-stale-bills"
PRUNE_SCHEDULE = "0 9 * * 1"   # Mondays 09:00 UTC

def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        for sql in MIGRATIONS:
            cur.execute(sql)
    conn.commit()
    ensure_prune_job(conn)

def ensure_prune_job(conn) -> None:
    """Schedule the weekly prune inside Postgres (pg_cron), so it runs even
    when no ingest does. cron.schedule with a job name replaces that job."""
    try:
        with conn.cursor() as cur:
            cur.execute("create extension if not exists pg_cron")
            cur.execute("select cron.schedule(%s, %s, %s)",
                        [PRUNE_JOB, PRUNE_SCHEDULE,
                         f"select prune_stale_bills('{GRACE_MONTHS} months')"])
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"warning: couldn't schedule the weekly prune with pg_cron ({e}). "
              "Run `python -m ingest.prune` weekly instead.", flush=True)
