import ollama
from itertools import groupby
from rag import db

EMBED_MODEL = "nomic-embed-text"
EMBED_BATCH = 16

COLUMNS = ["content", "embedding", "source_name", "doc_type", "url", "date", "jurisdiction",
           "issue_tags", "title", "bill_number", "congress", "introduced_date",
           "latest_action", "latest_action_date", "text_url", "passed_chamber"]

def embed_texts(texts: list[str]) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        out += ollama.embed(model=EMBED_MODEL, input=texts[i:i + EMBED_BATCH])["embeddings"]
    return out

def embed_and_store(chunks: list[dict]) -> list[int]:
    """Embed chunks and store them, REPLACING any rows already stored for the
    same bill URL, so re-running an ingest never duplicates a bill."""
    if not chunks:
        return []
    embeddings = embed_texts([c["content"] for c in chunks])

    placeholders = ", ".join("%s::vector" if col == "embedding" else "%s" for col in COLUMNS)
    pairs = sorted(zip(chunks, embeddings), key=lambda p: p[0].get("url") or "")

    # One transaction on a pooled connection. db.run always returns or closes
    # the connection (a leaked one per failed bill once exhausted Supabase's
    # session pool), and retries once on a dropped connection or timeout;
    # the delete-then-insert makes that retry safe.
    def store(cur):
        ids = []
        for url, group in groupby(pairs, key=lambda p: p[0].get("url") or ""):
            # serialize concurrent writers of the same bill, then replace its rows
            cur.execute("select pg_advisory_xact_lock(hashtext(%s))", [url])
            cur.execute("delete from documents where url = %s", [url])
            for chunk, embedding in group:
                row = {**chunk, "embedding": str(embedding)}
                row.setdefault("issue_tags", [])
                cur.execute(
                    f"insert into documents ({', '.join(COLUMNS)}) values ({placeholders}) returning id",
                    [row.get(col) for col in COLUMNS],
                )
                ids.append(cur.fetchone()[0])
        return ids

    return db.run(store)
