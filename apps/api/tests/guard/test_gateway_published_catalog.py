from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.guard.routers import gateway_proxy


def snapshot(alias="served", accepts=None):
    return {"name": "test", "model_alias": alias,
            "accepts": accepts or ["anthropic_messages"],
            "targets": [{"id": "primary", "transport": "native_http", "provider": "anthropic",
                         "model": "private-upstream-model", "credential_ref": "vault://11111111-1111-4111-8111-111111111111/private-key"}]}


def row(code, config):
    return (SimpleNamespace(id=code, cond_code=code, working_copy={"model_alias": "draft"}),
            SimpleNamespace(snapshot=config))


def database(rows):
    db = MagicMock()
    query = db.query.return_value
    query.join.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = rows
    return db, query


def test_catalog_uses_published_alias_not_working_copy_or_upstream(monkeypatch):
    monkeypatch.setattr(gateway_proxy, "settings", SimpleNamespace(gateway_profile_v2_enabled_for=lambda _: True))
    db, query = database([row("abcdefgh", snapshot()), row("ijklmnop", snapshot("other"))])
    assert gateway_proxy._anthropic_catalog(db, "workspace", 1) == [
        {"type": "model", "id": "cond-abcdefgh-served", "display_name": "served"}]
    predicates = [str(value) for value in query.filter.call_args.args]
    assert any("workspace_id" in value for value in predicates)
    assert any("schema_version" in value for value in predicates)
    join = str(query.join.call_args.args[1])
    assert "active_revision_id" in join and "profile_id" in join


def test_catalog_skips_invalid_and_incompatible_snapshots(monkeypatch):
    monkeypatch.setattr(gateway_proxy, "settings", SimpleNamespace(gateway_profile_v2_enabled_for=lambda _: True))
    db, _ = database([row("invalid", {}), row("openai", snapshot(accepts=["openai_responses"]))])
    assert gateway_proxy._anthropic_catalog(db, "workspace", 1000) == []


def test_disabled_v2_does_not_fall_back_to_v1(monkeypatch):
    monkeypatch.setattr(gateway_proxy, "settings", SimpleNamespace(gateway_profile_v2_enabled_for=lambda _: False))
    db, _ = database([])
    assert gateway_proxy._anthropic_catalog(db, "workspace", 1000) == []
    db.query.assert_not_called()
