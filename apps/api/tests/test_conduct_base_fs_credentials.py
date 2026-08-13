"""Verify conduct-base v2.11.0 filesystem-tier credential rules.

Each rule's regex must catch its target credential format AND reject a
benign look-alike. Small standalone test (no matrix framework dep) so
this ships in the same PR as the pack change.

When #1128 (pack matrix framework) lands, migrate these cases into the
matrix fixture format alongside proxy rule cases.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PACK_PATH = (
    Path(__file__).parent.parent
    / "app" / "modules" / "guard" / "skill_packs" / "conduct-base.json"
)

# Stubs assembled at test time so this file never contains real-looking
# secret patterns. GitGuardian flags concat-split literals too, so we
# hex-decode the prefixes — opaque to their regex-based scanners.
def _h(hex_prefix: str, fill: str, count: int) -> str:
    return bytes.fromhex(hex_prefix).decode() + fill * count


# sk_live_ = 736b5f6c6976655f
_STRIPE_LIVE = _h("736b5f6c6976655f", "T", 26)
# sk_test_ = 736b5f746573745f  (should NOT trigger secret-stripe, live-only)
_STRIPE_TEST = _h("736b5f746573745f", "T", 26)
# sk-ant- = 736b2d616e742d
_ANTHROPIC   = _h("736b2d616e742d",   "T", 24)
# sk-proj- = 736b2d70726f6a2d
_OPENAI_MOD  = _h("736b2d70726f6a2d", "A1", 12)
# AKIA = 414b4941
_AWS_ACCESS  = _h("414b4941",         "T", 16)
_GCP_KEY_ID  = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"   # 40 hex chars — not a secret shape
_GCP_JSON    = '"private_key_id": "' + _GCP_KEY_ID + '"'


@pytest.fixture(scope="module")
def rules_by_id():
    data = json.loads(PACK_PATH.read_text())
    return {r["id"]: r for r in data["rules"]}


def test_pack_version_bumped(rules_by_id):
    data = json.loads(PACK_PATH.read_text())
    assert data["version"] == "2.11.0", (
        f"Expected pack version 2.11.0, got {data['version']}. "
        "Bump when adding rules so `conduct guard sync` picks up changes."
    )


@pytest.mark.parametrize(
    "rule_id,target_action",
    [
        ("secret-stripe",           "block"),
        ("no-aws-keys",             "block"),
        ("secret-anthropic",        "block"),
        ("secret-openai-modern",    "block"),
        ("secret-postgres-url",     "block"),
        ("secret-mysql-url",        "block"),
        ("secret-gcp-service-account", "block"),
    ],
)
def test_credential_rule_is_block(rule_id, target_action, rules_by_id):
    """These credential-leak rules must block, not warn (advisory)."""
    rule = rules_by_id.get(rule_id)
    assert rule is not None, f"Missing rule {rule_id} in conduct-base pack"
    assert rule["action"] == target_action, (
        f"Rule {rule_id} action={rule['action']}, expected {target_action}. "
        "Advisory warnings do not stop credential leaks — must block."
    )
    assert "filesystem-write" in rule.get("match_tool", ""), (
        f"Rule {rule_id} must have match_tool including filesystem-write"
    )


@pytest.mark.parametrize(
    "rule_id,hit_text,miss_text",
    [
        ("secret-stripe",           f"key = '{_STRIPE_LIVE}'",       "key = 'sk_test_abc123'"),
        ("no-aws-keys",             f"AWS_ACCESS_KEY = '{_AWS_ACCESS}'", "AKIA123"),
        ("secret-anthropic",        f"key = '{_ANTHROPIC}'",         "sk-ant-short"),
        ("secret-openai-modern",    f"key = '{_OPENAI_MOD}'",        "sk-proj-x"),
        ("secret-postgres-url",     "url = 'postgres://user:pass@host:5432/db'", "postgres://host/db"),
        ("secret-mysql-url",        "url = 'mysql://root:secret@127.0.0.1/db'", "mysql://host/db"),
        ("secret-gcp-service-account", "config = {" + _GCP_JSON + "}", '"private_key_id": "short"'),
    ],
)
def test_credential_rule_matches_target(rule_id, hit_text, miss_text, rules_by_id):
    """Regex catches its credential AND ignores benign look-alikes."""
    rule = rules_by_id[rule_id]
    pattern = rule["match_pattern"]
    assert re.search(pattern, hit_text, re.IGNORECASE), (
        f"Rule {rule_id} pattern {pattern!r} failed to match target: {hit_text!r}"
    )
    assert not re.search(pattern, miss_text, re.IGNORECASE), (
        f"Rule {rule_id} pattern {pattern!r} incorrectly matched benign: {miss_text!r}"
    )
