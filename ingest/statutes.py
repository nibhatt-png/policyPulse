"""U.S. Code citations in bill text: the link between bills and court rulings.

Bills are proposals and courts cite enacted law, so a bill and a ruling are
connected when the bill cites (usually amends) a U.S. Code section the ruling
interprets. Both store those sections, normalized like "42 U.S.C. § 5122",
in documents.issue_tags.
"""
import re

USC_TITLES = range(1, 55)
SECTION = r"\d+[a-z]*(?:\s?[-–]\s?\d+[a-z]*)*"    # 5122, 1395w-4, 300gg-91, 9837b
# "42 U.S.C. 5122", "42 U.S.C. § 5122", "(42 U.S.C. 1395w- 4(c)(2)(B))", "42 U.S.C. 9831 et seq."
USC_RE = re.compile(rf"\b(\d{{1,2}})\s+U\.\s?S\.\s?C\.\s*(?:§+\s*)?({SECTION})", re.I)
# "section 552(b)(3) of title 5, United States Code"
TITLE_RE = re.compile(rf"\bsections?\s+({SECTION})(?:\([^()\s]{{1,8}}\))*\s+of\s+title\s+(\d{{1,2}}),?\s+United\s+States\s+Code", re.I)

def normalize(title: str, section: str) -> str | None:
    if int(title) not in USC_TITLES:
        return None
    section = re.sub(r"\s", "", section).replace("–", "-").lower().rstrip("-")
    return f"{int(title)} U.S.C. § {section}"

def citations_in(text: str) -> list[str]:
    """Every citation, in order, with repeats."""
    found = [normalize(t, s) for t, s in USC_RE.findall(text)]
    found += [normalize(t, s) for s, t in TITLE_RE.findall(text)]
    return [c for c in found if c]

# A bill that amends one title often names sections bare after its long title:
# "To amend title 5, United States Code, ..." then "except for purposes of
# sections 552 and 552a" (H.R. 9778). Bare references are counted for that
# title only when the bill amends exactly one title, the section number is at
# least 100 (the bill's own sections are usually smaller), it isn't one of the
# bill's own section headers ("SEC. 102."), and it isn't followed by "of this
# Act", "of such Act", "of title 42", etc.
AMEND_TITLE_RE = re.compile(r"\bTo amend title (\d{1,2}),?\s+United\s+States\s+Code", re.I)
BARE_RE = re.compile(rf"\bsections?\s+({SECTION})((?:\([^()\s]{{1,8}}\))*)(?:,?\s+(?:and|or)\s+({SECTION}))?", re.I)
NOT_BARE_AFTER = re.compile(r"\s*(?:\([^()\s]{1,8}\))*,?\s+of\s+(?:this|that|such|the|title|chapter|part|subtitle|division)\b", re.I)
OWN_SECTION_RE = re.compile(r"\bSEC\.\s+(\d+[a-z]?)\.", re.I)

def bare_title_citations(text: str) -> list[str]:
    titles = {int(t) for t in AMEND_TITLE_RE.findall(text[:2000])}
    if len(titles) != 1:
        return []
    title = titles.pop()
    own = {s.lower() for s in OWN_SECTION_RE.findall(text)}
    found = []
    for m in BARE_RE.finditer(text):
        if NOT_BARE_AFTER.match(text, m.end()):
            continue
        for section in (m.group(1), m.group(3)):
            if not section:
                continue
            digits = re.match(r"\d+", section).group()
            if int(digits) >= 100 and section.lower() not in own:
                c = normalize(str(title), section)
                if c:
                    found.append(c)
    return found

def statutes_in(text: str) -> list[str]:
    """The distinct sections a bill's full text cites, sorted: what it stores in issue_tags."""
    return sorted(set(citations_in(text)) | set(bare_title_citations(text)))
