import httpx, pdfplumber, tempfile, os

def pdf_url_to_text(url: str) -> str:
    resp = httpx.get(url, follow_redirects=True, timeout=30)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(resp.content)
        tmp = f.name
    text = ""
    with pdfplumber.open(tmp) as pdf:
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"
    os.unlink(tmp)
    return text.strip()

def clean_text(text: str) -> str:
    lines = text.split("\n")
    cleaned = [l.strip() for l in lines if len(l.strip()) > 20]
    return "\n".join(cleaned)