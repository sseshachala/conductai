"""
Schema smoke tests for the Phase 1 agent identity alignment (#1037).

Validates:
  - AgentIdentity model has the new identity fields
  - LIFECYCLE_STATES and RISK_TIERS constants match migration 0090
  - Column types, nullability, and defaults are set as expected
  - Migration module imports cleanly and has correct revision chain

No real DB needed. This runs against the ORM model + migration import only.
Real migration verification happens in CI against a Postgres container.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))


# ── Model shape tests ────────────────────────────────────────────────────────

def test_agent_identity_has_new_fields():
    """All identity fields added in migration 0090 must be on the model."""
    from app.modules.agent_identity.models import AgentIdentity

    expected_new = {
        "source",
        "source_id",
        "platform_of_origin",
        "owner_user_id",
        "agent_role_id",
        "lifecycle_state",
        "last_certified_at",
        "certification_cadence_days",
        "risk_tier",
        "deactivated_at",
        "metadata_json",
    }
    actual = {c.name for c in AgentIdentity.__table__.columns}
    missing = expected_new - actual
    assert not missing, f"AgentIdentity missing identity fields: {missing}"


def test_agent_identity_preserves_existing_token_fields():
    """Existing token/credential columns must not have been dropped."""
    from app.modules.agent_identity.models import AgentIdentity

    expected_existing = {
        "id", "workspace_id", "name", "provider",
        "token_prefix", "token_encrypted", "token_type", "token_name",
        "created_by_clerk_user_id", "environment_id",
        "created_at", "last_used_at", "expires_at",
        "refresh_token_hash", "refresh_token_expires_at",
    }
    actual = {c.name for c in AgentIdentity.__table__.columns}
    dropped = expected_existing - actual
    assert not dropped, f"Existing token columns were dropped: {dropped}"


def test_lifecycle_states_constant():
    from app.modules.agent_identity.models import LIFECYCLE_STATES
    assert LIFECYCLE_STATES == ("active", "pending_review", "deactivated", "expired")


def test_risk_tiers_constant():
    from app.modules.agent_identity.models import RISK_TIERS
    assert RISK_TIERS == ("tier_1", "tier_2", "tier_3")


def test_lifecycle_state_column_is_non_null_with_default():
    from app.modules.agent_identity.models import AgentIdentity
    col = AgentIdentity.__table__.columns["lifecycle_state"]
    assert not col.nullable, "lifecycle_state should be non-null"
    assert col.server_default is not None, "lifecycle_state should have a server default"


def test_risk_tier_column_is_non_null_with_default():
    from app.modules.agent_identity.models import AgentIdentity
    col = AgentIdentity.__table__.columns["risk_tier"]
    assert not col.nullable, "risk_tier should be non-null"
    assert col.server_default is not None, "risk_tier should have a server default"


def test_owner_user_id_is_indexed():
    from app.modules.agent_identity.models import AgentIdentity
    col = AgentIdentity.__table__.columns["owner_user_id"]
    assert col.index, "owner_user_id should be indexed for owner lookups"


def test_source_is_indexed():
    from app.modules.agent_identity.models import AgentIdentity
    col = AgentIdentity.__table__.columns["source"]
    assert col.index, "source should be indexed for filtering by IdP"


def test_check_constraints_present():
    from app.modules.agent_identity.models import AgentIdentity
    constraint_names = {c.name for c in AgentIdentity.__table__.constraints if c.name}
    assert "ck_agent_identities_lifecycle_state" in constraint_names
    assert "ck_agent_identities_risk_tier" in constraint_names


# ── Migration shape tests ────────────────────────────────────────────────────

def _load_migration(revision: str):
    """Load an alembic migration module by revision number."""
    versions = APPS_API / "alembic" / "versions"
    matches = list(versions.glob(f"{revision}_*.py"))
    assert matches, f"No migration file for revision {revision}"
    path = matches[0]
    spec = importlib.util.spec_from_file_location(f"migration_{revision}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0090_chains_from_0089():
    mig = _load_migration("0090")
    assert mig.revision == "0090"
    assert mig.down_revision == "0089"


def test_migration_0090_has_upgrade_and_downgrade():
    mig = _load_migration("0090")
    assert callable(mig.upgrade), "migration must define upgrade()"
    assert callable(mig.downgrade), "migration must define downgrade()"


def test_migration_0090_exports_enum_constants():
    mig = _load_migration("0090")
    assert mig.LIFECYCLE_STATES == ("active", "pending_review", "deactivated", "expired")
    assert mig.RISK_TIERS == ("tier_1", "tier_2", "tier_3")
