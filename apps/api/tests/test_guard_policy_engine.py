"""
Wave 3 — Guard policy_engine.py pure-function tests.

No DB, no FastAPI, no real pydantic-settings. All DB interactions are mocked
via MagicMock sessions so the functions themselves are exercised in isolation.
"""
import os
import sys
import types
import uuid
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Env vars — must be set before any app import
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

# ---------------------------------------------------------------------------
# Stub app.core.config
# ---------------------------------------------------------------------------
_cfg_stub = types.ModuleType("app.core.config")
_cfg_stub.settings = MagicMock(
    database_url="postgresql://test:test@localhost:5432/test_marshal",
    redis_url="redis://localhost:6379",
    sentry_dsn="",
    environment="test",
    log_level="INFO",
    clerk_secret_key="",
    clerk_frontend_api="",
)
sys.modules.setdefault("app.core.config", _cfg_stub)

# ---------------------------------------------------------------------------
# Stub app.core.database
# ---------------------------------------------------------------------------
from sqlalchemy.orm import declarative_base as _decl_base  # noqa: E402

_db_mod = types.ModuleType("app.core.database")
_db_mod.Base = _decl_base()
_db_mod.SessionLocal = MagicMock()
_db_mod.get_db = MagicMock()
sys.modules.setdefault("app.core.database", _db_mod)

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
from app.modules.guard.policy_engine import (  # noqa: E402
    PERSONAS,
    _build_rules,
    _resolve_canonical_workspace,
    canonical_workspace_id,
    compute_policy,
    invalidate_policy_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db():
    """Return a fresh MagicMock that behaves like a SQLAlchemy Session."""
    return MagicMock()


def _ws_uuid():
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# canonical_workspace_id
# ---------------------------------------------------------------------------

def test_canonical_workspace_id_valid_uuid():
    """Valid UUID string round-trips through _resolve_canonical_workspace."""
    ws_id = str(_ws_uuid())
    db = _mock_db()
    # Workspace lookup returns None → falls back to the original id
    db.query.return_value.filter.return_value.first.return_value = None

    with patch("app.modules.guard.policy_engine._SessionLocal", return_value=db):
        result = canonical_workspace_id(ws_id)

    assert result == ws_id


def test_canonical_workspace_id_invalid_uuid():
    """Non-UUID string is returned as-is without raising."""
    db = _mock_db()
    with patch("app.modules.guard.policy_engine._SessionLocal", return_value=db):
        result = canonical_workspace_id("not-a-uuid")
    assert result == "not-a-uuid"


def test_resolve_canonical_workspace_no_workspace():
    """When workspace row is missing, input is returned unchanged."""
    ws_id = str(_ws_uuid())
    db = _mock_db()
    db.query.return_value.filter.return_value.first.return_value = None

    result = _resolve_canonical_workspace(db, ws_id)
    assert result == ws_id


def test_resolve_canonical_workspace_owner_canonical():
    """Returns the oldest workspace under the same owner."""
    ws_id = str(_ws_uuid())
    canonical_id = str(_ws_uuid())

    ws_row = MagicMock()
    ws_row.owner_id = uuid.uuid4()

    canonical_row = MagicMock()
    canonical_row.id = uuid.UUID(canonical_id)

    db = _mock_db()
    # First call: fetch workspace by id
    db.query.return_value.filter.return_value.first.side_effect = [
        ws_row,       # the workspace itself
        canonical_row,  # the oldest workspace for that owner
    ]
    # order_by chain must still return something that has .first()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        canonical_row
    )

    result = _resolve_canonical_workspace(db, ws_id)
    assert result == canonical_id


def test_resolve_canonical_workspace_invalid_uuid_falls_back():
    """A non-UUID string triggers the except branch and is returned as-is."""
    db = _mock_db()
    result = _resolve_canonical_workspace(db, "bad-uuid!")
    assert result == "bad-uuid!"


# ---------------------------------------------------------------------------
# compute_policy
# ---------------------------------------------------------------------------

def test_compute_policy_returns_cached_payload():
    """Cache hit → _build_rules is never called; cached payload returned."""
    ws_uuid = _ws_uuid()
    cached = MagicMock()
    cached.payload = [{"id": "rule_1", "action": "block"}]

    db = _mock_db()
    db.get.return_value = cached  # GuardPolicyCache hit

    result = compute_policy(db, ws_uuid, "agent")
    assert result == [{"id": "rule_1", "action": "block"}]
    # _write_cache path not taken — db.add should NOT be called
    db.add.assert_not_called()


def test_compute_policy_builds_on_cache_miss():
    """Cache miss → _build_rules is invoked and result is written + returned."""
    ws_uuid = _ws_uuid()

    db = _mock_db()
    db.get.return_value = None  # cache miss

    # Patch _write_cache to avoid SQLAlchemy mapper resolution for unrelated models
    with patch("app.modules.guard.policy_engine._write_cache"), \
         patch("app.modules.guard.policy_engine._build_rules", return_value=[{"id": "r1"}]):
        result = compute_policy(db, ws_uuid, "agent")

    assert result == [{"id": "r1"}]


def test_compute_policy_empty_rules():
    """No packs, no custom rules → empty list returned and cache written."""
    ws_uuid = _ws_uuid()
    db = _mock_db()
    db.get.return_value = None

    with patch("app.modules.guard.policy_engine._write_cache"), \
         patch("app.modules.guard.policy_engine._build_rules", return_value=[]):
        result = compute_policy(db, ws_uuid, "proxy")

    assert result == []


# ---------------------------------------------------------------------------
# _build_rules
# ---------------------------------------------------------------------------

def test_build_rules_filters_by_persona():
    """Rules whose persona_affinity excludes the requested persona are dropped."""
    ws_uuid = _ws_uuid()
    db = _mock_db()

    pack = MagicMock()
    pack.rules = [
        {"id": "r_agent_only", "action": "block", "persona_affinity": ["agent"]},
        {"id": "r_proxy_only", "action": "warn", "persona_affinity": ["proxy"]},
    ]

    ws_pack = MagicMock()
    ws_pack.pack_slug = "base"
    ws_pack.pinned_version = None

    # WorkspaceSkillPack.all() → [ws_pack]
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ws_pack
    ]
    # WorkspaceCustomRule.all() → []
    # GuardRuleOverride.all() → []
    db.query.return_value.filter.return_value.all.return_value = []

    with patch("app.modules.guard.policy_engine._get_pack", return_value=pack):
        rules = _build_rules(db, ws_uuid, "agent")

    ids = [r["id"] for r in rules]
    assert "r_agent_only" in ids
    assert "r_proxy_only" not in ids


def test_build_rules_override_disables_rule():
    """A GuardRuleOverride with disabled=True removes the rule from the result."""
    ws_uuid = _ws_uuid()
    db = _mock_db()

    pack = MagicMock()
    pack.rules = [{"id": "r_danger", "action": "block", "persona_affinity": PERSONAS}]

    ws_pack = MagicMock()
    ws_pack.pack_slug = "base"
    ws_pack.pinned_version = None

    override = MagicMock()
    override.rule_id = "r_danger"
    override.disabled = True
    override.action = None
    override.custom_message = None

    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ws_pack
    ]
    db.query.return_value.filter.return_value.all.side_effect = [
        [],          # WorkspaceCustomRule
        [override],  # GuardRuleOverride
    ]

    with patch("app.modules.guard.policy_engine._get_pack", return_value=pack):
        rules = _build_rules(db, ws_uuid, "agent")

    assert not any(r["id"] == "r_danger" for r in rules)


def test_build_rules_override_changes_action():
    """An override with disabled=False + action='warn' changes the rule action."""
    ws_uuid = _ws_uuid()
    db = _mock_db()

    pack = MagicMock()
    pack.rules = [{"id": "r_strict", "action": "block", "persona_affinity": PERSONAS}]

    ws_pack = MagicMock()
    ws_pack.pack_slug = "base"
    ws_pack.pinned_version = None

    override = MagicMock()
    override.rule_id = "r_strict"
    override.disabled = False
    override.action = "warn"
    override.custom_message = None

    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        ws_pack
    ]
    db.query.return_value.filter.return_value.all.side_effect = [
        [],          # WorkspaceCustomRule
        [override],  # GuardRuleOverride
    ]

    with patch("app.modules.guard.policy_engine._get_pack", return_value=pack):
        rules = _build_rules(db, ws_uuid, "agent")

    assert rules[0]["action"] == "warn"


# ---------------------------------------------------------------------------
# invalidate_policy_cache
# ---------------------------------------------------------------------------

def test_invalidate_policy_cache_deletes_rows():
    """invalidate_policy_cache issues a DELETE for the workspace and calls expire_all."""
    ws_uuid = _ws_uuid()
    db = _mock_db()
    db.query.return_value.filter.return_value.delete.return_value = 2

    with patch("app.modules.guard.policy_engine.publish_policy_invalidated", create=True):
        invalidate_policy_cache(db, ws_uuid)

    db.query.assert_called()
    db.expire_all.assert_called_once()


def test_invalidate_policy_cache_redis_failure_is_swallowed():
    """Redis unavailability during publish_policy_invalidated must not raise."""
    ws_uuid = _ws_uuid()
    db = _mock_db()
    db.query.return_value.filter.return_value.delete.return_value = 0

    # Simulate publish raising — must be silently caught
    with patch(
        "app.modules.guard.policy_engine.publish_policy_invalidated",
        side_effect=RuntimeError("redis down"),
        create=True,
    ):
        invalidate_policy_cache(db, ws_uuid)  # must not raise

    db.expire_all.assert_called_once()
