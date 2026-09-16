"""Resolver contract tests for #2001.

Covers two independent invariants:

- **v1 selector bug fix** — the historical resolver picked by
  name/env preference BEFORE checking provider compatibility, so an
  alphabetically-earlier incompatible row prevented a compatible one
  from resolving. The fix filters by provider first.
- **v2 resolver** — reads only ``gateway_profile_bindings`` by exact
  ``(workspace_id, environment_id, model_alias)``. No alphabetical
  fallback, no cross-environment lookup, no closest-alias match.
  Returns the pinned revision id so callers can lock it through every
  attempt of the same request.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from app.modules.guard.gateway_runtime import (
    ResolvedV2,
    TransportResolver,
    resolve_v2,
)


# ─── v1 selector bug fix ──────────────────────────────────────────────


def _v1_row(name: str, provider: str, environment_id=None, upstream: str | None = None):
    """Shape one persisted v1 profile row for the resolver's query.

    ``environment_id`` is stored as UUID in the DB but the v1 Pydantic
    config expects ``str | None`` — mirror the ORM's serialization by
    stringifying at test-fixture time (matches production behavior).
    """
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        environment_id=str(environment_id) if environment_id else None,
        config={
            "provider": provider,
            "protocol": "anthropic" if provider == "anthropic" else "openai_compatible",
            "upstream_url": upstream,
        },
    )


class _V1Query:
    def __init__(self, rows):
        self._rows = rows
    def filter(self, *a, **kw): return self
    def order_by(self, *a, **kw): return self
    def all(self): return list(self._rows)


class _V1Db:
    def __init__(self, rows):
        self._rows = rows
    def query(self, model): return _V1Query(self._rows)


def test_v1_picks_compatible_row_when_alphabetically_earlier_is_incompatible():
    """Regression guard for the historical selector bug.

    Two profiles:
      alpha  (provider=openai)  — earlier alphabetically
      beta   (provider=anthropic)

    Client hits ``/gateway/v1/anthropic``. Old code selected ``alpha``
    by name-order, saw its provider mismatch, and returned None → 503.
    Fixed code filters by provider first → picks ``beta``.
    """
    db = _V1Db([
        _v1_row("alpha", "openai"),
        _v1_row("beta", "anthropic"),
    ])
    resolved = TransportResolver().resolve_profile(
        db, workspace_id="ws", provider="anthropic", environment_id=None,
    )
    assert resolved is not None
    assert resolved.name == "beta"


def test_v1_environment_match_still_preferred_among_compatible_rows():
    """Provider filter first, THEN env preference.

    Two profiles both compatible with anthropic:
      alpha (env=dev)
      beta  (env=prod)

    Client asks for env=prod. Fixed selector still prefers the env
    match — the bug fix does not regress env-preference behavior.
    """
    dev_id = uuid4()
    prod_id = uuid4()
    db = _V1Db([
        _v1_row("alpha", "anthropic", environment_id=dev_id),
        _v1_row("beta",  "anthropic", environment_id=prod_id),
    ])
    resolved = TransportResolver().resolve_profile(
        db, workspace_id="ws", provider="anthropic", environment_id=str(prod_id),
    )
    assert resolved is not None
    assert resolved.name == "beta"


def test_v1_falls_back_to_environment_null_when_no_env_match():
    dev_id = uuid4()
    db = _V1Db([
        _v1_row("alpha", "anthropic", environment_id=None),
        _v1_row("beta",  "anthropic", environment_id=dev_id),
    ])
    # Client asks for a different env than any compatible row carries.
    other_env = uuid4()
    resolved = TransportResolver().resolve_profile(
        db, workspace_id="ws", provider="anthropic", environment_id=str(other_env),
    )
    assert resolved is not None
    assert resolved.name == "alpha"  # env=NULL fallback


def test_v1_returns_none_when_no_compatible_row_exists():
    """Every row is openai; client hits anthropic. No compatible row →
    None. Behavior unchanged from the pre-fix version — no false
    positives from the bug fix."""
    db = _V1Db([
        _v1_row("alpha", "openai"),
        _v1_row("beta", "openai"),
    ])
    resolved = TransportResolver().resolve_profile(
        db, workspace_id="ws", provider="anthropic", environment_id=None,
    )
    assert resolved is None


def test_v1_litellm_row_is_compatible_with_every_provider():
    """A profile with ``provider="litellm"`` acts as a wildcard.
    Locking this so the bug fix doesn't accidentally exclude it."""
    db = _V1Db([_v1_row("beta", "litellm", upstream="https://litellm.test")])
    for surface in ("anthropic", "openai", "perplexity"):
        resolved = TransportResolver().resolve_profile(
            db, workspace_id="ws", provider=surface, environment_id=None,
        )
        assert resolved is not None, f"litellm wildcard should match {surface}"
        assert resolved.name == "beta"


def test_v1_corrupt_row_is_skipped_not_fatal():
    """A single bad row must not poison sibling profiles. Ensures a
    silently-mangled config JSONB doesn't fail traffic for other
    profiles in the same workspace."""
    db = _V1Db([
        SimpleNamespace(  # corrupt — provider missing
            id=uuid4(), name="corrupt", environment_id=None, config={"protocol": "anthropic"},
        ),
        _v1_row("beta", "anthropic"),
    ])
    resolved = TransportResolver().resolve_profile(
        db, workspace_id="ws", provider="anthropic", environment_id=None,
    )
    assert resolved is not None
    assert resolved.name == "beta"


# ─── v2 resolver ──────────────────────────────────────────────────────


ENV = UUID("11111111-1111-1111-1111-111111111111")
WS = "22222222-2222-2222-2222-222222222222"
REV = UUID("33333333-3333-3333-3333-333333333333")
COND_CODE = "abc12345"

_V2_SNAPSHOT = {
    "schema_version": 2,
    "name": "prod",
    "model_alias": "coding",
    "accepts": ["anthropic_messages"],
    "timeout_seconds": 60,
    "max_attempts": 2,
    "targets": [
        {
            "id": "primary",
            "transport": "litellm_sdk",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "credential_ref": f"vault://{ENV}/anthropic",
        },
    ],
}


def _make_v2_db(*, profile=None, revision=None):
    """Build a mock Session for the v2 resolver.

    v3 resolver calls ``db.query(Model).filter(...).one_or_none()``
    twice — once for the profile row (by cond_code), once for the
    revision (by active_revision_id). Route the fake calls per model
    class.
    """
    from app.models.gateway_profile import GatewayProfile as _Row, GatewayProfileRevision

    def _q(model):
        query = MagicMock()
        query.filter.return_value = query
        if model is _Row:
            query.one_or_none.return_value = profile
        elif model is GatewayProfileRevision:
            query.one_or_none.return_value = revision
        else:
            query.one_or_none.return_value = None
        return query

    db = MagicMock()
    db.query.side_effect = _q
    return db


def test_v2_returns_revision_and_profile_on_exact_match():
    profile = MagicMock(active_revision_id=REV)
    revision = MagicMock(id=REV, snapshot=_V2_SNAPSHOT)
    db = _make_v2_db(profile=profile, revision=revision)

    result = resolve_v2(db, workspace_id=WS, cond_code=COND_CODE)
    assert isinstance(result, ResolvedV2)
    assert result.revision_id == REV
    assert result.profile.model_alias == "coding"
    assert result.profile.targets[0].provider == "anthropic"


def test_v2_returns_none_when_no_profile_exists():
    """Unknown cond_code → None. Caller sees clear 'unknown model' 4xx."""
    db = _make_v2_db(profile=None, revision=None)
    result = resolve_v2(db, workspace_id=WS, cond_code="nope0000")
    assert result is None


def test_v2_returns_none_when_profile_has_no_active_revision():
    """A draft profile (never published) has active_revision_id=None.
    Runtime treats it as a 'no config live yet' case, same as unknown."""
    profile = MagicMock(active_revision_id=None)
    db = _make_v2_db(profile=profile, revision=None)
    result = resolve_v2(db, workspace_id=WS, cond_code=COND_CODE)
    assert result is None


def test_v2_returns_none_when_active_revision_points_at_missing_row():
    """RESTRICT should prevent this, but if it happens (data corruption),
    we fail closed. The log line is the audit trail."""
    profile = MagicMock(active_revision_id=REV)
    db = _make_v2_db(profile=profile, revision=None)
    result = resolve_v2(db, workspace_id=WS, cond_code=COND_CODE)
    assert result is None


def test_v2_returns_none_when_published_snapshot_is_invalid():
    """A published snapshot that can't parse against v2 schema is a bug
    in publish-time validation — fail closed rather than crash the
    request path."""
    profile = MagicMock(active_revision_id=REV)
    revision = MagicMock(
        id=REV,
        snapshot={"schema_version": 2, "name": "prod"},  # missing required fields
    )
    db = _make_v2_db(profile=profile, revision=revision)
    result = resolve_v2(db, workspace_id=WS, cond_code=COND_CODE)
    assert result is None


def test_v2_pins_revision_id_so_caller_can_lock_it_through_all_attempts():
    """The invariant the whole revision-id concept exists for: a
    resolved request MUST reference exactly one revision, and callers
    are expected to pin it in routing_meta so a concurrent publish
    can't flip the profile mid-request."""
    profile = MagicMock(active_revision_id=REV)
    revision = MagicMock(id=REV, snapshot=_V2_SNAPSHOT)
    db = _make_v2_db(profile=profile, revision=revision)

    result = resolve_v2(db, workspace_id=WS, cond_code=COND_CODE)
    assert result is not None
    assert result.revision_id == REV
    assert isinstance(result.revision_id, UUID)
