from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.guard import mcp_impls as impl


def context(configured=True):
    ws = uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = (
        SimpleNamespace(advisory_mode=False, arg_anomaly_enabled=False) if configured else None
    )
    return impl.GuardCtx(db, ws, str(ws), 'cond_agt_fixture', 'local-user', None,
                         'test', 'session', agent_identity_id=str(uuid4()))


@pytest.mark.parametrize('prompt', [False, True])
def test_missing_setup_blocks_before_policy_lookup_and_records_identity(monkeypatch, prompt):
    ctx = context(False)
    rules = MagicMock()
    record = MagicMock()
    monkeypatch.setattr(impl, '_get_rules', rules)
    monkeypatch.setattr(impl, '_record_event', record)
    result = (impl.guard_check_prompt_impl(ctx, prompt='hello') if prompt
              else impl.guard_check_impl(ctx, tool_name='read', tool_input={}))
    assert result.startswith('BLOCKED')
    rules.assert_not_called()
    assert record.call_args.args[4:6] == ('blocked', 'guard_not_configured')
    assert record.call_args.kwargs['agent_identity_id'] == ctx.agent_identity_id


def test_status_reports_missing_setup_without_caching_empty_policy(monkeypatch):
    import json
    ctx = context(False)
    ctx.db.execute.return_value.fetchone.return_value = None
    ctx.db.get.return_value = None
    rules = MagicMock()
    monkeypatch.setattr(impl, '_get_rules', rules)
    result = json.loads(impl.guard_status_impl(ctx))
    assert result['configured'] is False
    assert result['rules_active'] == 0
    rules.assert_not_called()


def test_activity_uses_authenticated_identity(monkeypatch):
    ctx = context()
    record = MagicMock()
    monkeypatch.setattr(impl, '_record_event', record)
    impl.guard_activity_impl(ctx, summary='synthetic test', agent_identity_id='spoofed')
    assert record.call_args.kwargs['agent_identity_id'] == ctx.agent_identity_id


@pytest.mark.parametrize('action,decision', [(None, 'allowed'), ('audit', 'audited'), ('block', 'blocked')])
def test_configured_checks_keep_authenticated_identity(monkeypatch, action, decision):
    ctx = context()
    monkeypatch.setattr(impl, '_get_rules', lambda *a, **k: [])
    monkeypatch.setattr(impl, '_match_policy', lambda *a, **k: (
        {'action': action, 'rule_id': 'fixture', 'message': 'fixture'} if action else None
    ))
    record = MagicMock()
    monkeypatch.setattr(impl, '_record_event', record)
    impl.guard_check_impl(ctx, tool_name='read', tool_input={}, agent_identity_id='spoofed')
    assert record.call_args.args[4] == decision
    assert record.call_args.kwargs['agent_identity_id'] == ctx.agent_identity_id


def test_resolved_identity_is_workspace_scoped(monkeypatch):
    ws = str(uuid4())
    row = SimpleNamespace(id=str(uuid4()), workspace_id=ws, risk_tier='tier_2')
    monkeypatch.setattr('app.core.auth.resolve_agent_identity_row', lambda *a: row)
    fields = impl.authenticated_agent_fields(None, 'cond_agt_fixture', ws)
    assert fields == {'agent_identity_id': row.id, 'agent_risk_tier': 'tier_2'}
    with pytest.raises(HTTPException):
        impl.authenticated_agent_fields(None, 'cond_agt_fixture', str(uuid4()))


def test_unresolved_agent_fails_but_member_token_has_no_fabricated_identity(monkeypatch):
    monkeypatch.setattr('app.core.auth.resolve_agent_identity_row', lambda *a: None)
    with pytest.raises(HTTPException):
        impl.authenticated_agent_fields(None, 'cond_agt_fixture', str(uuid4()))
    assert impl.authenticated_agent_fields(None, 'guard-mt-fixture', str(uuid4())) == {}


def test_writer_persists_identity(monkeypatch):
    from app.modules.guard.routers import mcp
    db = MagicMock()
    identity = str(uuid4())
    monkeypatch.setattr(mcp, 'chain_hash_for_insert', lambda *a: ('prev', 'entry'))
    monkeypatch.setattr(mcp, 'get_policy_hash', lambda *a: 'policy')
    mcp._record_event(db, uuid4(), 'read', {}, 'allowed', None, 'test', None, 'session',
                      agent_identity_id=identity)
    assert db.add.call_args.args[0].agent_identity_id == identity
    db.commit.assert_called_once()
