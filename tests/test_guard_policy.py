"""
Tests for conduct_cli.guard._check_policy

Covers:
  - No policy file → allow
  - match_tool: wildcard, exact, comma-separated, no-match
  - match_pattern: hit, miss, invalid regex
  - match_path_pattern: hit, miss
  - match_tokens_before_gt: above threshold, at threshold, below threshold
  - action pass-through (block, warn, audit, approval)
  - First-match-wins ordering
  - Builtin policy rules from builtin_policies.yaml
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ── ensure conduct_cli is importable ─────────────────────────────────────────
CONDUCT_CLI_SRC = Path(__file__).resolve().parent.parent / "src"
if str(CONDUCT_CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CONDUCT_CLI_SRC))

import conduct_cli.guard as guard_mod
from conduct_cli.guard import _check_policy, POLICY_PATH

BUILTIN_POLICIES_YAML = (
    Path(__file__).resolve().parents[3]
    / "apps/api/app/modules/guard/builtin_policies.yaml"
)
CONDUCT_BASE_JSON = (
    Path(__file__).resolve().parents[3]
    / "apps/api/app/modules/guard/skill_packs/conduct-base.json"
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _write_policy(tmp_path: Path, rules: list[dict]) -> Path:
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({"version": "test", "rules": rules}))
    return p


def _rule(**kw) -> dict:
    return {
        "rule_id": kw.get("rule_id", "test-rule"),
        "match_tool": kw.get("match_tool", "*"),
        "match_pattern": kw.get("match_pattern", None),
        "match_path_pattern": kw.get("match_path_pattern", None),
        "action": kw.get("action", "block"),
        "message": kw.get("message", "Test violation"),
        **{k: v for k, v in kw.items()
           if k not in ("rule_id", "match_tool", "match_pattern",
                        "match_path_pattern", "action", "message")},
    }


@pytest.fixture()
def policy_path(tmp_path, monkeypatch):
    """Returns a factory; call it with rules to write policy and patch the path."""
    def _make(rules):
        p = _write_policy(tmp_path, rules)
        monkeypatch.setattr(guard_mod, "POLICY_PATH", p)
        return p
    return _make


@pytest.fixture()
def no_policy(tmp_path, monkeypatch):
    """Point POLICY_PATH at a non-existent file."""
    p = tmp_path / "missing.json"
    monkeypatch.setattr(guard_mod, "POLICY_PATH", p)


# ── no policy file ────────────────────────────────────────────────────────────

class TestNoPolicyFile:
    def test_allow_when_file_missing(self, no_policy):
        _, action, rule_id, _ = _check_policy("bash", {"command": "ls"})
        assert action == "allow"
        assert rule_id is None

    def test_allow_when_file_corrupt(self, tmp_path, monkeypatch):
        p = tmp_path / "policy.json"
        p.write_text("not json {{{{")
        monkeypatch.setattr(guard_mod, "POLICY_PATH", p)
        _, action, _, _ = _check_policy("bash", {"command": "ls"})
        assert action == "allow"


# ── match_tool ────────────────────────────────────────────────────────────────

class TestMatchTool:
    def test_wildcard_matches_any_tool(self, policy_path):
        policy_path([_rule(match_tool="*", action="warn")])
        _, action, _, _ = _check_policy("bash", {})
        assert action == "warn"

    def test_exact_tool_match(self, policy_path):
        # semantic group "shell" matches raw tool "bash"
        policy_path([_rule(match_tool="shell", action="warn")])
        _, action, _, _ = _check_policy("bash", {})
        assert action == "warn"

    def test_exact_tool_no_match(self, policy_path):
        # "filesystem-write" does not match "bash"
        policy_path([_rule(match_tool="filesystem-write", action="block")])
        _, action, _, _ = _check_policy("bash", {})
        assert action == "allow"

    def test_comma_separated_includes_tool(self, policy_path):
        # "shell,filesystem-write" matches "edit" (filesystem-write group)
        policy_path([_rule(match_tool="shell,filesystem-write", action="warn")])
        _, action, _, _ = _check_policy("edit", {})
        assert action == "warn"

    def test_comma_separated_excludes_tool(self, policy_path):
        # "shell,filesystem-write" does not match "read" (filesystem-read group)
        policy_path([_rule(match_tool="shell,filesystem-write", action="warn")])
        _, action, _, _ = _check_policy("read", {})
        assert action == "allow"

    def test_tool_name_case_insensitive(self, policy_path):
        policy_path([_rule(match_tool="Bash", action="warn")])
        _, action, _, _ = _check_policy("bash", {})
        assert action == "warn"


# ── match_ai_tool (surface filtering) ────────────────────────────────────────

def _surface_rule(**kw):
    return _rule(match_tool="shell", match_pattern=r".*", **kw)

class TestMatchAiTool:
    def test_surface_match_blocks(self, policy_path):
        policy_path([_surface_rule(match_ai_tool="claude-ai", action="block")])
        _, action, _, _ = _check_policy("bash", {"command": "ls"}, ai_tool="claude-ai")
        assert action == "block"

    def test_surface_no_match_allows(self, policy_path):
        # rule targets claude-ai, tool is claude-code — should not fire
        policy_path([_surface_rule(match_ai_tool="claude-ai", action="block")])
        _, action, _, _ = _check_policy("bash", {"command": "ls"}, ai_tool="claude-code")
        assert action == "allow"

    def test_surface_multi_targets(self, policy_path):
        # comma-separated: matches any listed surface
        policy_path([_surface_rule(match_ai_tool="claude-ai,openai-chatgpt", action="warn")])
        _, action, _, _ = _check_policy("bash", {"command": "ls"}, ai_tool="openai-chatgpt")
        assert action == "warn"

    def test_no_match_ai_tool_field_always_fires(self, policy_path):
        # rule with no match_ai_tool applies to all surfaces
        policy_path([_surface_rule(action="warn")])
        _, action, _, _ = _check_policy("bash", {"command": "ls"}, ai_tool="cursor")
        assert action == "warn"

    def test_unknown_surface_skipped(self, policy_path):
        # empty ai_tool string doesn't match a specific surface rule
        policy_path([_surface_rule(match_ai_tool="claude-ai", action="block")])
        _, action, _, _ = _check_policy("bash", {"command": "ls"}, ai_tool="")
        assert action == "allow"


# ── match_pattern ─────────────────────────────────────────────────────────────

class TestMatchPattern:
    def test_pattern_hit(self, policy_path):
        policy_path([_rule(match_pattern=r"rm\s+-rf", action="block")])
        _, action, _, _ = _check_policy("bash", {"command": "rm -rf /tmp/foo"})
        assert action == "block"

    def test_pattern_miss(self, policy_path):
        policy_path([_rule(match_pattern=r"DROP TABLE", action="block")])
        _, action, _, _ = _check_policy("bash", {"command": "select * from users"})
        assert action == "allow"

    def test_pattern_case_insensitive(self, policy_path):
        policy_path([_rule(match_pattern=r"drop table", action="block")])
        _, action, _, _ = _check_policy("bash", {"command": "DROP TABLE users;"})
        assert action == "block"

    def test_invalid_regex_skips_rule(self, policy_path):
        policy_path([_rule(match_pattern=r"[invalid(", action="block")])
        _, action, _, _ = _check_policy("bash", {"command": "anything"})
        assert action == "allow"

    def test_pattern_searches_full_input_json(self, policy_path):
        policy_path([_rule(match_pattern=r"secret_value", action="warn")])
        _, action, _, _ = _check_policy("write", {"content": "secret_value = 'abc'"})
        assert action == "warn"


# ── match_path_pattern ────────────────────────────────────────────────────────

class TestMatchPathPattern:
    def test_path_hit_via_file_path(self, policy_path):
        policy_path([_rule(match_path_pattern=r"\.(pem|key)$", action="block")])
        _, action, _, _ = _check_policy("write", {"file_path": "/project/id_rsa.key"})
        assert action == "block"

    def test_path_hit_via_path_field(self, policy_path):
        policy_path([_rule(match_path_pattern=r"\.env$", action="block")])
        _, action, _, _ = _check_policy("edit", {"path": "/project/.env"})
        assert action == "block"

    def test_path_miss(self, policy_path):
        policy_path([_rule(match_path_pattern=r"\.env$", action="block")])
        _, action, _, _ = _check_policy("edit", {"file_path": "/project/app.py"})
        assert action == "allow"

    def test_invalid_path_regex_skips(self, policy_path):
        policy_path([_rule(match_path_pattern=r"[bad(", action="block")])
        _, action, _, _ = _check_policy("write", {"file_path": "/any/file.py"})
        assert action == "allow"


# ── match_tokens_before_gt ────────────────────────────────────────────────────

class TestMatchTokensBeforeGt:
    def test_above_threshold_fires(self, policy_path):
        policy_path([_rule(match_tokens_before_gt=50000, action="warn")])
        _, action, _, _ = _check_policy("bash", {}, tokens_before=60000)
        assert action == "warn"

    def test_at_threshold_does_not_fire(self, policy_path):
        policy_path([_rule(match_tokens_before_gt=50000, action="warn")])
        _, action, _, _ = _check_policy("bash", {}, tokens_before=50000)
        assert action == "allow"

    def test_below_threshold_does_not_fire(self, policy_path):
        policy_path([_rule(match_tokens_before_gt=50000, action="warn")])
        _, action, _, _ = _check_policy("bash", {}, tokens_before=10000)
        assert action == "allow"

    def test_no_threshold_field_ignores_tokens(self, policy_path):
        policy_path([_rule(match_tool="*", action="warn")])
        _, action, _, _ = _check_policy("bash", {}, tokens_before=999999)
        assert action == "warn"

    def test_threshold_string_value_coerced(self, policy_path):
        policy_path([_rule(match_tokens_before_gt="50000", action="warn")])
        _, action, _, _ = _check_policy("bash", {}, tokens_before=60000)
        assert action == "warn"


# ── actions and return values ─────────────────────────────────────────────────

class TestReturnValues:
    def test_rule_id_returned(self, policy_path):
        policy_path([_rule(rule_id="no-rm-rf", action="block")])
        _, action, rule_id, _ = _check_policy("bash", {})
        assert rule_id == "no-rm-rf"

    def test_message_returned(self, policy_path):
        policy_path([_rule(action="block", message="Custom message")])
        _, _, _, msg = _check_policy("bash", {})
        assert msg == "Custom message"

    def test_action_block(self, policy_path):
        policy_path([_rule(action="block")])
        _, action, _, _ = _check_policy("bash", {})
        assert action == "block"

    def test_action_warn(self, policy_path):
        policy_path([_rule(action="warn")])
        _, action, _, _ = _check_policy("bash", {})
        assert action == "warn"

    def test_action_audit(self, policy_path):
        policy_path([_rule(action="audit")])
        _, action, _, _ = _check_policy("bash", {})
        assert action == "audit"

    def test_action_approval(self, policy_path):
        policy_path([_rule(action="approval")])
        _, action, _, _ = _check_policy("bash", {})
        assert action == "approval"

    def test_first_match_wins(self, policy_path):
        policy_path([
            _rule(rule_id="first", match_pattern=r"secret", action="block"),
            _rule(rule_id="second", match_pattern=r"secret", action="warn"),
        ])
        _, action, rule_id, _ = _check_policy("bash", {"cmd": "secret"})
        assert action == "block"
        assert rule_id == "first"

    def test_allow_returns_none_rule(self, policy_path):
        policy_path([_rule(match_pattern=r"no-match-ever-xyz", action="block")])
        rule, action, rule_id, msg = _check_policy("bash", {})
        assert rule is None
        assert action == "allow"
        assert rule_id is None
        assert msg is None


# ── builtin policies integration ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def builtin_rules():
    """Load rules from conduct-base.json (falls back to builtin_policies.yaml)."""
    import json as _json  # noqa: PLC0415

    if CONDUCT_BASE_JSON.exists():
        rules = _json.loads(CONDUCT_BASE_JSON.read_text())["rules"]
        # conduct-base uses "id"; _check_policy reads "rule_id"
        for r in rules:
            if "id" in r and "rule_id" not in r:
                r["rule_id"] = r["id"]
        return rules
    pytest.importorskip("yaml")
    import yaml  # noqa: PLC0415
    if not BUILTIN_POLICIES_YAML.exists():
        pytest.skip(f"builtin_policies.yaml not found at {BUILTIN_POLICIES_YAML}")
    return yaml.safe_load(BUILTIN_POLICIES_YAML.read_text())


@pytest.fixture()
def builtin_policy_path(tmp_path, monkeypatch, builtin_rules):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({"version": "builtin", "rules": builtin_rules}))
    monkeypatch.setattr(guard_mod, "POLICY_PATH", p)


class TestBuiltinPolicies:
    # ── Destructive ───────────────────────────────────────────────────────────
    def test_no_rm_rf_blocks(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "rm -rf /tmp/test"})
        assert action == "block"
        assert rule_id == "no-rm-rf"

    def test_no_rm_rf_misses_plain_rm(self, builtin_policy_path):
        _, _, rule_id, _ = _check_policy("bash", {"command": "rm file.txt"})
        assert rule_id != "no-rm-rf"

    def test_no_git_reset_hard_blocks(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "git reset --hard HEAD~1"})
        assert action == "block"
        assert rule_id == "no-git-reset-hard"

    def test_no_force_push_blocks(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "git push --force origin main"})
        assert action == "block"
        assert rule_id == "no-force-push"

    def test_no_force_push_short_flag(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "git push -f origin main"})
        assert action == "block"
        assert rule_id == "no-force-push"

    def test_no_drop_table_blocks(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "DROP TABLE users;"})
        assert action == "block"
        assert rule_id == "no-drop-table"

    # ── Permissions ───────────────────────────────────────────────────────────
    def test_no_sudo_blocks(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "sudo apt-get install pkg"})
        assert action == "block"
        assert rule_id == "no-sudo"

    def test_no_chmod_777_warns(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "chmod 777 /etc/passwd"})
        assert action == "warn"
        assert rule_id == "no-chmod-permissive"

    # ── Secrets ───────────────────────────────────────────────────────────────
    def test_no_env_commits_blocks(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "git add .env && git commit -m fix"})
        assert action == "block"
        assert rule_id == "no-env-commits"

    def test_no_hardcoded_secrets_warns(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy(
            "write",
            {"content": "API_KEY='Abc123XyzLong456AbcXyz789'"},
        )
        assert action == "warn"
        assert rule_id == "no-hardcoded-secrets"

    def test_no_private_key_files_blocks(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("write", {"file_path": "/project/server.pem"})
        assert action == "block"
        assert rule_id == "no-private-key-files"

    # ── Production gates ──────────────────────────────────────────────────────
    def test_approve_prod_deploy(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "deploy to production"})
        assert action == "approval"
        assert rule_id == "approve-prod-deploy"

    def test_approve_db_migration(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "alembic upgrade head"})
        assert action == "approval"
        assert rule_id == "approve-db-migration-prod"

    # ── Token efficiency ──────────────────────────────────────────────────────
    def test_warn_deterministic_compute_sort_uniq(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "sort users.csv | uniq -c"})
        assert action == "warn"
        assert rule_id == "warn-deterministic-compute"

    def test_warn_deterministic_compute_grep_count(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "grep -c 'ERROR' app.log"})
        assert action == "warn"
        assert rule_id == "warn-deterministic-compute"

    def test_warn_deterministic_compute_wc_l(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "cat data.txt | wc -l"})
        assert action == "warn"
        assert rule_id == "warn-deterministic-compute"

    def test_warn_deterministic_compute_python_oneliner(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "python -c 'print(sum([1,2,3]))'"}  )
        assert action == "warn"
        assert rule_id == "warn-deterministic-compute"

    def test_warn_deterministic_compute_no_false_positive(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {"command": "git status"})
        assert rule_id != "warn-deterministic-compute"

    def test_warn_large_context_above_threshold(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {}, tokens_before=60000)
        assert action == "warn"
        assert rule_id == "warn-large-context-dump"

    def test_warn_large_context_at_threshold_does_not_fire(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {}, tokens_before=50000)
        assert rule_id != "warn-large-context-dump"

    def test_warn_large_context_below_threshold_does_not_fire(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy("bash", {}, tokens_before=1000)
        assert rule_id != "warn-large-context-dump"



    # ── Vision / OCR ──────────────────────────────────────────────────────────
    def test_proxy_audit_vision_input_png(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy(
            "bash", {"content": "data:image/png;base64,iVBORw0KGgo="}
        )
        assert action == "audit"
        assert rule_id == "proxy-audit-vision-input"

    def test_proxy_audit_vision_input_jpeg(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy(
            "bash", {"content": "data:image/jpeg;base64,/9j/4AAQ="}
        )
        assert action == "audit"
        assert rule_id == "proxy-audit-vision-input"

    def test_proxy_audit_vision_no_false_positive(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy(
            "bash", {"content": "just plain text, no images here"}
        )
        assert rule_id != "proxy-audit-vision-input"

    def test_audit_image_file_read_png(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy(
            "read", {"file_path": "/tmp/scan_result.png"}
        )
        assert action == "audit"
        assert rule_id == "audit-image-file-read"

    def test_audit_image_file_read_pdf(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy(
            "read", {"file_path": "/docs/contract.pdf"}
        )
        assert action == "audit"
        assert rule_id == "audit-image-file-read"

    def test_audit_image_file_read_no_false_positive(self, builtin_policy_path):
        _, action, rule_id, _ = _check_policy(
            "read", {"file_path": "/src/main.py"}
        )
        assert rule_id != "audit-image-file-read"
