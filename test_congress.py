from dotenv import load_dotenv
load_dotenv()
from ingest.sources.congress import fetch_bills

bills = fetch_bills("environment", limit=10)
for bill in bills:
    print(bill["title"])
    print(bill["date"])
    print("---")