"""PII redaction for Brain block context — strips common PII before LLM calls."""
from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b(\+1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"), "[CARD]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
]


def redact_pii(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


if __name__ == "__main__":
    samples = [
        ("email", "contact me at foo@bar.com please", "[EMAIL]"),
        ("phone", "call 415-555-1234 now", "[PHONE]"),
        ("ssn", "ssn is 123-45-6789", "[SSN]"),
        ("card", "card 4111 1111 1111 1111 here", "[CARD]"),
        ("ip", "server at 192.168.1.1", "[IP]"),
    ]
    for name, text, expected_tag in samples:
        out = redact_pii(text)
        assert expected_tag in out, f"FAIL {name}: {out!r}"
        print(f"ok {name}: {out!r}")
    print("all pass")
