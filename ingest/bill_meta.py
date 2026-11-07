# Display labels for Congress.gov bill types, e.g. ("HR", "132") -> "H.R. 132"
BILL_TYPE_LABELS = {
    "HR":      "H.R.",
    "S":       "S.",
    "HJRES":   "H.J.Res.",
    "SJRES":   "S.J.Res.",
    "HCONRES": "H.Con.Res.",
    "SCONRES": "S.Con.Res.",
    "HRES":    "H.Res.",
    "SRES":    "S.Res.",
}

def format_bill_number(bill_type: str, number: str | int) -> str:
    label = BILL_TYPE_LABELS.get(bill_type.upper(), bill_type.upper())
    return f"{label} {number}"

def bill_number_from_url(url: str) -> str | None:
    """https://api.congress.gov/v3/bill/118/hr/132?format=json -> "H.R. 132" """
    parts = url.split("?")[0].rstrip("/").split("/")
    try:
        i = parts.index("bill")
        return format_bill_number(parts[i + 2], parts[i + 3])
    except (ValueError, IndexError):
        return None
