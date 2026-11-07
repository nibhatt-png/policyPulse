from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

from rag.retriever import retrieve, recent_activity, is_topicless
from rag import db
from rag.synthesizer import synthesize, clean_markdown, MODEL
from groq import Groq, APIStatusError, APIConnectionError
import os, traceback, psycopg2

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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

@app.post("/ask")
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
    traceback.print_exc()
    return HTTPException(500, "Something went wrong on the server.")

@app.get("/bill")
def get_bill(url: str):
    try:
        def query_db(cur):
            cur.execute("""
                select content, source_name, doc_type, date, url, title, bill_number,
                       congress, latest_action, latest_action_date
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
        "chunks":      len(rows)
    }