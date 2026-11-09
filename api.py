import re
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

from rag.retriever import retrieve, recent_activity, is_topicless
from rag import db
from rag.synthesizer import synthesize, clean_markdown, MODEL
from rag.topics import TOPICS_BY_SLUG
from rag import browse, summaries
from rag.embeddings import EmbeddingError
from groq import Groq, APIStatusError, APIConnectionError
import os, traceback, psycopg2

app = FastAPI()

# Every route is under /api. On Vercel (vercel.json) the site and the API share
# one domain: /api/... goes to this service, everything else to the Next.js
# frontend, and the service sees the full path (/api/ask, not /ask).
router = APIRouter(prefix="/api")

# Only for local development, where the frontend (next dev) and this API run
# on different ports. In production they share a domain, so CORS doesn't apply.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class Message(BaseModel):
    role: str
    content: str

class Query(BaseModel):
    question: str
    history: list[Message] = []

@router.post("/ask")
def ask(query: Query):
    history = [{"role": m.role, "content": m.content} for m in query.history]
    try:
        # A question that names no topic ("What is Congress doing right now?")
        # has nothing for similarity search to match, so show recent activity.
        recent = is_topicless(query.question)
        chunks = recent_activity(top_k=8) if recent else retrieve(query.question, top_k=8)
        answer = synthesize(query.question, chunks, history, recent=recent)
    except Exception as e:
        raise readable_error(e)
    return {"answer": answer, "sources": chunks}  # one chunk per bill

# An uncaught exception becomes a bare 500 without CORS headers, which the
# browser can only report as "Failed to fetch". Endpoints convert failures to
# an HTTPException instead, so the frontend can show the reason.
def readable_error(e: Exception) -> HTTPException:
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, APIStatusError):
        if e.status_code in (413, 429):
            return HTTPException(429, "The AI model's rate limit was hit. Wait a minute and try again.")
        return HTTPException(502, f"The AI model returned an error ({e.status_code}).")
    if isinstance(e, APIConnectionError):
        return HTTPException(503, "Couldn't reach the AI model. Check your internet connection and try again.")
    if isinstance(e, psycopg2.Error):
        return HTTPException(503, "Couldn't reach the bill database. Check your internet connection and try again.")
    if isinstance(e, EmbeddingError):
        print(f"embedding failed: {e}", flush=True)
        return HTTPException(503, "Couldn't reach the search service. Wait a moment and try again.")
    if isinstance(e, ConnectionError):   # local: the Ollama app isn't running
        return HTTPException(503, "Couldn't reach the search model. Start the Ollama app and try again.")
    traceback.print_exc()
    return HTTPException(500, "Something went wrong on the server.")

# Sentences where an opinion states its outcome. Opinions usually reach their
# holding far past the opening, which is all a plain cut would show the model.
HOLDING_RE = re.compile(r"\b(we hold|we conclude|we therefore|we affirm|we reverse|we vacate|"
                        r"accordingly|for (?:the|these) reasons|(?:is|are) (?:affirmed|reversed|vacated)|remanded)\b", re.I)

def ruling_excerpt(text: str, head: int = 3000, budget: int = 5000) -> str:
    """The opinion's opening plus the passages around its conclusions (about 8,000
    characters, which fits Groq's per-minute token limit alongside the answer)."""
    opening = text[:head]
    sentences = re.split(r"(?<=[.!?])\s+", text[head:])
    picked, used, last = [], 0, -2
    for i, sent in enumerate(sentences):
        if not HOLDING_RE.search(sent):
            continue
        passage = " ".join(sentences[max(i - 1, last + 1):i + 2])
        if not passage or used + len(passage) > budget:
            continue
        picked.append(passage)
        used += len(passage)
        last = i + 1
    if not picked:
        return text[:head + budget]
    return opening + "\n\n[...]\n\n" + "\n\n[...]\n\n".join(picked)

@router.get("/bill")
def get_bill(url: str):
    try:
        def query_db(cur):
            cur.execute("""
                select content, source_name, doc_type, date, url, title, bill_number,
                       congress, latest_action, latest_action_date, issue_tags
                from documents
                where url = %s
                order by id   -- chunks in text order
            """, [url])
            return cur.fetchall()
        rows = db.run(query_db)
    except Exception as e:
        raise readable_error(e)

    if not rows:
        return {"error": "Bill not found"}

    # combine all chunks for this bill
    full_text = "\n\n".join(dict.fromkeys(r[0] for r in rows))  # skip duplicate chunks
    meta      = rows[0]

    # generate plain english summary
    if meta[2] == "ruling":
        prompt = f"""You are explaining a federal court decision to someone with no legal background.

Given the beginning of this opinion, provide:
1. **What was this case about?** (2-3 sentences, very simple: who sued whom, and over what)
2. **What did the court decide?** (2-3 sentences)
3. **Why?** (the court's main reasoning, as bullet points in plain English)
4. **What does it mean for people?** (who is affected and how)
5. **Key things to know** (the law it interprets, the court and year, and anything the excerpt leaves unclear)

Use only what the text says. It's an excerpt: the opening of the opinion, then passages where the court states conclusions. If it doesn't clearly say how the court ruled, say "The excerpt doesn't show the court's final decision" in section 2 instead of inferring it, and don't guess at reasoning you can't see. Keep track of who is asking for what: the party seeking a court's order is not necessarily the winner.

Format your answer in Markdown, using a "## " heading for each of the five sections. Don't use HTML tags.

Case: {meta[5]} ({meta[1]}, decided {meta[3]})

Opinion text (excerpt):
{ruling_excerpt(full_text)}"""
    else:
        prompt = f"""You are explaining a bill to someone with no legal background.

Given this bill text, provide:
1. **What is this bill about?** (2-3 sentences, very simple)
2. **What problem is it trying to solve?** (2-3 sentences)
3. **What would change if this became law?** (bullet points, plain English)
4. **Who does this affect?** (which groups of people)
5. **Key things to know** (important details from the text, such as deadlines, funding amounts, or exceptions)

Use only what the bill text says. Do not describe supporters, critics, controversies or how people have reacted, since the text doesn't contain that.

Format your answer in Markdown, using a "## " heading for each of the five sections. Don't use HTML tags.

Bill: {meta[6]}: {meta[5]}

Bill text:
{full_text[:4000]}"""

    try:
        resp = groq_client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2500,
            reasoning_effort="low",
        )
    except Exception as e:
        raise readable_error(e)

    return {
        "summary":     clean_markdown(resp.choices[0].message.content),
        "source_name": meta[1],
        "doc_type":    meta[2],
        "date":        str(meta[3]),
        "url":         meta[4],
        "title":       meta[5],
        "bill_number": meta[6],
        "congress":    meta[7],
        "latest_action":      meta[8],
        "latest_action_date": str(meta[9]) if meta[9] else None,
        # for a ruling, the statutes it interprets (a bill's list is long; /related uses it)
        "statutes":    (meta[10] or []) if meta[2] == "ruling" else [],
        "chunks":      len(rows)
    }

# ---- Bills <-> court rulings ---------------------------------------------
# Linked through the U.S. Code sections both store in issue_tags: the sections
# a bill cites (mostly ones it amends), and the ones a ruling was matched on.

MAX_RELATED = 12

@router.get("/related")
def related(url: str):
    """For a bill: court rulings on the laws it would change. For a ruling:
    current bills that would change the law it interprets. Each item lists
    the statutes it shares with the document."""
    def query_db(cur):
        cur.execute("select max(doc_type), array_agg(distinct t) from documents, unnest(issue_tags) t where url = %s", [url])
        doc_type, tags = cur.fetchone()
        if not doc_type or not tags:
            return None, []
        other = "legislation" if doc_type == "ruling" else "ruling"
        # Sharing a statute makes an item related; how close the openings of the
        # two texts are (a bill's title and purpose, a case's facts) ranks it, so
        # a case about FOIA comes before one citing FOIA in passing, and a bill
        # about FOIA before a 1,000-page bill that mentions it once. (Comparing
        # every chunk would favor long bills, which have more chances to match.)
        cur.execute("""
            with me as (select embedding from documents where url = %(url)s order by id limit 1),
            openings as (
                select distinct on (d.url) d.url, d.title, d.bill_number, d.source_name, d.date,
                       d.latest_action, d.latest_action_date, d.issue_tags, d.embedding
                from documents d
                where d.doc_type = %(other)s and d.issue_tags && %(tags)s and d.url <> %(url)s
                order by d.url, d.id
            )
            select url, title, bill_number, source_name, date::text, latest_action, latest_action_date::text,
                   array(select t from unnest(issue_tags) t where t = any(%(tags)s) order by t) as shared
            from openings
            order by embedding <=> (select embedding from me)
            limit %(limit)s
        """, {"tags": tags, "other": other, "url": url, "limit": MAX_RELATED})
        return other, cur.fetchall()
    try:
        other, rows = db.run(query_db)
    except Exception as e:
        raise readable_error(e)
    return {
        "kind": other,   # what the items are: "ruling" or "legislation"; None if nothing links
        "items": [{"url": r[0], "title": r[1], "bill_number": r[2], "source_name": r[3], "date": r[4],
                   "latest_action": r[5], "latest_action_date": r[6], "shared": r[7]} for r in rows],
    }

# ---- Browse: topic pages and "what's new" --------------------------------
# Bill lists and their AI summaries are separate endpoints so a page can show
# its bills right away while the summary (cached, but slow when regenerated)
# loads.

def get_topic(slug: str):
    topic = TOPICS_BY_SLUG.get(slug)
    if not topic:
        raise HTTPException(404, "No such topic.")
    return topic

@router.get("/topics")
def list_topics():
    try:
        return {"as_of": browse.data_as_of(), "topics": browse.topic_overview()}
    except Exception as e:
        raise readable_error(e)

@router.get("/topics/{slug}")
def topic_page(slug: str):
    topic = get_topic(slug)
    try:
        bills = browse.topic_bills(topic)
        as_of = browse.data_as_of()
    except Exception as e:
        raise readable_error(e)
    groups = [{"status": s, "label": label, "bills": [b for b in bills if b["status"] == s]}
              for s, label in sorted(browse.STATUS_LABELS.items(), reverse=True)]
    return {"slug": topic.slug, "name": topic.name, "icon": topic.icon,
            "description": topic.description, "as_of": as_of, "total": len(bills),
            "groups": [g for g in groups if g["bills"]]}

@router.get("/topics/{slug}/summary")
def topic_summary(slug: str):
    topic = get_topic(slug)
    try:
        return {"summary": summaries.topic_summary(topic, browse.topic_bills(topic), browse.data_as_of())}
    except Exception as e:
        raise readable_error(e)

def check_days(days: int) -> int:
    if days not in browse.WHATS_NEW_PERIODS:
        raise HTTPException(400, f"days must be one of {browse.WHATS_NEW_PERIODS}.")
    return days

@router.get("/whats-new")
def whats_new(days: int = 7):
    check_days(days)
    try:
        return browse.whats_new(days=days)
    except Exception as e:
        raise readable_error(e)

@router.get("/whats-new/summary")
def whats_new_summary(days: int = 7):
    check_days(days)
    try:
        return {"summary": summaries.period_summary(browse.whats_new(days=days))}
    except Exception as e:
        raise readable_error(e)

# after all routes are defined on the router
app.include_router(router)
