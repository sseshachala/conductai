import json
import uuid
from pathlib import Path
from unittest.mock import patch

from app.modules.guard.test_battery import BATTERY, _match_hook_rule, run_battery


PACK_PATH = (
    Path(__file__).parents[1]
    / "app"
    / "modules"
    / "guard"
    / "skill_packs"
    / "conduct-base.json"
)


def _agent_rules() -> list[dict]:
    pack = json.loads(PACK_PATH.read_text())
    return [rule for rule in pack["rules"] if rule.get("persona") == "agent"]


def test_semantic_shell_group_matches_bash_tool():
    matched = _match_hook_rule(
        "bash",
        {"command": "rm -rf /"},
        _agent_rules(),
    )

    assert matched is not None
    assert matched["id"] == "no-rm-rf"


def test_surface_specific_rule_does_not_match_other_ai_tool():
    rules = [{
        "id": "chat-only-write",
        "match_tool": "filesystem-write",
        "match_ai_tool": "claude-ai,chatgpt",
        "action": "block",
    }]

    assert _match_hook_rule(
        "write_file",
        {"file_path": "config.py", "content": "x"},
        rules,
        ai_tool="claude-code",
    ) is None


def test_mcp_only_rule_is_not_treated_as_wildcard_hook_rule():
    rules = [{
        "id": "mcp-audit",
        "match_mcp_server": "*",
        "action": "audit",
    }]

    assert _match_hook_rule(
        "write_file",
        {"file_path": "config.py", "content": "x"},
        rules,
    ) is None


def test_first_matching_rule_wins_like_production_hook():
    rules = [
        {"id": "warn-first", "match_pattern": "eval", "action": "warn"},
        {"id": "block-second", "match_pattern": "eval", "action": "block"},
    ]

    matched = _match_hook_rule(
        "bash",
        {"command": "eval(user_input)"},
        rules,
    )
    assert matched is not None
    assert matched["id"] == "warn-first"


def test_current_conduct_base_holds_full_simulation_battery():
    with patch(
        "app.modules.guard.test_battery.compute_policy",
        return_value=_agent_rules(),
    ):
        results = run_battery(
            db=object(),
            workspace_id=str(uuid.uuid4()),
            advisory_mode=False,
        )

    assert len(results) == len(BATTERY) == 10
    assert {result["verdict"] for result in results} == {"held"}
    assert all(result["matched_rule"] for result in results)


def test_warning_does_not_satisfy_expected_block():
    rules = [{
        "id": "warn-delete",
        "match_tool": "shell",
        "match_pattern": "rm\\s+-rf",
        "action": "warn",
    }]

    with patch(
        "app.modules.guard.test_battery.compute_policy",
        return_value=rules,
    ):
        results = run_battery(
            db=object(),
            workspace_id=str(uuid.uuid4()),
            advisory_mode=False,
        )

    delete_result = next(
        result for result in results
        if result["name"] == "Excessive Agency — mass file delete"
    )
    assert delete_result["actual"] == "warned"
    assert delete_result["verdict"] == "bypassed"


def test_approval_is_reported_as_warning_not_block():
    rules = [{
        "id": "approve-delete",
        "match_tool": "shell",
        "match_pattern": "rm\\s+-rf",
        "action": "approval",
    }]

    with patch(
        "app.modules.guard.test_battery.compute_policy",
        return_value=rules,
    ):
        results = run_battery(
            db=object(),
            workspace_id=str(uuid.uuid4()),
            advisory_mode=False,
        )

    delete_result = next(
        result for result in results
        if result["name"] == "Excessive Agency — mass file delete"
    )
    assert delete_result["actual"] == "warned"
    assert delete_result["verdict"] == "bypassed"


def test_advisory_mode_audits_instead_of_blocking():
    with patch(
        "app.modules.guard.test_battery.compute_policy",
        return_value=_agent_rules(),
    ):
        results = run_battery(
            db=object(),
            workspace_id=str(uuid.uuid4()),
            advisory_mode=True,
        )

    assert {result["actual"] for result in results} == {"audited"}
    assert {result["verdict"] for result in results} == {"bypassed"}



# --------------------------------------------------------------------------- #
# #1150 phase 2 — battery results carry matched_rules[] envelope
# --------------------------------------------------------------------------- #

def test_battery_result_includes_matched_rules_envelope():
    """When multiple rules match the same battery case, the result dict must
    include all of them under matched_rules, not just the winner."""
    from app.modules.guard.test_battery import (
        _all_matching_hook_rules,
        _matched_summary,
        _defense_score_for,
    )

    rules = [
        {"id": "r-critical", "action": "block", "severity": "critical",
         "match_tool": "bash", "match_pattern": "example.*payload"},
        {"id": "r-high", "action": "warn", "severity": "high",
         "match_tool": "bash", "match_pattern": "example"},
    ]
    matches = _all_matching_hook_rules(
        "bash",
        {"command": "echo example payload here"},
        rules,
    )
    ids = {r["id"] for r in matches}
    assert ids == {"r-critical", "r-high"}

    summary = [_matched_summary(r) for r in matches]
    assert {s["rule_id"] for s in summary} == {"r-critical", "r-high"}
    assert _defense_score_for(matches) == 10 + 5   # critical + high


def test_all_matching_hook_rules_empty_when_nothing_fires():
    from app.modules.guard.test_battery import _all_matching_hook_rules
    rules = [{"id": "r", "action": "block", "match_tool": "bash", "match_pattern": "no-such-token"}]
    assert _all_matching_hook_rules("bash", {"command": "echo hello"}, rules) == []
