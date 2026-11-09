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
    # Congress.gov's policy area (assigned by CRS a few weeks after
    # introduction); topic pages group bills by it (see rag/topics.py)
    "alter table documents add column if not exists policy_area text",
    "create index if not exists documents_url_idx on documents (url)",
    "create index if not exists documents_policy_area_idx on documents (policy_area)",
    # cached AI summaries for the topic and "what's new" pages, regenerated
    # only when the bills they're based on change (see rag/summaries.py)
    """create table if not exists page_summaries (
        key         text primary key,
        inputs_hash text not null,
        content     text not null,
        created_at  timestamptz not null default now()
    )""",
    "alter table page_summaries enable row level security",
    # "recent activity" lookups by Congress + latest action date
    "create index if not exists documents_recent_idx on documents (congress, latest_action_date)",
    # The keep rule from ingest/policy.py, in SQL: delete bills that never
    # passed a chamber and were introduced before the grace period. Returns
    # the number of bills deleted.
    """create or replace function prune_stale_bills(grace interval)
    returns integer language sql as $$
        with gone as (
            delete from documents
            where doc_type = 'legislation'          -- never court rulings
              and passed_chamber is not true
              and introduced_date < current_date - grace
            returning url
        )
        select count(distinct url)::int from gone
    $$""",
    # Supabase would otherwise let anyone call it through the REST API
    "revoke execute on function prune_stale_bills(interval) from public, anon, authenticated",
    # ---- court rulings (ingest/run_courts.py): doc_type = 'ruling', the
    # statutes that matched them in issue_tags
    # CourtListener lists many cases more than once; court + date + docket
    # number identifies a case across those duplicates
    "alter table documents add column if not exists docket_number text",
    # which statutes have been searched, so re-runs (which the 125-requests-a-day
    # limit makes necessary) continue instead of starting over
    """create table if not exists court_searches (
        statute     text primary key,         -- e.g. '42 U.S.C. § 5122'
        searched_at timestamptz not null default now(),
        results     int not null,             -- opinions CourtListener matched
        stored      int not null,             -- cases newly stored
        tagged      int not null default 0    -- already-stored cases given this statute's tag
    )""",
    "alter table court_searches enable row level security",
    # bills and rulings both store U.S. Code sections in issue_tags (see
    # ingest/statutes.py); the bill <-> ruling links match on overlaps
    "create index if not exists documents_issue_tags_idx on documents using gin (issue_tags)",
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
