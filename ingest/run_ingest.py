from dotenv import load_dotenv
load_dotenv()
from ingest.sources.congress import fetch_bills
from ingest.sources.senate import fetch_senate_bills
from ingest.parse import pdf_url_to_text, clean_text
from ingest.chunk import chunk_document
from ingest.embed import embed_and_store
import httpx, os, psycopg2

API_KEY = os.getenv("CONGRESS_API_KEY")

def already_ingested(url: str) -> bool:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur  = conn.cursor()
    cur.execute("select 1 from documents where url = %s limit 1", [url])
    exists = cur.fetchone() is not None
    cur.close()
    conn.close()
    return exists

def process_bills(bills):
    total = 0
    for bill in bills:
        try:
            if already_ingested(bill["url"]):
                print(f"  — skipping (already ingested): {bill['title'][:60]}")
                continue

            resp     = httpx.get(bill["url"], params={"api_key": API_KEY}, timeout=10)
            detail   = resp.json().get("bill", {})
            text_url = detail.get("textVersions", {}).get("url")
            if not text_url:
                continue

            resp2    = httpx.get(text_url, params={"api_key": API_KEY}, timeout=10)
            versions = resp2.json().get("textVersions", [])
            pdf_url  = None
            for v in versions:
                for fmt in v.get("formats", []):
                    if fmt.get("type") == "PDF":
                        pdf_url = fmt.get("url")
                        break

            if not pdf_url:
                continue

            text   = clean_text(pdf_url_to_text(pdf_url))
            chunks = chunk_document(text, bill)
            ids    = embed_and_store(chunks)
            total += len(ids)
            print(f"  ✓ {bill['title'][:60]} — {len(ids)} chunks")

        except Exception as e:
            print(f"  ✗ skipping: {e}")
    return total

total_stored = 0

# House bills
print("\n=== HOUSE BILLS ===")
for offset in range(0, 10000, 50):
    print(f"\nfetching house bills offset {offset}...")
    bills = fetch_bills(limit=50, offset=offset)
    if not bills:
        break
    print(f"got {len(bills)} bills")
    total_stored += process_bills(bills)

# Senate bills
print("\n=== SENATE BILLS ===")
for offset in range(0, 5000, 50):
    print(f"\nfetching senate bills offset {offset}...")
    bills = fetch_senate_bills(limit=50, offset=offset)
    if not bills:
        break
    print(f"got {len(bills)} bills")
    total_stored += process_bills(bills)

print(f"\ndone! total chunks stored: {total_stored}")