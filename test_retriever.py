from dotenv import load_dotenv
load_dotenv()
import ollama, os
from supabase import create_client

resp      = ollama.embeddings(model="nomic-embed-text", prompt="algal blooms")
embedding = resp["embedding"]

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

result = supabase.rpc("match_documents", {
    "query_embedding": embedding,
    "match_threshold": 0.1,
    "match_count":     5
}).execute()

print("results:", len(result.data))
for r in result.data:
    print(r["content"][:100])