"""Embedding a user's question for similarity search.

Stored chunks were embedded with nomic-embed-text v1.5 (768 dimensions) by the
local Ollama app (ingest/embed.py). A question must use the same model:

  - Deployed (Vercel, no Ollama): Nomic's hosted API, model
    nomic-embed-text-v1.5, when NOMIC_API_KEY is set.
  - Local: Ollama, as before.

Nomic's API always applies a task prefix (task_type), and the model is meant
to be used with one, so the local path adds the same "search_query: " prefix.
Both paths then embed the same text. Checked on 10 questions (2026-11-08):
the prefix keeps about 6 of 8 bill results and the same rulings, and raises
similarity slightly.
"""
import os
import httpx

MODEL_OLLAMA = "nomic-embed-text"          # Ollama's build of v1.5 (137M, F16, 768 dims)
MODEL_NOMIC  = "nomic-embed-text-v1.5"
DIMENSIONS   = 768                         # documents.embedding is vector(768)
QUERY_PREFIX = "search_query: "
NOMIC_URL    = "https://api-atlas.nomic.ai/v1/embedding/text"

class EmbeddingError(Exception):
    """The embedding service couldn't be reached or refused the request."""

def embed_query(text: str) -> list[float]:
    key = os.getenv("NOMIC_API_KEY")
    if key:
        return _nomic(text, key)
    try:
        import ollama   # local only; not installed on Vercel
    except ImportError as e:
        raise EmbeddingError("NOMIC_API_KEY isn't set, and Ollama isn't available here") from e
    return ollama.embeddings(model=MODEL_OLLAMA, prompt=QUERY_PREFIX + text)["embedding"]

def _nomic(text: str, key: str) -> list[float]:
    try:
        resp = httpx.post(NOMIC_URL, timeout=20,
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": MODEL_NOMIC, "texts": [text], "task_type": "search_query",
                                "dimensionality": DIMENSIONS})
    except httpx.HTTPError as e:
        raise EmbeddingError(f"couldn't reach Nomic ({type(e).__name__})") from e
    if resp.status_code != 200:
        # the body explains validation errors; it never contains the key
        raise EmbeddingError(f"Nomic returned {resp.status_code}: {resp.text[:200]}")
    vector = resp.json()["embeddings"][0]
    if len(vector) != DIMENSIONS:
        raise EmbeddingError(f"Nomic returned {len(vector)} dimensions, expected {DIMENSIONS}")
    return vector
