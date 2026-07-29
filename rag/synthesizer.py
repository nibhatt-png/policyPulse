import ollama, os
from dotenv import load_dotenv
load_dotenv()

def synthesize(query: str, chunks: list[dict]) -> str:
    if not chunks:
        return "I couldn't find any relevant documents to answer your question."

    context = "\n\n---\n\n".join([
        f"[{c['doc_type'].upper()} | {c['source']} | {c['date']}]\n{c['content']}"
        for c in chunks
    ])

    prompt = f"""You are a policy research assistant specializing in environmental legislation.
Answer the user's question using ONLY the provided source documents.

Rules:
- Cite sources inline as [Source Name, Date]
- If the documents don't contain enough information, say so
- Be clear and concise
- End with a "Sources" section listing the documents used

<sources>
{context}
</sources>

Question: {query}"""

    resp = ollama.chat(
        model="llama3.2",
        messages=[{"role": "user", "content": prompt}]
    )
    return resp["message"]["content"]