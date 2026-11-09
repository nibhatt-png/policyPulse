"""Bill listings for the topic pages and the "what's new" page.

Everything is per bill (the documents table has one row per chunk), using the
metadata columns only, never the chunk text.
"""
from datetime import timedelta
from rag import db
from rag.retriever import STAGE_SQL, current_congress
from rag.topics import TOPICS, Topic

# "this week" and "last 30 days" (the longer view helps during recesses)
WHATS_NEW_PERIODS = (7, 30)

STATUS_LABELS = {
    5: "Became law",
    4: "Sent to the President",
    3: "Passed the House or Senate",
    2: "Advanced in committee",
    1: "Introduced",
}

# action_stage: what the latest action itself was (for "what happened this week").
# status: how far the bill has gotten overall. A bill that passed the House and
# was then referred to a Senate committee has a routine latest action but has
# still passed a chamber.
BILLS_SQL = f"""
    select url,
           max(bill_number)        as bill_number,
           max(title)              as title,
           max(latest_action)      as latest_action,
           max(latest_action_date) as latest_action_date,
           max(introduced_date)    as introduced_date,
           max(policy_area)        as policy_area,
           max({STAGE_SQL})        as action_stage,
           greatest(max({STAGE_SQL}), case when bool_or(passed_chamber) then 3 else 1 end) as status
    from documents
    where congress = %(congress)s
    group by url
"""

def _bills(rows) -> list[dict]:
    out = []
    for r in rows:
        url, number, title, action, action_date, introduced, area, action_stage, status = r
        out.append({
            "url": url, "bill_number": number, "title": title,
            "latest_action": action,
            "latest_action_date": str(action_date) if action_date else None,
            "introduced_date": str(introduced) if introduced else None,
            "policy_area": area, "action_stage": action_stage,
            "status": status, "status_label": STATUS_LABELS[status],
        })
    return out

def data_as_of() -> str | None:
    """Date of the newest action in the data, i.e. how current the last ingest was."""
    def q(cur):
        cur.execute("select max(latest_action_date) from documents where congress = %s", [current_congress()])
        return cur.fetchone()[0]
    d = db.run(q)
    return str(d) if d else None

def topic_overview() -> list[dict]:
    """Every topic with its bill counts."""
    def q(cur):
        cur.execute(f"""
            select policy_area, count(*), count(*) filter (where status >= 3), count(*) filter (where status = 5)
            from ({BILLS_SQL}) b
            where policy_area is not null
            group by policy_area
        """, {"congress": current_congress()})
        return {r[0]: r[1:] for r in cur.fetchall()}
    by_area = db.run(q)
    out = []
    for t in TOPICS:
        counts = [by_area.get(a, (0, 0, 0)) for a in t.policy_areas]
        out.append({"slug": t.slug, "name": t.name, "icon": t.icon, "description": t.description,
                    "bills":  sum(c[0] for c in counts),
                    "passed": sum(c[1] for c in counts),
                    "laws":   sum(c[2] for c in counts)})
    return out

def topic_bills(topic: Topic) -> list[dict]:
    """The topic's bills, furthest along first, then most recent action."""
    def q(cur):
        cur.execute(f"""
            select * from ({BILLS_SQL}) b
            where policy_area = any(%(areas)s)
            order by status desc, latest_action_date desc nulls last, url
        """, {"congress": current_congress(), "areas": list(topic.policy_areas)})
        return cur.fetchall()
    return _bills(db.run(q))

def whats_new(days: int = 7) -> dict:
    """What happened in the `days` days ending at the newest action in the data
    (not today, so a missed daily ingest doesn't empty the page)."""
    def q(cur):
        cur.execute("select max(latest_action_date) from documents where congress = %s", [current_congress()])
        end = cur.fetchone()[0]
        if not end:
            return None, None, []
        start = end - timedelta(days=days - 1)
        cur.execute(f"""
            select * from ({BILLS_SQL}) b
            where latest_action_date between %(start)s and %(end)s
               or introduced_date    between %(start)s and %(end)s
            order by latest_action_date desc nulls last, url
        """, {"congress": current_congress(), "start": start, "end": end})
        return start, end, cur.fetchall()
    start, end, rows = db.run(q)
    bills = _bills(rows)
    s, e = str(start) if start else None, str(end) if end else None
    acted = [b for b in bills if b["latest_action_date"] and s <= b["latest_action_date"] <= e]
    # Committee progress isn't listed: the database only keeps bills that
    # passed a chamber or are under 4 months old, so most bills that moved in
    # committee aren't in it, and a partial list would mislead.
    sections = [
        ("laws", "Became law", "Signed by the President.",
         [b for b in acted if b["action_stage"] == 5]),
        ("president", "Sent to the President", "Passed both chambers and waiting for a signature or veto.",
         [b for b in acted if b["action_stage"] == 4]),
        ("passed", "Passed the House or Senate", "Approved by at least one chamber.",
         [b for b in acted if b["action_stage"] == 3]),
        ("introduced", "Newly introduced", "Newly proposed. Most bills never get a vote.",
         [b for b in bills if b["introduced_date"] and s <= b["introduced_date"] <= e
          and not (b in acted and b["action_stage"] >= 3)]),
    ]
    return {"start": s, "end": e, "days": days,
            "sections": [{"key": k, "label": l, "description": d, "bills": bs} for k, l, d, bs in sections]}
