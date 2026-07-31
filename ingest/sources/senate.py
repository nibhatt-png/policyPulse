import httpx, os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("CONGRESS_API_KEY")
BASE    = "https://api.congress.gov/v3"

def fetch_senate_bills(limit: int = 50, offset: int = 0) -> list[dict]:
    params = {
        "api_key": API_KEY,
        "limit":   limit,
        "offset":  offset,
        "sort":    "updateDate+desc",
    }

    resp = httpx.get(f"{BASE}/bill/118/s", params=params)
    resp.raise_for_status()
    bills = resp.json().get("bills", [])

    results = []
    for bill in bills:
        title = bill.get("title", "")
        if not title:
            continue
        results.append({
            "title":        title,
            "url":          bill.get("url"),
            "date":         bill.get("updateDate"),
            "jurisdiction": "federal",
            "doc_type":     "legislation",
            "issue_tags":   [],
            "source_name":  "Congress.gov (Senate)"
        })
    return results