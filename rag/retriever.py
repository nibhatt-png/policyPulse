import re
from datetime import date
from rag import db
from rag.embeddings import embed_query

# How many nearest chunks to consider before grouping by bill. Bills have many
# (often duplicated) chunks, so the pool must be much larger than top_k to end
# up with top_k *different* bills. HNSW returns at most hnsw.ef_search rows, so
# ef_search is raised to match.
CANDIDATES_PER_RESULT = 25
MIN_CANDIDATES        = 100

# Most users ask about what Congress is doing now. Bills from past Congresses
# that didn't pass are dead, so rank them as if they were this much less similar:
# an old bill still wins when it is clearly more relevant, and still appears
# when the current Congress has nothing on the topic.
PAST_CONGRESS_PENALTY = 0.05

# "Recent activity" mode looks at actions within this many days of the newest
# action in the data (not of today, so a stale ingest still returns results).
RECENT_DAYS = 30
RECENT_PER_STAGE = 3

COLUMNS = ["content", "source", "url", "doc_type", "date", "title", "bill_number",
           "congress", "latest_action", "latest_action_date", "issue_tags", "similarity"]
SELECT = """content, source_name, url, doc_type, date, title, bill_number,
            congress, latest_action, latest_action_date, issue_tags"""

# Court rulings are searched separately from bills and merged in, so the far
# more numerous bill chunks can't crowd out a relevant ruling: up to
# MAX_RULINGS of the result slots go to rulings at most RULING_MARGIN less
# similar than the best bill. An unrelated ruling still stays out.
MAX_RULINGS   = 3
RULING_MARGIN = 0.05   # checked on 8 questions: keeps Medicaid/FOIA/asylum cases, drops off-topic ones
# A ruling's issue_tags list the statutes it was matched on; a bill's list
# every section it cites (often dozens), which the sources don't need.
MAX_TAGS_RETURNED = 5

def current_congress(today: date | None = None) -> int:
    # each Congress starts January 3 of an odd year; the 1st began in 1789
    today = today or date.today()
    year = today.year - 1 if (today.month, today.day) < (1, 3) else today.year
    start_year = year if year % 2 == 1 else year - 1
    return (start_year - 1789) // 2 + 1

def _to_dicts(rows) -> list[dict]:
    out = []
    for r in rows:
        d = dict(zip(COLUMNS, r))
        d["similarity"] = float(d["similarity"]) if d["similarity"] is not None else None
        d["latest_action_date"] = str(d["latest_action_date"]) if d["latest_action_date"] else None
        d["date"] = str(d["date"]) if d["date"] else None
        d["issue_tags"] = (d["issue_tags"] or [])[:MAX_TAGS_RETURNED] if d["doc_type"] == "ruling" else []
        out.append(d)
    return out

def _search(cur, vec: str, doc_type: str, limit: int, candidates: int, exact: bool) -> list[dict]:
    """Best-matching chunk per document of one type, best first. exact=True
    scans every row (cheap for the few hundred ruling chunks; the HNSW index
    would return mostly bill chunks and leave too few rulings after filtering)."""
    distance = "(embedding <=> %(vec)s::vector)" + (" + 0" if exact else "")   # "+ 0" bypasses the index
    cur.execute(f"""
        with candidates as (
            select {SELECT}, {distance} as distance
            from documents
            where doc_type = %(doc_type)s
            order by {distance}
            limit %(candidates)s
        ),
        best_per_doc as (
            select distinct on (url) * from candidates order by url, distance
        )
        select {SELECT}, 1 - distance as similarity
        from best_per_doc
        order by distance + case when congress = %(current)s or doc_type = 'ruling' then 0 else %(penalty)s end
        limit %(limit)s
    """, {"vec": vec, "doc_type": doc_type, "candidates": candidates, "limit": limit,
          "current": current_congress(), "penalty": PAST_CONGRESS_PENALTY})
    return _to_dicts(cur.fetchall())

def _merge_companions(bills: list[dict]) -> list[dict]:
    """The same bill is often introduced in both chambers under one title
    (e.g. H.R. 9778 and S. 5033); keep the better match and note the other."""
    kept, by_title = [], {}
    for b in bills:
        key = (b["title"] or "").strip().lower() or b["url"]
        if key in by_title:
            if b["bill_number"]:
                by_title[key].setdefault("companions", []).append(b["bill_number"])
            continue
        by_title[key] = b
        kept.append(b)
    return kept

def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """The top_k most similar documents (one best-matching chunk each):
    bills, plus up to MAX_RULINGS court rulings that are about as relevant."""
    embedding  = embed_query(query)
    vec_str    = "[" + ",".join(str(x) for x in embedding) + "]"
    candidates = min(max(top_k * CANDIDATES_PER_RESULT, MIN_CANDIDATES), 1000)

    def query_db(cur):
        # SET LOCAL lasts only for this transaction
        cur.execute("set local hnsw.ef_search = %s", [candidates])
        bills   = _search(cur, vec_str, "legislation", top_k * 2, candidates, exact=False)
        rulings = _search(cur, vec_str, "ruling", MAX_RULINGS, MAX_RULINGS * CANDIDATES_PER_RESULT, exact=True)
        return bills, rulings

    bills, rulings = db.run(query_db)
    bills = _merge_companions(bills)
    if not bills:
        return rulings[:top_k]
    best = bills[0]["similarity"]
    rulings = [r for r in rulings if r["similarity"] >= best - RULING_MARGIN]
    picked = bills[:top_k - len(rulings)] + rulings
    # most similar first, so the model and the source list lead with the best match
    return sorted(picked, key=lambda d: -d["similarity"])

# How far a bill has gotten, judged from its latest action. Most latest actions
# are routine committee referrals, so ranking by date alone would mostly surface
# paperwork; this ranks laws and floor votes first.
STAGE_SQL = r"""
    case
        when latest_action ~* '^(became public law|signed by president)' then 5
        when latest_action ~* '^(presented to president|vetoed)' then 4
        when latest_action ~* '(passed|agreed to|received in the senate|held at the desk|message on senate action)' then 3
        when latest_action ~* '(placed on .*calendar|reported|ordered to be reported)' then 2
        else 1
    end
"""

def recent_activity(top_k: int = 8) -> list[dict]:
    """Current-Congress bills with the most significant recent actions
    (one representative chunk each: the start of the bill's text)."""
    def query_db(cur):
        cur.execute(f"""
            with window_start as (
                select max(latest_action_date) - %(days)s as d
                from documents where congress = %(congress)s
            ),
            -- rank bills on their (per-bill) metadata only, without touching chunk text
            bills as (
                select url, max(latest_action_date) as action_date, max({STAGE_SQL}) as stage
                from documents
                where congress = %(congress)s
                  and latest_action_date >= (select d from window_start)
                group by url
            ),
            -- take up to PER_STAGE of the newest bills from each stage first, so
            -- the answer covers new laws AND floor votes AND committee progress,
            -- then fill any remaining slots by stage and date
            top_bills as (
                select url, action_date, stage
                from (
                    select *, row_number() over (partition by stage order by action_date desc, url) as rn
                    from bills
                ) ranked
                order by (rn <= %(per_stage)s) desc, stage desc, action_date desc
                limit %(top_k)s
            )
            select distinct on (t.stage, t.action_date, d.url)
                   d.content, d.source_name, d.url, d.doc_type, d.date, d.title, d.bill_number,
                   d.congress, d.latest_action, d.latest_action_date, d.issue_tags, null as similarity
            from top_bills t
            join documents d on d.url = t.url
            order by t.stage desc, t.action_date desc, d.url, d.id   -- first chunk = start of the bill
        """, {"congress": current_congress(), "days": RECENT_DAYS, "top_k": top_k,
              "per_stage": RECENT_PER_STAGE})
        return cur.fetchall()

    return _to_dicts(db.run(query_db))

# Words that don't name a policy topic. A question made only of these
# ("What is Congress doing right now?") has nothing for similarity search to
# match on, so it gets recent activity instead.
NON_TOPIC_WORDS = set("""
    a an the of on in at to for with about from by and or is are was were be been being
    am do does did doing done has have had having can could will would should may might
    what whats what's which who how why when where there here that this these those it its
    me us we you i my our your tell show give list any anything something everything
    congress congressional house senate lawmakers legislators legislature representatives
    senators capitol hill federal government u.s united states washington
    bill bills law laws legislation legislative act acts measure measures
    pass passed passing vote voted votes voting introduced signed working work worked
    right now currently current lately recent recently latest new news today week weeks
    month months year years days happening going on up update updates going been
    important major big key top main biggest notable
""".split())

def is_topicless(question: str) -> bool:
    words = re.findall(r"[a-z][a-z.'’]*", question.lower())
    return bool(words) and all(w.strip(".'’") in NON_TOPIC_WORDS for w in words)
