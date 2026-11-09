import os, re
from datetime import date
from groq import Groq
from rag.retriever import current_congress
from rag.db import ConfigError
from dotenv import load_dotenv
load_dotenv()

_client: Groq | None = None

def groq_client() -> Groq:
    """Created on first use, not at import: with GROQ_API_KEY unset, creating it
    at import crashed the whole API (every route a 500), not just AI answers."""
    global _client
    if _client is None:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise ConfigError("GROQ_API_KEY isn't set")
        _client = Groq(api_key=key)
    return _client

# llama-3.3-70b-versatile was retired by Groq; override with GROQ_MODEL in .env
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

MAX_CHUNK_CHARS   = 2000  # per retrieved chunk
MAX_HISTORY_MSGS  = 4     # last 2 exchanges
MAX_HISTORY_CHARS = 1000  # per history message (old answers are long)

def clean_markdown(text: str) -> str:
    """The model sometimes puts <br> inside table cells despite being told not to.
    The frontend doesn't render raw HTML (on purpose), so turn them into separators."""
    return re.sub(r"\s*<br\s*/?>\s*", "; ", text, flags=re.I)

def bill_label(c: dict) -> str:
    """e.g. "H.R. 132: Protecting Local Communities from Harmful Algal Blooms Act" """
    parts = [p for p in (c.get("bill_number"), c.get("title")) if p]
    return ": ".join(parts) or c["doc_type"].upper()

def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

def source_header(c: dict) -> str:
    """e.g. [H.R. 132: Title | 119th Congress | Latest action 2026-10-29: Referred to ...]
    or [Court ruling: Nken v. Holder | Supreme Court of the United States | Decided 2009-04-22]"""
    if c.get("doc_type") == "ruling":
        parts = [c.get("title") or "Untitled case", c.get("source"),
                 f"Decided {c['date']}" if c.get("date") else None,
                 f"Interprets {', '.join(c['issue_tags'])}" if c.get("issue_tags") else None]
        return "[Court ruling: " + " | ".join(p for p in parts if p) + "]"
    parts = ["Bill: " + bill_label(c)]
    if c.get("companions"):
        parts.append(f"Same bill also introduced as {', '.join(c['companions'])}")
    if c.get("congress"):
        parts.append(f"{ordinal(c['congress'])} Congress")
    if c.get("latest_action"):
        parts.append(f"Latest action {c.get('latest_action_date') or ''}: {c['latest_action'][:200]}")
    return "[" + " | ".join(parts) + "]"

def synthesize(query: str, chunks: list[dict], history: list[dict] = [], recent: bool = False) -> str:
    """recent=True: chunks are the current Congress's most significant recent
    actions (see retriever.recent_activity), not a topic search."""
    if not chunks:
        return "I couldn't find any relevant documents to answer your question. Try rephrasing or asking about a different aspect of legislation."

    # Groq's free tier allows 8000 tokens/minute, counting the prompt AND max_tokens,
    # so keep the request small: drop duplicate chunks and cap each piece of text.
    seen, unique = set(), []
    for c in chunks:
        if c["content"] not in seen:
            seen.add(c["content"])
            unique.append(c)

    context = "\n\n---\n\n".join([
        f"{source_header(c)}\n{c['content'][:MAX_CHUNK_CHARS]}"
        for c in unique
    ])

    today    = date.today()
    number   = current_congress(today)
    congress = ordinal(number)
    start    = 1789 + 2 * (number - 1)
    end      = start + 2
    system_prompt = f"""You are PolicyPulse, a friendly policy research assistant that helps everyday people understand US legislation.

Your job is to make complex legislation simple and accessible. You:
- Explain things in plain English, never assume legal knowledge
- Always define legal or technical terms when you use them
- Give concrete real-world examples of what legislation means for regular people
- Are honest when documents don't contain enough information
- Cite your sources clearly so people can verify what you say
- Never make up information — only use what's in the provided documents

Today is {today}. The current Congress is the {congress} ({start}–{end}).
- Each source is labeled with its Congress and its latest action. Use them to say where a bill stands right now (e.g. "introduced and referred to committee", "passed the House").
- A bill from an earlier Congress that did not become law died when that Congress ended (on January 3 of the year the next one began). Never call it active, pending or "still moving"; say it expired, and note that it would have to be reintroduced.
- When asked what Congress is doing now, focus on {congress} Congress bills and their most recent actions.
- Sources are of two kinds, and people often confuse them, so keep them clearly apart:
  - "Bill" sources are proposals. Say what a bill "would" do or "proposes"; never describe a bill's provisions as current law unless its latest action says it became law.
  - "Court ruling" sources are decisions about laws already on the books. Say what "the court held" or "ruled", with the court and year from the label, and name the statute it interprets. Never call a ruling a bill or give it a legislative status.
  - When both appear, connect them where they share a law: what the law says now according to the court, then what the bill would change.
  - A ruling may only be about a related law. If no ruling directly addresses the question, say so plainly instead of implying one does."""

    recent_note = f"""These sources are not a topic search: they are the {congress} Congress bills with the most significant recent actions as of {today} (new laws first, then floor votes, then committee action). Summarize what Congress has been doing lately, most significant first, grouped by how far each bill got, and give the date of each action.

""" if recent else ""

    context_prompt = f"""{recent_note}Answer the user's question using ONLY these source documents:

<sources>
{context}
</sources>

Rules:
- Cite sources inline as [Bill Number: Bill Title] for bills and [Case Name (Year)] for court rulings, using the label at the top of each source
- Explain what each bill actually DOES in practice for regular people
- If bills conflict or take opposing sides, point that out
- Format with Markdown (headings, bullet lists, bold, tables where helpful). Never use HTML tags such as <br>; keep table cells to a sentence or two, and use a bullet list instead of a table when items need more detail
- End with a "Sources" section
- If you can't answer from the documents, say so clearly"""

    messages = [{"role": "system", "content": system_prompt}]
    
    # add conversation history
    for msg in history[-MAX_HISTORY_MSGS:]:
        messages.append({"role": msg["role"], "content": msg["content"][:MAX_HISTORY_CHARS]})
    
    messages.append({
        "role": "user",
        "content": f"{context_prompt}\n\nQuestion: {query}"
    })

    resp = groq_client().chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=2000,
        reasoning_effort="low",
    )
    return clean_markdown(resp.choices[0].message.content)