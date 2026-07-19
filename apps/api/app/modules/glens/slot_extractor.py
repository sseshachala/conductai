"""Pure-Python slot extraction — no LLM, no embeddings."""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import datetime, timedelta, timezone

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_MONTH_PAT = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"


def _month_key(s: str) -> int:
    s = s.lower().rstrip(".")
    for k, v in _MONTH_MAP.items():
        if s.startswith(k):
            return v
    return 0


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    last = monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}T23:59:59"


def extract_date_range(text: str) -> dict[str, str]:
    """Return {since, until} ISO date strings, or {} if no date found."""
    low = text.lower()
    now = datetime.now(timezone.utc)

    # "June 2026" / "Jul 2026"
    m = re.search(_MONTH_PAT + r"\s+(\d{4})", low)
    if m:
        month = _month_key(m.group(1))
        year = int(m.group(2))
        since, until = _month_bounds(year, month)
        return {"since": since, "until": until}

    # "2026-06" or "2026/06"
    m = re.search(r"\b(\d{4})[-/](\d{2})\b", low)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        since, until = _month_bounds(year, month)
        return {"since": since, "until": until}

    # "last month"
    if re.search(r"\blast\s+month\b", low):
        first = now.replace(day=1)
        prev = first - timedelta(days=1)
        since, until = _month_bounds(prev.year, prev.month)
        return {"since": since, "until": until}

    # "last week"
    if re.search(r"\blast\s+week\b", low):
        start = now - timedelta(days=now.weekday() + 7)
        end = start + timedelta(days=6)
        return {"since": start.strftime("%Y-%m-%d"), "until": end.strftime("%Y-%m-%d")}

    # "this month"
    if re.search(r"\bthis\s+month\b", low):
        since, until = _month_bounds(now.year, now.month)
        return {"since": since, "until": until}

    # "yesterday"
    if re.search(r"\byesterday\b", low):
        d = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        return {"since": d, "until": d}

    # bare year "in 2026" / "for 2026"
    m = re.search(r"\b(20\d{2})\b", low)
    if m:
        year = int(m.group(1))
        return {"since": f"{year}-01-01", "until": f"{year}-12-31"}

    return {}


def extract_decision(text: str) -> str | None:
    low = text.lower()
    if re.search(r"\bblock(ed|s)?\b", low):
        return "blocked"
    if re.search(r"\bwarn(ed|s|ing)?\b", low):
        return "warned"
    if re.search(r"\ballow(ed|s)?\b", low):
        return "allowed"
    return None


def extract_limit(text: str) -> int | None:
    m = re.search(r"\b(?:top|show|last|first)\s+(\d+)\b", text.lower())
    if m:
        return min(int(m.group(1)), 100)
    return None


def extract_slots(text: str) -> dict:
    slots: dict = {}
    slots.update(extract_date_range(text))
    d = extract_decision(text)
    if d:
        slots["decision"] = d
    lim = extract_limit(text)
    if lim:
        slots["limit"] = lim
    return slots
