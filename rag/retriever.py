import ollama, psycopg2, os
from dotenv import load_dotenv
load_dotenv()

def retrieve(query: str, top_k: int = 5) -> list[dict]:
    resp      = ollama.embeddings(model="nomic-embed-text", prompt=query)
    embedding = resp["embedding"]
    
    # convert to postgres vector string format
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()
    cur.execute("""
        select content, source_name, url, doc_type, date,
               1 - (embedding <=> %s::vector) as similarity
        from documents
        order by embedding <=> %s::vector
        limit %s
    """, [vec_str, vec_str, top_k])

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "content":    r[0],
            "source":     r[1],
            "url":        r[2],
            "doc_type":   r[3],
            "date":       r[4],
            "similarity": float(r[5])
        }
        for r in rows
    ]