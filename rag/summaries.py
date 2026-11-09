"""One-paragraph AI summaries for the topic and "what's new" pages.

Each summary is cached in page_summaries with a hash of the prompt it came
from, so it's regenerated only when the underlying bills change (after an
ingest), not on every page view. That keeps page views from spending Groq's
small per-minute token allowance. rag/warm_summaries.py rebuilds stale ones
right after the daily ingest, so visitors rarely wait for one.
"""
import hashlib
from rag import db
from rag.synthesizer import client, MODEL, clean_markdown
from rag.browse import STATUS_LABELS

MAX_BILLS_IN_PROMPT = 35
MAX_TOKENS = 1500   # includes the model's reasoning tokens

STYLE = """Write ONE paragraph of 4 to 6 sentences for a general audience, in plain English with no jargon.
Use only the bills listed; don't add outside facts. Start with what became law or passed the House or Senate: name at most three of the most significant by short name with the number in parentheses, e.g. "the Romance Scam Prevention Act (H.R. 2481)", and describe the rest by theme (e.g. "most of the other new laws transfer federal land or rename parks"). Then describe the main themes of the newer proposals in general terms rather than listing them.
Write plainly: no filler like "a flurry of" or "overall", and say what bills do rather than calling them significant.
Don't predict whether bills will pass, and don't mention supporters, opponents, parties or politics.
No headings, no bullet points, no bold, no HTML."""

def bill_line(b: dict) -> str:
    action = (b["latest_action"] or "")[:140]
    return (f"- {b['bill_number']}: {(b['title'] or '')[:160]}. Status: {STATUS_LABELS[b['status']]}. "
            f"Latest action ({b['latest_action_date']}): {action}")

# ---- prompts: (cache key, prompt), or a fixed message when there's nothing to summarize

def topic_prompt(topic, bills: list[dict], as_of: str | None) -> tuple[str, str] | str:
    if not bills:
        return f"No current bills on {topic.name.lower()} are in the database yet."
    shown = bills[:MAX_BILLS_IN_PROMPT]   # already sorted: furthest along, then most recent
    prompt = f"""Summarize what the current Congress has been doing on {topic.name.lower()} ({topic.description.lower()}), as of {as_of}.

{STYLE}

There are {len(bills)} bills on this topic; these are the furthest along and most recent:
{chr(10).join(bill_line(b) for b in shown)}"""
    return f"topic:{topic.slug}", prompt

def period_prompt(data: dict) -> tuple[str, str] | str:
    """For the "what's new" page (browse.whats_new output)."""
    sections = {s["key"]: s["bills"] for s in data["sections"]}
    acted = sections["laws"] + sections["president"] + sections["passed"]
    introduced = sections["introduced"]
    if not acted and not introduced:
        return "There was no new activity on bills in the database in this period."
    lines = [bill_line(b) for b in acted[:MAX_BILLS_IN_PROMPT]]
    room = max(MAX_BILLS_IN_PROMPT - len(lines), 10)
    prompt = f"""Summarize what happened in Congress from {data['start']} to {data['end']}.

{STYLE}

Bills that became law, were sent to the President, or passed the House or Senate in that period ({len(acted)}):
{chr(10).join(lines) or '(none)'}

Bills introduced in that period ({len(introduced)}; a sample):
{chr(10).join(f"- {b['bill_number']}: {(b['title'] or '')[:160]}" for b in introduced[:room]) or '(none)'}"""
    return f"new:{data['days']}:{data['end']}", prompt

# ---- cache

def _hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()

def lookup(key: str, prompt: str) -> str | None:
    """The cached summary, if it was made from exactly this prompt."""
    def q(cur):
        cur.execute("select inputs_hash, content from page_summaries where key = %s", [key])
        return cur.fetchone()
    row = db.run(q)
    return row[1] if row and row[0] == _hash(prompt) else None

def generate(key: str, prompt: str) -> str:
    """Ask the model for a summary and cache it."""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=MAX_TOKENS,
        reasoning_effort="low",
    )
    content = clean_markdown((resp.choices[0].message.content or "").strip())
    if not content:
        raise RuntimeError("The AI model returned an empty summary.")

    def store(cur):
        cur.execute("""
            insert into page_summaries (key, inputs_hash, content) values (%s, %s, %s)
            on conflict (key) do update
                set inputs_hash = excluded.inputs_hash, content = excluded.content, created_at = now()
        """, [key, _hash(prompt), content])
    db.run(store)
    return content

def summarize(job: tuple[str, str] | str) -> str:
    """A prompt function's result -> the summary text (cached, or made now)."""
    if isinstance(job, str):
        return job
    key, prompt = job
    return lookup(key, prompt) or generate(key, prompt)

def topic_summary(topic, bills: list[dict], as_of: str | None) -> str:
    return summarize(topic_prompt(topic, bills, as_of))

def period_summary(data: dict) -> str:
    return summarize(period_prompt(data))
