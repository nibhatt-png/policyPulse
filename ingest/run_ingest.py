from dotenv import load_dotenv
load_dotenv()
from ingest.sources.congress import fetch_bills
from ingest.parse import pdf_url_to_text, clean_text
from ingest.chunk import chunk_document
from ingest.embed import embed_and_store
import httpx, os

API_KEY = os.getenv("CONGRESS_API_KEY")

bills = fetch_bills("environment", limit=20)
print(f"found {len(bills)} bills")

for bill in bills:
    try:
        print(f"processing: {bill['title']}")

        # get pdf url
        resp     = httpx.get(bill["url"], params={"api_key": API_KEY})
        detail   = resp.json().get("bill", {})
        text_url = detail.get("textVersions", {}).get("url")
        if not text_url:
            print("  no text url, skipping")
            continue

        resp2    = httpx.get(text_url, params={"api_key": API_KEY})
        versions = resp2.json().get("textVersions", [])
        pdf_url  = None
        for v in versions:
            for fmt in v.get("formats", []):
                if fmt.get("type") == "PDF":
                    pdf_url = fmt.get("url")
                    break

        if not pdf_url:
            print("  no pdf, skipping")
            continue

        text   = clean_text(pdf_url_to_text(pdf_url))
        chunks = chunk_document(text, bill)
        ids    = embed_and_store(chunks)
        print(f"  stored {len(ids)} chunks")

    except Exception as e:
        print(f"  error: {e}, skipping")