"""PII and secret redaction — strips PII and credentials before LLM calls or audit logs."""
from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b(\+1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"), "[CARD]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
]

# Secret patterns: (compiled regex, label)
_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    # GitHub tokens
    (re.compile(r"\bghp_[A-Za-z0-9]{36,}\b"), "github_pat"),
    (re.compile(r"\bgho_[A-Za-z0-9]{36,}\b"), "github_oauth"),
    (re.compile(r"\bghs_[A-Za-z0-9]{36,}\b"), "github_app"),
    (re.compile(r"\bghr_[A-Za-z0-9]{36,}\b"), "github_refresh"),
    # AWS
    (re.compile(r"\bAKIA[A-Z0-9]{16}\b"), "aws_access_key"),
    (re.compile(r"(?i)aws_secret[_\s]*=\s*['\"]?([A-Za-z0-9/+]{40})['\"]?"), "aws_secret"),
    # Slack
    (re.compile(r"\bxoxb-[0-9A-Za-z\-]{40,}\b"), "slack_bot_token"),
    (re.compile(r"\bxoxp-[0-9A-Za-z\-]{40,}\b"), "slack_user_token"),
    (re.compile(r"\bxoxs-[0-9A-Za-z\-]{40,}\b"), "slack_session_token"),
    # Generic sk-/pk- (OpenAI, Stripe, Anthropic, etc.)
    (re.compile(r"\bsk-[A-Za-z0-9\-_]{20,}\b"), "secret_key"),
    (re.compile(r"\bpk-[A-Za-z0-9\-_]{20,}\b"), "public_key"),
    # Anthropic API keys
    (re.compile(r"\bak-[A-Za-z0-9\-_]{10,}\b"), "anthropic_key"),
    # PyPI tokens
    (re.compile(r"\bpypi-[A-Za-z0-9\-_]{32,}\b"), "pypi_token"),
    # npm tokens
    (re.compile(r"\bnpm_[A-Za-z0-9]{36,}\b"), "npm_token"),
    (re.compile(r"\bnp_[A-Za-z0-9]{20,}\b"), "npm_token"),
    # Render deploy keys
    (re.compile(r"\brk_[A-Za-z0-9]{32,}\b"), "render_key"),
    # GitHub fine-grained PATs
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b"), "github_fine_grained_pat"),
    # Vercel tokens
    (re.compile(r"\bvercel_[A-Za-z0-9]{24,}\b"), "vercel_token"),
    # Stripe keys
    (re.compile(r"\b(?:sk|pk|rk|whsec)_(?:live|test)_[A-Za-z0-9]{24,}\b"), "stripe_key"),
    # Twilio
    (re.compile(r"\bSK[a-f0-9]{32}\b"), "twilio_key"),
    (re.compile(r"\bAC[a-f0-9]{32}\b"), "twilio_account_sid"),
    # SendGrid
    (re.compile(r"\bSG\.[A-Za-z0-9\-_]{22,}\.[A-Za-z0-9\-_]{43,}\b"), "sendgrid_key"),
    # HuggingFace
    (re.compile(r"\bhf_[A-Za-z0-9]{34,}\b"), "huggingface_token"),
    # Generic high-entropy bearer tokens (≥32 alphanumeric chars after common prefixes)
    (re.compile(r"\b(?:Bearer|bearer)\s+([A-Za-z0-9\-_\.]{32,})\b"), "bearer_token"),
    # PEM private keys
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"), "private_key"),
    # URL-embedded passwords: scheme://user:password@host
    (re.compile(r"(?i)([a-z][a-z0-9+\-.]*://[^:@/\s]+:)([^@/\s]+)(@)"), "url_password"),
    # Generic assignment: api_key=, token=, password=, secret= followed by a value (8+ non-space chars)
    (re.compile(r"(?i)(api[_\-]?key|token|password|passwd|secret|auth)[_\-\s]*[=:]\s*['\"]?([^\s'\"]{8,})['\"]?"), "credential"),
]


def redact_pii(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_secrets(text: str) -> tuple[str, list[str]]:
    """Redact credentials from text. Returns (sanitized_text, [secret_types_found])."""
    found: list[str] = []
    for pattern, label in _SECRET_PATTERNS:
        if label == "url_password":
            # Keep scheme://user:***@host intact
            def _mask_url(m: re.Match) -> str:
                return m.group(1) + "[REDACTED]" + m.group(3)
            new_text = pattern.sub(_mask_url, text)
        elif label == "credential":
            # Keep the key name, redact the value
            def _mask_cred(m: re.Match) -> str:
                return m.group(1) + "=[REDACTED]"
            new_text = pattern.sub(_mask_cred, text)
        else:
            new_text = pattern.sub(f"[REDACTED:{label}]", text)
        if new_text != text:
            found.append(label)
            text = new_text
    return text, found


if __name__ == "__main__":
    # PII checks
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

    # Secret checks
    secret_samples = [
        ("github_pat", "token=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456789012", "github_pat"),
        ("aws", "AKIAIOSFODNN7EXAMPLE is the key", "aws_access_key"),
        ("slack", "xoxb-" + "1" * 12 + "-" + "2" * 12 + "-AbCdEfGhIjKlMnOpQrStUvWx", "slack_bot_token"),
        ("sk", "Authorization: Bearer sk-proj-abc123def456ghi789jkl012", "secret_key"),
        ("url_pw", "postgres://admin:supersecret@db.host:5432/mydb", "url_password"),
        ("generic", "DATABASE_PASSWORD=MyS3cr3tP@ss!", "credential"),
    ]
    for name, text, expected_label in secret_samples:
        out, found = redact_secrets(text)
        assert expected_label in found, f"FAIL secret/{name}: found={found!r} text={out!r}"
        assert text not in out or "[REDACTED" in out, f"FAIL secret/{name}: secret not redacted: {out!r}"
        print(f"ok secret/{name}: {out!r}")

    print("all pass")
