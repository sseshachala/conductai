"""Tests for the ``GuardDecision`` parser.

Pure Python — no NeMo, no HTTP, no async. If ``GuardDecision.parse`` maps
the ``guard_check`` response envelope to the right verdict, every
higher-level integration (Colang action, LLM provider) inherits correct
behaviour.
"""
from __future__ import annotations

import pytest

from conduct_nemo_guard._decisions import (
    ConductGuardBlocked,
    GuardDecision,
    _extract_rule_id,
    _strip_prefix,
)


# ── happy-path verdicts ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected_verdict",
    [
        ("", "allow"),
        ("ok", "allow"),
        ("OK", "allow"),
        ("ok — 0 rules checked", "allow"),
        ("  ok  ", "allow"),
    ],
)
def test_allow_prefixes(text: str, expected_verdict: str) -> None:
    d = GuardDecision.parse(text)
    assert d.verdict == expected_verdict
    assert d.rule_id is None


def test_advisory_carries_message_and_rule_id() -> None:
    d = GuardDecision.parse("advisory: minor deviation (rule=advisory-1)")
    assert d.verdict == "advisory"
    assert d.rule_id == "advisory-1"
    assert d.message and "minor deviation" in d.message


def test_warning_carries_message_and_rule_id() -> None:
    d = GuardDecision.parse("WARNING — approaching cost cap (rule=cost-cap-daily)")
    assert d.verdict == "warning"
    assert d.rule_id == "cost-cap-daily"
    assert d.message and "cost cap" in d.message


def test_blocked_carries_message_and_rule_id() -> None:
    d = GuardDecision.parse("BLOCKED — destructive deploy (rule=approve-prod-deploy)")
    assert d.verdict == "block"
    assert d.rule_id == "approve-prod-deploy"
    assert d.message and "destructive deploy" in d.message


def test_pending_approval_is_treated_as_approval_verdict() -> None:
    d = GuardDecision.parse("PENDING approval — waiting for NOC (rule=hitl-noc)")
    assert d.verdict == "approval"
    assert d.rule_id == "hitl-noc"


# ── unknown / defensive parsing ──────────────────────────────────────


def test_unknown_prefix_falls_back_to_unknown_verdict() -> None:
    d = GuardDecision.parse("something the server has not shipped yet")
    assert d.verdict == "unknown"
    assert d.raw == "something the server has not shipped yet"


def test_none_input_treated_as_allow() -> None:
    # Servers occasionally return no text field at all. Do not crash.
    d = GuardDecision.parse(None)  # type: ignore[arg-type]
    assert d.verdict == "allow"


def test_raw_text_is_preserved_verbatim() -> None:
    text = "BLOCKED — anything (rule=x)"
    d = GuardDecision.parse(text)
    assert d.raw == text  # audit surfaces quote this verbatim


# ── helpers ──────────────────────────────────────────────────────────


def test_strip_prefix_removes_marker_and_leading_punctuation() -> None:
    assert _strip_prefix("BLOCKED — foo bar", "BLOCKED") == "foo bar"
    assert _strip_prefix("advisory: minor thing", "advisory") == "minor thing"


def test_strip_prefix_returns_original_when_result_would_be_empty() -> None:
    # Guard against ever surfacing an empty message that hides the intent.
    assert _strip_prefix("BLOCKED", "BLOCKED") == "BLOCKED"


def test_extract_rule_id_finds_marker() -> None:
    assert _extract_rule_id("BLOCKED — foo (rule=my-rule)") == "my-rule"


def test_extract_rule_id_strips_trailing_punctuation() -> None:
    assert _extract_rule_id("advisory: rule=hitl-noc.") == "hitl-noc"


def test_extract_rule_id_returns_none_when_absent() -> None:
    assert _extract_rule_id("BLOCKED — no marker here") is None


# ── real-world server envelope (regression) ──────────────────────────


def test_parse_strips_ws_prefix_and_reads_bracket_rule() -> None:
    """Server wraps tool responses with '[ws:xxxxxxxx] ' for debug context
    (apps/api/app/modules/guard/routers/mcp.py:_text) and emits rule IDs
    as '[rule: <id>]'. Both must be transparent to the parser or every
    verdict falls through to 'unknown' and plugin flows never block."""
    raw = (
        "[ws:fd4b6608] BLOCKED — Account deletion needs a workspace "
        "admin's approval. \u2502  [rule: account-deletion-needs-a-workspace-admin-s-approval]"
    )
    d = GuardDecision.parse(raw)
    assert d.verdict == "block"
    assert d.rule_id == "account-deletion-needs-a-workspace-admin-s-approval"
    assert d.message and "Account deletion" in d.message


def test_extract_rule_id_supports_bracket_format() -> None:
    assert _extract_rule_id("BLOCKED — foo [rule: my-rule]") == "my-rule"


# ── ConductGuardBlocked exception ────────────────────────────────────


def test_blocked_exception_uses_message_when_available() -> None:
    d = GuardDecision.parse("BLOCKED — payload was too spicy (rule=r1)")
    exc = ConductGuardBlocked(d)
    assert "spicy" in str(exc)
    assert exc.decision is d


def test_blocked_exception_falls_back_to_raw_when_no_message() -> None:
    d = GuardDecision(verdict="block", raw="raw string, no parse")
    exc = ConductGuardBlocked(d)
    assert "raw string" in str(exc)
