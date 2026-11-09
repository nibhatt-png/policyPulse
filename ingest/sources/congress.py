import os
from ingest import http
from dotenv import load_dotenv
from ingest.bill_meta import format_bill_number
load_dotenv()

API_KEY = os.getenv("CONGRESS_API_KEY")
BASE    = "https://api.congress.gov/v3"
PAGE    = 250  # API maximum

SOURCE_NAMES = {"hr": "Congress.gov", "s": "Congress.gov (Senate)"}

def to_bill(b: dict, bill_type: str) -> dict:
    latest = b.get("latestAction") or {}
    return {
        "title":              b.get("title", ""),
        "bill_number":        format_bill_number(b["type"], b["number"]),
        "congress":           b.get("congress"),
        "url":                b.get("url"),
        # last change to the bill or its text; the incremental ingest compares this
        "date":               max(filter(None, [b.get("updateDate"), (b.get("updateDateIncludingText") or "")[:10]]), default=None),
        "origin_chamber":     b.get("originChamber"),
        "introduced_date":    b.get("introducedDate"),
        "latest_action":      latest.get("text"),
        "latest_action_date": latest.get("actionDate"),
        "jurisdiction":       "federal",
        "doc_type":           "legislation",
        "issue_tags":         [],
        "source_name":        SOURCE_NAMES.get(bill_type, "Congress.gov"),
    }

def fetch_bills(congress: int = 119, bill_type: str = "hr", limit: int = 50, offset: int = 0) -> list[dict]:
    """One page of bills, most recently updated first."""
    resp = http.get(
        f"{BASE}/bill/{congress}/{bill_type}",
        params={"api_key": API_KEY, "limit": limit, "offset": offset,
                # a space, not "+": httpx would send a literal "+" as %2B, which the API ignores
                "sort": "updateDate desc", "format": "json"},
    )
    return [to_bill(b, bill_type) for b in resp.json().get("bills", []) if b.get("title")]

def fetch_all_bills(congress: int, bill_type: str, since: str | None = None) -> list[dict]:
    """Every bill of one type (or only those updated on/after `since`,
    YYYY-MM-DD), fetched up front so the list can't shift under pagination
    while bills are being updated during a long ingest."""
    bills, offset = {}, 0
    while True:
        page = fetch_bills(congress, bill_type, limit=PAGE, offset=offset)
        if not page:
            break
        for b in page:
            if not since or (b["date"] or "") >= since:
                bills.setdefault(b["url"], b)  # a bill updated mid-listing can appear twice
        # pages are newest-updated first, so once a page reaches past `since`, stop
        if since and min(b["date"] or "" for b in page) < since:
            break
        offset += PAGE
    return sorted(bills.values(), key=lambda b: b["date"] or "", reverse=True)

def fetch_policy_area(bill_url: str) -> str | None:
    """e.g. "Health". Assigned by CRS, usually within a few weeks of introduction."""
    resp = http.get(bill_url.split("?")[0], params={"api_key": API_KEY, "format": "json"})
    return ((resp.json().get("bill") or {}).get("policyArea") or {}).get("name")

def fetch_text_versions(bill_url: str) -> list[dict]:
    """The bill's published text versions, e.g. "Introduced in House",
    "Engrossed in House", "Referred in Senate", "Public Law"."""
    resp = http.get(bill_url.split("?")[0] + "/text",
                    params={"api_key": API_KEY, "format": "json"})
    return resp.json().get("textVersions", [])

def newest_version(versions: list[dict]) -> dict | None:
    # undated versions (e.g. a just-enrolled bill) come first in the API's own
    # order, which is newest-first, so fall back to that order
    dated = [v for v in versions if v.get("date")]
    return max(dated, key=lambda v: v["date"]) if dated else (versions[0] if versions else None)

def earliest_version(versions: list[dict]) -> dict | None:
    # usually "Introduced in ..."; some bills (e.g. reconciliation) start as "Reported in ..."
    dated = [v for v in versions if v.get("date")]
    return min(dated, key=lambda v: v["date"]) if dated else (versions[-1] if versions else None)

def version_text_url(version: dict | None) -> str | None:
    """Formatted Text (.htm) if published, else PDF."""
    if not version:
        return None
    formats = {f.get("type"): f.get("url") for f in version.get("formats", [])}
    return formats.get("Formatted Text") or formats.get("PDF")
