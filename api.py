from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

from rag.retriever import retrieve
from rag.synthesizer import synthesize

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Query(BaseModel):
    question: str

@app.post("/ask")
def ask(query: Query):
    chunks = retrieve(query.question, top_k=5)
    answer = synthesize(query.question, chunks)
    return {
        "answer": answer,
        "sources": chunks
    }