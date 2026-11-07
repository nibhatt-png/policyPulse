from dotenv import load_dotenv
load_dotenv()
from ingest.sources.congress import fetch_bills
from ingest.parse import pdf_url_to_text, clean_text
from ingest.chunk import chunk_document
from ingest.embed import embed_and_store
import httpx, os

API_KEY = os.getenv("CONGRESS_API_KEY")

# get one bill
bills = fetch_bills(limit=1)
bill  = bills[0]
print("bill:", bill["title"])

# get pdf url
resp     = httpx.get(bill["url"], params={"api_key": API_KEY})
detail   = resp.json().get("bill", {})
text_url = detail.get("textVersions", {}).get("url")
resp2    = httpx.get(text_url, params={"api_key": API_KEY})
versions = resp2.json().get("textVersions", [])
pdf_url  = None
for v in versions:
    for fmt in v.get("formats", []):
        if fmt.get("type") == "PDF":
            pdf_url = fmt.get("url")
            break

# parse, chunk, embed and store
text   = clean_text(pdf_url_to_text(pdf_url))
chunks = chunk_document(text, bill)
ids    = embed_and_store(chunks)

print(f"stored {len(ids)} chunks with ids: {ids}")