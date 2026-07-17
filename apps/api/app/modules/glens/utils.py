"""Shared GLens utilities."""
import re


def extract_json(raw: str) -> str:
    """Strip markdown fences and extract first JSON object."""
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    return m.group(0) if m else raw
