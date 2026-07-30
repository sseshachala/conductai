from __future__ import annotations

import inspect
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.modules.guard.coverage import workspace_coverage_matrix
from app.modules.guard.enforcement import (
    EnforcementMetadataError,
    conservative_custom_enforcement,
    validate_enforcement_metadata,
    validate_pack,
)
from app.modules.guard.models import GuardRuleOverride, WorkspaceCustomRule, WorkspaceSkillPack
from app.modules.guard.policy_engine import _skill_pack_version_key
from app.modules.guard.routers import policies
from app.modules.guard.routers.mcp import _match_policy
from scripts.generate_guard_enforcement_coverage import OUTPUT_PATH, render_document

PACK_DIR = Path(__file__).parents[1] / "app/modules/guard/skill_packs"


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class _CoverageDB:
    def __init__(self, installed, customs=None, overrides=None):
        self.rows = {
            WorkspaceSkillPack: installed,
            WorkspaceCustomRule: customs or [],
            GuardRuleOverride: overrides or [],
        }

    def query(self, model):
        return _Query(self.rows[model])


def _rule(**changes):
    rule = {
        "id": "test-rule",
        "persona": "agent",
        "match_tool": "shell",
        "match_pattern": "danger",
        "action": "block",
        "enforcement": {
            "version": 1,
            "proxy": "not_supported",
            "hook": "conditional",
            "mcp": "conditional",
            "runtime": "not_supported",
            "guarantee": "Blocks matching submitted tool actions when dependencies are met.",
            "requires": ["A governed hook or MCP guard_check is invoked"],
            "known_limitations": ["Workflow runtime does not evaluate shell-only rules"],
        },
    }
    rule.update(changes)
    return rule


def test_all_current_skill_packs_have_valid_enforcement_metadata():
    for path in sorted(PACK_DIR.glob("*.json")):
        validate_pack(json.loads(path.read_text()), source=str(path))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda rule: rule.pop("enforcement"), "enforcement must be an object"),
        (
            lambda rule: rule["enforcement"].update(hook="conditional", requires=[]),
            "conditional claims require",
        ),
        (
            lambda rule: rule.update(action="audit")
            or rule["enforcement"].update(hook="hard"),
            "cannot claim hard blocking",
        ),
        (
            lambda rule: rule["enforcement"].update(proxy="hard"),
            "proxy claim requires proxy persona",
        ),
        (
            lambda rule: rule.update(match_ai_tool="claude-ai")
            or rule["enforcement"].update(mcp="conditional"),
            "does not evaluate match_ai_tool",
        ),
    ],
)
def test_validator_rejects_missing_or_overclaimed_metadata(mutation, message):
    rule = _rule()
    mutation(rule)
    with pytest.raises(EnforcementMetadataError, match=message):
        validate_enforcement_metadata(rule)


def test_legacy_custom_rule_contract_is_conservative():
    metadata = conservative_custom_enforcement(_rule(enforcement=None))
    assert metadata["proxy"] == "not_supported"
    assert "hard" not in {metadata[surface] for surface in ("proxy", "hook", "mcp", "runtime")}


def test_semantic_version_key_orders_2_10_after_2_9():
    assert _skill_pack_version_key("2.10.0") > _skill_pack_version_key("2.9.0")


def test_mcp_expands_semantic_tool_groups():
    matched = _match_policy(
        "bash",
        {"command": "rm -rf build"},
        [_rule(match_tool="shell", match_pattern="rm -rf")],
    )
    assert matched is not None
    assert matched["id"] == "test-rule"


def test_coverage_uses_pinned_pack_and_override_does_not_change_capability():
    workspace_id = uuid.uuid4()
    installed = SimpleNamespace(
        workspace_id=workspace_id,
        pack_slug="conduct-test",
        pinned_version="1.0.0",
        installed_at=datetime.now(timezone.utc),
    )
    override = SimpleNamespace(
        rule_id="test-rule",
        disabled=False,
        action="warn",
        reason="Temporary exception",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    pinned = SimpleNamespace(
        slug="conduct-test",
        version="1.0.0",
        rules=[_rule()],
    )
    latest = SimpleNamespace(
        slug="conduct-test",
        version="2.0.0",
        rules=[_rule(enforcement={**_rule()["enforcement"], "hook": "not_supported"})],
    )
    db = _CoverageDB([installed], overrides=[override])

    def resolve(_db, slug, version):
        assert slug == "conduct-test"
        return pinned if version == "1.0.0" else latest

    with patch("app.modules.guard.coverage._get_pack", side_effect=resolve):
        row = workspace_coverage_matrix(db, workspace_id)[0]

    assert row["pack_version"] == "1.0.0"
    assert row["action"] == "warn"
    assert row["base_action"] == "block"
    assert row["hook"] == "conditional"
    assert row["exception_active"] is True
    assert row["enabled"] is True


def test_active_disable_changes_enabled_not_enforcement_capability():
    workspace_id = uuid.uuid4()
    installed = SimpleNamespace(
        workspace_id=workspace_id,
        pack_slug="conduct-test",
        pinned_version=None,
        installed_at=datetime.now(timezone.utc),
    )
    override = SimpleNamespace(
        rule_id="test-rule",
        disabled=True,
        action=None,
        reason="Temporary exception",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    pack = SimpleNamespace(slug="conduct-test", version="1.0.0", rules=[_rule()])
    db = _CoverageDB([installed], overrides=[override])
    with patch("app.modules.guard.coverage._get_pack", return_value=pack):
        row = workspace_coverage_matrix(db, workspace_id)[0]
    assert row["enabled"] is False
    assert row["hook"] == "conditional"
    assert row["exception_active"] is True


def test_expired_exception_is_visible_but_does_not_change_effective_policy():
    workspace_id = uuid.uuid4()
    installed = SimpleNamespace(
        workspace_id=workspace_id,
        pack_slug="conduct-test",
        pinned_version=None,
        installed_at=datetime.now(timezone.utc),
    )
    override = SimpleNamespace(
        rule_id="test-rule",
        disabled=True,
        action="warn",
        reason="Expired exception",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    pack = SimpleNamespace(slug="conduct-test", version="1.0.0", rules=[_rule()])
    db = _CoverageDB([installed], overrides=[override])
    with patch("app.modules.guard.coverage._get_pack", return_value=pack):
        row = workspace_coverage_matrix(db, workspace_id)[0]
    assert row["enabled"] is True
    assert row["action"] == "block"
    assert row["exception_active"] is False
    assert row["exception_expired"] is True
    assert row["hook"] == "conditional"


def test_coverage_endpoint_shape_and_permission_contract():
    source = inspect.getsource(policies.get_enforcement_coverage)
    assert 'require_permission("guard.policies.view")' in source
    expected = workspace_coverage_matrix(
        _CoverageDB(
            customs=[
                SimpleNamespace(
                    rule_id="custom-rule",
                    body={"id": "custom-rule", "action": "warn", "match_pattern": "x"},
                    enabled=True,
                    persona="agent",
                )
            ],
            installed=[],
        ),
        uuid.UUID("00000000-0000-0000-0000-000000000001"),
    )
    with patch.object(policies, "workspace_coverage_matrix", return_value=expected):
        result = policies.get_enforcement_coverage(
            db=object(),
            workspace_id="00000000-0000-0000-0000-000000000001",
            _="viewer",
        )
    assert result[0]["rule_id"] == "custom-rule"
    assert result[0]["proxy"] == "not_supported"
    assert result[0]["enforcement_version"] == 1
    policies.EnforcementCoverageOut.model_validate(result[0])


def test_generated_document_is_deterministic_and_checked_in():
    first = render_document()
    second = render_document()
    assert first == second
    assert OUTPUT_PATH.read_text() == first
    assert first.startswith("<!-- GENERATED FILE: DO NOT EDIT DIRECTLY. -->")
