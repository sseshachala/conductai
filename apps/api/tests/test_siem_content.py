"""docs/siem detection content stays valid and tied to the real feed schema."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from app.modules.guard.audit_export import EXPORT_FIELDS

SIEM = Path(__file__).resolve().parents[3] / "docs" / "siem"
RULES = sorted((SIEM / "sentinel" / "analytics-rules").glob("*.yaml"))
CONF = (SIEM / "splunk" / "savedsearches.conf").read_text()
README = (SIEM / "README.md").read_text()
# Sentinel column -> feed field (the DCR transform in docs/reference/siem-feed.md)
COLUMNS = {"EventId": "id", "WorkspaceId": "workspace_id", "AiTool": "ai_tool", "ToolCall": "tool_call",
           "Decision": "decision", "RuleId": "rule_id", "RuleMessage": "rule_message", "UserEmail": "user_email",
           "UserId": "clerk_user_id", "AgentIdentityId": "agent_identity_id", "SessionId": "session_id",
           "PreviousHash": "previous_hash", "EntryHash": "entry_hash"}
SPLUNK_FIELDS = {"id", "workspace_id", "ai_tool", "tool_call", "decision", "rule_id", "rule_message", "user_email",
                 "clerk_user_id", "agent_identity_id", "session_id", "previous_hash", "entry_hash"}


def _stanzas():
    return {m.group(1): m.group(2) for m in re.finditer(r"^\[([^\]]+)\]\n((?:(?!^\[).*\n?)*)", CONF, re.M)}


def test_five_rules_everywhere():
    assert len(RULES) == 5
    assert len(_stanzas()) == 5
    arm = json.loads((SIEM / "sentinel" / "arm-template.json").read_text())
    assert len(arm["resources"]) == 5


def test_sentinel_yaml_is_well_formed_and_matches_arm():
    arm = json.loads((SIEM / "sentinel" / "arm-template.json").read_text())
    by_id = {r["name"].split("'")[-2]: r["properties"] for r in arm["resources"]}
    ids = set()
    for path in RULES:
        rule = yaml.safe_load(path.read_text())
        assert rule["kind"] == "Scheduled" and rule["severity"] in ("Low", "Medium", "High", "Informational")
        assert rule["query"].strip().startswith(("let ", "ConductAudit_CL")), path.name
        assert "ConductAudit_CL" in rule["query"]
        ids.add(rule["id"])
        assert by_id[rule["id"]]["query"] == rule["query"]
        assert by_id[rule["id"]]["displayName"] == rule["name"]
    assert len(ids) == 5 and ids == set(by_id)


def test_sentinel_lookback_within_platform_limit():
    for path in RULES:
        period = yaml.safe_load(path.read_text())["queryPeriod"]
        days = re.fullmatch(r"P(\d+)D", period)
        assert not days or int(days.group(1)) <= 14, f"{path.name}: scheduled rules allow at most 14 days"


def test_sentinel_columns_map_to_real_feed_fields():
    for path in RULES:
        query = yaml.safe_load(path.read_text())["query"]
        for col in set(re.findall(r"\b(?:Decision|ToolCall|RuleId|UserEmail|UserId|AgentIdentityId|"
                                  r"EventId|PreviousHash|EntryHash|WorkspaceId|AiTool|RuleMessage|SessionId)\b", query)):
            assert COLUMNS[col] in EXPORT_FIELDS
    assert set(COLUMNS.values()) <= set(EXPORT_FIELDS)


def test_splunk_searches_have_schedule_and_use_real_fields():
    for name, body in _stanzas().items():
        assert "search = " in body and "cron_schedule = " in body, name
        assert re.search(r"^dedup|\| dedup id", body, re.M), f"{name}: feed is at-least-once, dedup on id"
    assert SPLUNK_FIELDS <= set(EXPORT_FIELDS)
    used = set(re.findall(r"\b(decision|tool_call|rule_id|user_email|clerk_user_id|agent_identity_id|"
                          r"previous_hash|entry_hash|workspace_id|ai_tool)\b", CONF))
    assert used <= set(EXPORT_FIELDS)


def test_readme_field_table_uses_real_fields():
    section = README.split("## Field names")[1].split("##")[0]
    first_col = re.findall(r"^\| `([a-z_]+)`(?:, `([a-z_]+)`)? \|", section, re.M)
    fields = {f for pair in first_col for f in pair if f}
    assert fields and fields <= set(EXPORT_FIELDS)
