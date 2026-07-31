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

class Message(BaseModel):
    role: str
    content: str

class Query(BaseModel):
    question: str
    history: list[Message] = []

@app.post("/ask")
def ask(query: Query):
    chunks  = retrieve(query.question, top_k=8)
    history = [{"role": m.role, "content": m.content} for m in query.history]
    answer  = synthesize(query.question, chunks, history)
    return {
        "answer":  answer,
        "sources": chunks
    }