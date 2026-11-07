import pdfplumber, tempfile, os, re, html
from ingest import http

def pdf_url_to_text(url: str) -> str:
    resp = http.get(url)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(resp.content)
        tmp = f.name
    text = ""
    with pdfplumber.open(tmp) as pdf:
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"
    os.unlink(tmp)
    return text.strip()

def htm_url_to_text(url: str) -> str:
    """Congress.gov 'Formatted Text' is the bill text inside <pre>; strip the tags."""
    resp = http.get(url)
    text = html.unescape(re.sub(r"<[^>]+>", "", resp.text)).strip()
    # drop the GPO header: "[Congressional Bills 119th Congress]\n[From the U.S. ...]\n[S. 584 Introduced in Senate (IS)]"
    return re.sub(r"^(\s*\[[^\]\n]*\]\s*\n)+", "", text).strip()

def govinfo_mirror(url: str) -> str | None:
    """Same file on GovInfo (the Government Publishing Office, which publishes bill
    text). Trying it first spreads downloads across two hosts, since Congress.gov
    answers bursts with 429 Too Many Requests:
    https://www.congress.gov/119/bills/hr7044/BILLS-119hr7044ih.htm
      -> https://www.govinfo.gov/content/pkg/BILLS-119hr7044ih/html/BILLS-119hr7044ih.htm"""
    m = re.search(r"/(BILLS-[0-9a-z]+)\.(htm|pdf)$", url)
    if not m:
        return None
    name, ext = m.groups()
    folder = "html" if ext == "htm" else "pdf"
    return f"https://www.govinfo.gov/content/pkg/{name}/{folder}/{name}.{ext}"

def url_to_text(url: str) -> str:
    fetch = pdf_url_to_text if url.lower().endswith(".pdf") else htm_url_to_text
    mirror = govinfo_mirror(url)
    if mirror:
        try:
            return fetch(mirror)
        except Exception:
            pass  # fall back to Congress.gov
    return fetch(url)

def clean_text(text: str) -> str:
    lines = text.split("\n")
    cleaned = [l.strip() for l in lines if len(l.strip()) > 20]
    return "\n".join(cleaned)
