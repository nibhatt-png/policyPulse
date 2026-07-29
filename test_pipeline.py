from dotenv import load_dotenv
load_dotenv()
from rag.retriever import retrieve
from rag.synthesizer import synthesize

query   = "What does Congress say about algal blooms and water pollution?"
chunks  = retrieve(query, top_k=5)
print(f"retrieved {len(chunks)} chunks\n")

answer  = synthesize(query, chunks)
print(answer)