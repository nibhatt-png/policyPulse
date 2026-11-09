"""Rebuild the topic and "what's new" summaries whose bills changed.

    venv/bin/python -m rag.warm_summaries

Run after an ingest (ingest/daily.py does), so visitors get cached summaries
instead of waiting for one. Unchanged summaries are skipped without calling
the model. Calls are spaced out to stay under Groq's free tier limit of 8,000
tokens per minute, which counts each request's prompt plus its max_tokens
(about 4,000 to 5,000 for one summary).
"""
import sys, time
from groq import APIStatusError
from rag import browse, db, summaries
from rag.topics import TOPICS

PAUSE_SECONDS      = 40   # between model calls
RATE_LIMIT_WAIT    = 65   # after a 413/429, let the per-minute window reset
ATTEMPTS           = 3
KEEP_PERIODS_DAYS  = 60   # "what's new" summaries are keyed by date; drop old ones

def jobs():
    as_of = browse.data_as_of()
    for t in TOPICS:
        yield f"topic: {t.name}", lambda t=t: summaries.topic_prompt(t, browse.topic_bills(t), as_of)
    for days in browse.WHATS_NEW_PERIODS:
        yield f"what's new: last {days} days", lambda days=days: summaries.period_prompt(browse.whats_new(days))

def main() -> int:
    counts = {"up to date": 0, "generated": 0, "nothing to summarize": 0, "failed": 0}
    last_call = 0.0
    for name, make in jobs():
        job = make()
        if isinstance(job, str):
            counts["nothing to summarize"] += 1
            continue
        key, prompt = job
        if summaries.lookup(key, prompt):
            counts["up to date"] += 1
            continue
        for attempt in range(1, ATTEMPTS + 1):
            time.sleep(max(0.0, last_call + PAUSE_SECONDS - time.time()))
            last_call = time.time()
            try:
                summaries.generate(key, prompt)
                counts["generated"] += 1
                print(f"generated  {name}", flush=True)
                break
            except APIStatusError as e:
                if e.status_code in (413, 429) and attempt < ATTEMPTS:
                    print(f"rate limited on {name}; waiting {RATE_LIMIT_WAIT}s", flush=True)
                    time.sleep(RATE_LIMIT_WAIT)
                    continue
                counts["failed"] += 1
                print(f"FAILED     {name}: {e}", flush=True)
                break
            except Exception as e:
                counts["failed"] += 1
                print(f"FAILED     {name}: {e}", flush=True)
                break

    db.run(lambda cur: cur.execute(
        "delete from page_summaries where key like 'new:%%' and created_at < now() - %s::interval",
        [f"{KEEP_PERIODS_DAYS} days"]))
    print(f"summaries: {counts}", flush=True)
    return 1 if counts["failed"] else 0

if __name__ == "__main__":
    sys.exit(main())
