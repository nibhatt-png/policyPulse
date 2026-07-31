import os
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def synthesize(query: str, chunks: list[dict], history: list[dict] = []) -> str:
    if not chunks:
        return "I couldn't find any relevant documents to answer your question. Try rephrasing or asking about a different aspect of legislation."

    context = "\n\n---\n\n".join([
        f"[{c['doc_type'].upper()} | {c['source']} | {c['date']}]\n{c['content']}"
        for c in chunks
    ])

    system_prompt = """You are PolicyPulse, a friendly policy research assistant that helps everyday people understand US legislation.

Your job is to make complex legislation simple and accessible. You:
- Explain things in plain English, never assume legal knowledge
- Always define legal or technical terms when you use them
- Give concrete real-world examples of what legislation means for regular people
- Are honest when documents don't contain enough information
- Cite your sources clearly so people can verify what you say
- Never make up information — only use what's in the provided documents"""

    context_prompt = f"""Answer the user's question using ONLY these source documents:

<sources>
{context}
</sources>

Rules:
- Cite sources inline as [Bill Name, Date]
- Explain what each bill actually DOES in practice for regular people
- If bills conflict or take opposing sides, point that out
- End with a "Sources" section
- If you can't answer from the documents, say so clearly"""

    messages = [{"role": "system", "content": system_prompt}]
    
    # add conversation history
    for msg in history[-6:]:  # last 3 exchanges
        messages.append(msg)
    
    messages.append({
        "role": "user",
        "content": f"{context_prompt}\n\nQuestion: {query}"
    })

    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=1500
    )
    return resp.choices[0].message.content