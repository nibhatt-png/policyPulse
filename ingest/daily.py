"""The daily update: run by the launchd job in scripts/, or by hand.

    venv/bin/python -m ingest.daily

1. Ingest bills updated since the last successful run (plus a 2-day margin,
   so bills Congress.gov updates late aren't missed). If the Mac was off for a
   while it looks back further; after a month away it re-checks everything.
2. Fill in policy areas that CRS has assigned since (for the topic pages).
3. Rebuild the topic and "what's new" summaries whose bills changed.
4. Add court rulings for the next statutes in line (ingest/run_courts.py).

The weekly prune runs inside Postgres (pg_cron), not here.
"""
import subprocess, sys, time, urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT       = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "logs" / "last_daily_success"
MARGIN_DAYS = 2
MIN_DAYS    = 3
FULL_AFTER  = 30   # beyond this, a full re-check is simpler than a long window
OLLAMA_URL  = "http://localhost:11434/api/version"
# Only statutes cited by at least this many stored bills get court rulings:
# ~200 statutes, ~18 days of the free CourtListener quota, ~110 MB. Lowering
# it to 5 (~765 statutes) would outgrow Supabase's 500 MB free tier.
COURT_MIN_BILLS = 10

def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

def since_days() -> int:
    """0 means check every bill."""
    try:
        last = date.fromisoformat(STATE_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return MIN_DAYS
    days = (date.today() - last).days + MARGIN_DAYS
    return 0 if days > FULL_AFTER else max(days, MIN_DAYS)

def ollama_running() -> bool:
    try:
        urllib.request.urlopen(OLLAMA_URL, timeout=3)
        return True
    except OSError:
        return False

def ensure_ollama() -> None:
    """Embedding needs the local Ollama app; start it if it isn't running."""
    if ollama_running():
        return
    log("starting Ollama")
    subprocess.run(["open", "-a", "Ollama"], check=False)
    for _ in range(60):
        time.sleep(2)
        if ollama_running():
            return
    raise SystemExit("Ollama didn't start; the ingest needs it to embed bills.")

def step(name: str, *module_and_args: str) -> int:
    log(f"--- {name}")
    code = subprocess.run([sys.executable, "-u", "-m", *module_and_args], cwd=ROOT).returncode
    log(f"--- {name}: {'ok' if code == 0 else f'exit code {code}'}")
    return code

def main() -> int:
    days = since_days()
    log(f"daily update: {'all bills' if days == 0 else f'bills updated in the last {days} days'}")
    ensure_ollama()

    if step("ingest", "ingest.run_ingest", "--since-days", str(days)) != 0:
        log("ingest failed; not marking this run successful, so the next run looks back further")
        return 1
    if step("policy areas", "ingest.backfill_policy_areas") != 0:
        log("policy area fill failed; the next run will retry it")
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(date.today().isoformat())

    # summaries regenerate on demand too, so a failure here only costs speed
    if step("summaries", "rag.warm_summaries") != 0:
        log("some summaries weren't rebuilt; pages will generate them when visited")

    # Court rulings for the statutes bills cite most, as many as CourtListener's
    # free quota (125 requests a day) allows; each run continues where the last
    # stopped. Takes up to ~2.5 hours because of the 50-requests-an-hour limit.
    if step("court rulings", "ingest.run_courts", "--min-bills", str(COURT_MIN_BILLS),
            "--order", "relevant") != 0:
        log("court rulings step failed; the next run continues where it stopped")
    log("daily update done")
    return 0

if __name__ == "__main__":
    sys.exit(main())
