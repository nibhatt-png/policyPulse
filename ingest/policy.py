"""Which bills the database keeps.

A bill is kept if it has passed at least one chamber (permanently), or if it
was introduced within the last GRACE_MONTHS (so new bills are searchable while
they're fresh). Bills that fail both are skipped at ingest and deleted by the
weekly prune (prune_stale_bills in ingest/schema.py), which applies the same
rule in SQL.
"""
import re
from calendar import monthrange
from datetime import date

# The main storage driver: most bills in the grace window never pass and are
# pruned later. Shorten it if space gets tight.
GRACE_MONTHS = 4

def grace_cutoff(today: date | None = None) -> date:
    """today minus GRACE_MONTHS, clamping the day like Postgres's
    `current_date - interval 'N months'` does (Jul 31 - 1 month = Jun 30)."""
    today = today or date.today()
    months = today.year * 12 + today.month - 1 - GRACE_MONTHS
    year, month = divmod(months, 12)
    month += 1
    return date(year, month, min(today.day, monthrange(year, month)[1]))

def in_grace_period(introduced_date: str | None, today: date | None = None) -> bool:
    return bool(introduced_date) and date.fromisoformat(introduced_date[:10]) >= grace_cutoff(today)

# Text version names (Congress.gov API textVersions[].type), checked against a
# sample of 400 119th-Congress bills. A bill has passed its origin chamber when
# it has an engrossed/enrolled/law version, or any version from the OTHER
# chamber ("Referred in Senate" or "Placed on Calendar Senate" for an H.R.;
# "Reported in House" for an S.). Same-chamber versions don't count:
# "Reported in House" on an H.R. is committee approval, not a floor vote, and
# "Placed on Calendar Senate" on an S. means it skipped committee, not passed.
FINAL_VERSION = re.compile(r"engrossed|enrolled|public law|private law", re.I)

# Latest actions that only happen after the origin chamber passed the bill.
# Covers the day or two before a passed bill's engrossed text is published.
PASSED_ACTION = re.compile(
    r"^(became (public|private) law|signed by president|presented to president|vetoed|"
    r"passed (house|senate)|passed/agreed to in (house|senate)|received in the (senate|house)|"
    r"held at the desk|message on (senate|house) action|resolving differences)", re.I)

def passed_a_chamber(version_types: list[str], origin_chamber: str | None,
                     latest_action: str | None) -> bool:
    other = "Senate" if origin_chamber == "House" else "House"
    if any(FINAL_VERSION.search(t or "") or other in (t or "") for t in version_types):
        return True
    return bool(PASSED_ACTION.search(latest_action or ""))

# Naming bills pass easily and say nothing about policy; skipped entirely.
CEREMONIAL = re.compile(
    r"^to (re)?(designate|name) (the|a) ("
    r"facility of the united states postal service"
    r"|department of veterans affairs"
    r"|.{0,80}\b(united states courthouse|federal building)\b)", re.I)

def is_ceremonial(title: str | None) -> bool:
    return bool(CEREMONIAL.search(title or ""))
