"""Missing Vault credentials must not become fake provider authentication errors."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.modules.glens.routers.chat import _llm_config


@pytest.fixture
def config(monkeypatch):
    from app.core import credentials
    from app.runtime import llm_client, model_router
    monkeypatch.setattr("app.modules.glens.vault_settings.selected_environment", lambda *a: None)
    monkeypatch.setattr(model_router, "resolve_for_workspace", lambda **kw: ("anthropic", "claude-sonnet-4-6", "workspace"))
    lookup, factory = Mock(), Mock()
    monkeypatch.setattr(credentials, "get_credential", lookup)
    monkeypatch.setattr(llm_client, "client_for", factory)
    return SimpleNamespace(db=object(), workspace_id="workspace"), lookup, factory


@pytest.mark.parametrize("key", [None, "", "  ", 123])
def test_missing_key_stops_before_client_creation(config, key):
    executor, lookup, factory = config
    lookup.return_value = {"api_key": key}
    with pytest.raises(ValueError, match="Vault selected in Lens settings"):
        _llm_config(executor)
    factory.assert_not_called()


def test_lookup_failure_is_not_disguised_as_missing_key_or_leaked(config):
    executor, lookup, factory = config
    lookup.side_effect = RuntimeError("private connection details")
    with pytest.raises(ValueError, match="could not read") as exc:
        _llm_config(executor)
    assert "private" not in str(exc.value)
    factory.assert_not_called()


def test_valid_key_uses_existing_scoped_resolver(config):
    executor, lookup, factory = config
    lookup.return_value = {"api_key": "test-only"}
    client, provider, model = _llm_config(executor)
    lookup.assert_called_once_with(executor.db, executor.workspace_id, "anthropic", environment_id=None)
    factory.assert_called_once_with("anthropic", api_key="test-only")
    assert client is factory.return_value
    assert (provider, model) == ("anthropic", "claude-sonnet-4-6")


def test_selected_vault_is_forwarded_to_strict_resolver(config, monkeypatch):
    from uuid import uuid4
    env = uuid4()
    monkeypatch.setattr("app.modules.glens.vault_settings.selected_environment", lambda *a: env)
    executor, lookup, _ = config
    lookup.return_value = {"api_key": "test-only"}
    _llm_config(executor)
    lookup.assert_called_once_with(executor.db, executor.workspace_id, "anthropic", environment_id=env)
