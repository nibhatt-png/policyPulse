import httpx, os
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("CONGRESS_API_KEY")
BASE    = "https://api.congress.gov/v3"

KEYWORDS = [
    "environment", "climate", "clean", "emissions", "conservation",
    "pollution", "energy", "wildlife", "water", "forest", "algal",
    "carbon", "renewable", "endangered", "toxic"
]

def fetch_bills(topic: str, limit: int = 10) -> list[dict]:
    results = []
    offset  = 0

    while len(results) < limit:
        resp = httpx.get(
            f"{BASE}/bill/118/hr",
            params={"api_key": API_KEY, "limit": 50, "offset": offset}
        )
        bills = resp.json().get("bills", [])
        if not bills:
            break
        for b in bills:
            if any(word in b.get("title", "").lower() for word in KEYWORDS):
                results.append({
                    "title":        b.get("title"),
                    "url":          b.get("url"),
                    "date":         b.get("updateDate"),
                    "jurisdiction": "federal",
                    "doc_type":     "legislation",
                    "issue_tags":   [topic],
                    "source_name":  "Congress.gov"
                })
            if len(results) >= limit:
                break
        offset += 50

    return results