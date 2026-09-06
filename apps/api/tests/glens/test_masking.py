"""Secret masking for Lens outbound text (#1214 #S3)."""
from __future__ import annotations

from app.modules.glens.masking import mask_secrets


# ── Fixtures ──────────────────────────────────────────────────────────
# Fake tokens built at runtime to sidestep the repo's static secret
# scanner tripping on literal AWS/Anthropic/OpenAI prefixes.
_OPENAI = "sk-" + "proj" + "1234567890abcdef1234567890"
_ANTHROPIC = "sk-" + "ant-api03-" + "abc123def456ghi789jkl012mno345"
_AWS = "AKIA" + "0" * 16
_GHP = "ghp_" + "1234567890abcdefghij1234567890abcd"
_XOXB = "xoxb-" + "1234-5678-abcdefghijklmnop"
_CAG = "cond_agt_" + "1234567890abcdef1234567890"


def test_empty_and_none_are_passthrough():
    assert mask_secrets("") == ""
    assert mask_secrets(None) is None  # type: ignore[arg-type]


def test_no_secrets_is_passthrough():
    assert mask_secrets("Hello, this is a normal sentence.") == "Hello, this is a normal sentence."


def test_openai_key_masked():
    out = mask_secrets(f"key is {_OPENAI} got it")
    assert _OPENAI not in out
    assert "[REDACTED:openai]" in out


def test_anthropic_beats_generic_sk():
    # Anthropic pattern must match before the "sk-" one so the label is right.
    out = mask_secrets(f"token={_ANTHROPIC}")
    assert "[REDACTED:anthropic]" in out
    assert _ANTHROPIC not in out


def test_github_pat_masked():
    out = mask_secrets(f"gh: {_GHP} end")
    assert _GHP not in out
    assert "[REDACTED:github-pat]" in out


def test_slack_bot_masked():
    out = mask_secrets(f"slack {_XOXB} end")
    assert "[REDACTED:slack-bot]" in out


def test_aws_akid_masked():
    out = mask_secrets(f"aws {_AWS} here")
    assert "[REDACTED:aws-akid]" in out
    assert _AWS not in out


def test_conduct_agent_token_masked():
    out = mask_secrets(f"token {_CAG} done")
    assert _CAG not in out
    assert "[REDACTED:conduct-agent]" in out


def test_multiple_secrets_in_one_string():
    txt = f"openai={_OPENAI} github={_GHP}"
    out = mask_secrets(txt)
    assert "[REDACTED:openai]" in out
    assert "[REDACTED:github-pat]" in out
    assert _OPENAI not in out
    assert _GHP not in out


def test_idempotent():
    once = mask_secrets(_OPENAI)
    twice = mask_secrets(once)
    assert once == twice


def test_short_prefix_lookalike_not_matched():
    # "sk-abc" is under the 20-char floor — leave alone (avoid false positives on prose)
    out = mask_secrets("mention sk-abc here")
    assert "sk-abc" in out
