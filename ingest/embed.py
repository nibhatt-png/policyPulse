import ollama, psycopg2, os
from dotenv import load_dotenv
load_dotenv()

def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def embed_and_store(chunks: list[dict]) -> list[int]:
    conn = get_connection()
    cur  = conn.cursor()
    ids  = []

    for chunk in chunks:
        resp = ollama.embeddings(
            model="nomic-embed-text",
            prompt=chunk["content"]
        )
        embedding = resp["embedding"]

        cur.execute("""
            insert into documents
              (content, embedding, source_name, doc_type, url, date, jurisdiction, issue_tags)
            values (%s, %s::vector, %s, %s, %s, %s, %s, %s)
            returning id
        """, (
            chunk["content"],
            embedding,
            chunk.get("source_name"),
            chunk.get("doc_type"),
            chunk.get("url"),
            chunk.get("date"),
            chunk.get("jurisdiction"),
            chunk.get("issue_tags", []),
        ))
        ids.append(cur.fetchone()[0])

    conn.commit()
    cur.close()
    conn.close()
    return ids