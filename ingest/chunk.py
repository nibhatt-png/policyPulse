def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    words   = text.split()
    chunks  = []
    start   = 0

    while start < len(words):
        end   = start + chunk_size
        chunk = " ".join(words[start:end])
        if len(chunk.strip()) > 100:
            chunks.append(chunk)
        start = end - overlap

    return chunks

def chunk_document(text: str, metadata: dict) -> list[dict]:
    chunks = chunk_text(text)
    return [
        {"content": chunk, **metadata}
        for chunk in chunks
    ]