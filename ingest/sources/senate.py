from ingest.sources.congress import fetch_bills

def fetch_senate_bills(congress: int = 119, limit: int = 50, offset: int = 0) -> list[dict]:
    return fetch_bills(congress, "s", limit=limit, offset=offset)
