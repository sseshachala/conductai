"""PII and secret redaction — strips PII and credentials before LLM calls or audit logs.

Detection strategy (3 layers):
  1. Structural — unmistakable high-confidence formats (AKIA, ghp_, PEM). Zero false positives.
  2. Bare-in-text — tokens that appear without keyword context (sk-, xox*, ak-, Bearer).
  3. Context-aware — catch-all: any value ≥16 chars after a credential keyword. Catches any
     new service automatically without needing a new pattern.

Adding support for a new service: if their tokens appear near keywords (api_key=, token=, secret=),
the context-aware layer already catches them. Only add a structural or bare pattern if tokens
appear completely naked in text with no surrounding keyword.
"""
from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b(\+1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"), "[CARD]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
]

# ── Layer 1: Structural — unmistakable prefixes, zero false positives ─────────
_STRUCTURAL: list[tuple[re.Pattern, str]] = [
    # AWS access key ID
    (re.compile(r"\bAKIA[A-Z0-9]{16}\b"), "aws_access_key"),
    # GitHub tokens (all variants incl. fine-grained PATs)
    (re.compile(r"\bgh[psotr]_[A-Za-z0-9]{36,}\b"), "github_token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b"), "github_fine_grained_pat"),
    # PEM private keys
    (re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?"
        r"-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
    ), "private_key"),
]

# ── Layer 2: Bare-in-text — tokens that appear WITHOUT keyword context ────────
_BARE: list[tuple[re.Pattern, str]] = [
    # Slack tokens (always start with xox)
    (re.compile(r"\bxox[bpsr]-[0-9A-Za-z\-]{30,}\b"), "slack_token"),
    # sk-/pk- style keys (OpenAI, Anthropic, Stripe, etc.)
    (re.compile(r"\bsk-[A-Za-z0-9\-_]{20,}\b"), "secret_key"),
    (re.compile(r"\bpk-[A-Za-z0-9\-_]{20,}\b"), "public_key"),
    # ak- (Anthropic API keys, short format)
    (re.compile(r"\bak-[A-Za-z0-9\-_]{10,}\b"), "api_key"),
    # Stripe live/test keys that appear bare
    (re.compile(r"\b(?:sk|pk|rk|whsec)_(?:live|test)_[A-Za-z0-9]{24,}\b"), "stripe_key"),
    # Bearer tokens in Authorization headers
    (re.compile(r"(?i)\bBearer\s+([A-Za-z0-9\-_\.]{32,})\b"), "bearer_token"),
    # URL-embedded passwords: scheme://user:password@host
    (re.compile(r"(?i)([a-z][a-z0-9+\-.]*://[^:@/\s]+:)([^@/\s]{4,})(@)"), "url_password"),
]

# ── Layer 3: Context-aware — catch-all for any service ───────────────────────
# Fires when a credential keyword precedes a value ≥16 chars.
# Covers: PyPI, npm, HuggingFace, Vercel, Render, Twilio, SendGrid, any new service.
_CONTEXT_KEYWORDS = (
    r"api[_\-]?key|token|password|passwd|secret|auth(?:orization)?|"
    r"credential|access[_\-]?key|private[_\-]?key|client[_\-]?secret|"
    r"client[_\-]?id|bearer|api[_\-]?token|service[_\-]?key"
)
_CONTEXT_AWARE: list[tuple[re.Pattern, str]] = [
    (re.compile(
        rf"(?i)(?:{_CONTEXT_KEYWORDS})\s*[=:\"]\s*['\"]?([A-Za-z0-9\-_\.+/!@#$%^&*(){{}}]{{8,}})['\"]?"
    ), "credential"),
]

# Combined in evaluation order: structural → bare → context
_SECRET_PATTERNS: list[tuple[re.Pattern, str, str]] = (
    [(p, label, "structural") for p, label in _STRUCTURAL] +
    [(p, label, "bare") for p, label in _BARE] +
    [(p, label, "context") for p, label in _CONTEXT_AWARE]
)


def redact_pii(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_secrets(text: str) -> tuple[str, list[str]]:
    """Redact credentials from text. Returns (sanitized_text, [secret_types_found])."""
    found: list[str] = []
    for pattern, label, layer in _SECRET_PATTERNS:
        if label == "url_password":
            def _mask_url(m: re.Match) -> str:
                return m.group(1) + "[REDACTED]" + m.group(3)
            new_text = pattern.sub(_mask_url, text)
        elif layer == "context":
            # Keep keyword, redact value
            def _mask_ctx(m: re.Match) -> str:
                full = m.group(0)
                val = m.group(1)
                return full[: full.rfind(val)] + "[REDACTED]"
            new_text = pattern.sub(_mask_ctx, text)
        elif label == "bearer_token":
            def _mask_bearer(m: re.Match) -> str:
                return m.group(0)[: m.start(1) - m.start()] + "[REDACTED]"
            new_text = pattern.sub(lambda m: "Bearer [REDACTED]", text)
        else:
            new_text = pattern.sub(f"[REDACTED:{label}]", text)
        if new_text != text:
            found.append(label)
            text = new_text
    return text, found


if __name__ == "__main__":
    pii_samples = [
        ("email", "contact me at foo@bar.com please", "[EMAIL]"),
        ("phone", "call 415-555-1234 now", "[PHONE]"),
        ("ssn", "ssn is 123-45-6789", "[SSN]"),
        ("card", "card 4111 1111 1111 1111 here", "[CARD]"),
        ("ip", "server at 192.168.1.1", "[IP]"),
    ]
    for name, text, expected_tag in pii_samples:
        out = redact_pii(text)
        assert expected_tag in out, f"FAIL {name}: {out!r}"
        print(f"ok pii/{name}: {out!r}")

    secret_samples = [
        # Layer 1 — structural
        ("aws_key",       "AKIAIOSFODNN7EXAMPLE is the key",                          "aws_access_key"),
        ("github_pat",    "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456789012",              "github_token"),
        # Layer 2 — bare
        ("slack",         "xoxb-" + "1"*12 + "-" + "2"*12 + "-AbCdEfGhIjKlMnOpQrSt","slack_token"),
        ("sk",            "sk-proj-abc123def456ghi789jkl012mno345",                   "secret_key"),
        ("ak",            "ak-Lt0sinPUhhHUCCU",                                       "api_key"),
        ("stripe",        "sk_live_" + "a" * 24,                                        "stripe_key"),
        ("bearer",        "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9abc123", "bearer_token"),
        ("url_pw",        "postgres://admin:supersecret@db.host:5432/mydb",           "url_password"),
        # Layer 3 — context-aware (covers pypi, npm, hf, vercel, render, any new service)
        ("pypi",          "token=pypi-AgEIcHlwaS5vcmcCJDEyMzQ1Njc4OTAxMjM0NTY3",    "credential"),
        ("npm",           "npm_token=npm_abc123def456ghi789jkl012mno345pqr",          "credential"),
        ("huggingface",   "api_key=hf_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567",          "credential"),
        ("generic_pw",    "DATABASE_PASSWORD=MyS3cr3tP@ss!word123",                   "credential"),
        ("aws_secret",    "aws_secret=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",    "credential"),
    ]
    for name, text, expected_label in secret_samples:
        out, found = redact_secrets(text)
        status = "ok" if expected_label in found else "FAIL"
        print(f"{status} secret/{name}: found={found} → {out!r}")
        assert expected_label in found, f"FAIL secret/{name}: found={found!r}"

    print("\nall pass")
