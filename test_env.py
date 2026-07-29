from dotenv import load_dotenv
load_dotenv()
import os, ollama, psycopg2

print("checking ollama...")
resp = ollama.embeddings(model="nomic-embed-text", prompt="test")
print(f" ollama ok: embedding dim = {len(resp['embedding'])}")

print("checking database...")
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur  = conn.cursor()
cur.execute("select count(*) from documents")
print(f" db ok: {cur.fetchone()[0]} documents stored")
conn.close()

print("\n all good — ready to build!")