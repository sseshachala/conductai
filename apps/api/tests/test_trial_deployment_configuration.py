from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.modules.guard.trial_configuration import setup_reason


def test_saas_unchanged_without_operator_key(monkeypatch):
    monkeypatch.delenv("GUARD_TRIAL_ANTHROPIC_KEY", raising=False)
    assert setup_reason(SimpleNamespace(auth_mode="clerk")) is None


def test_onprem_requires_local_gateway_and_operator_key(monkeypatch):
    settings = SimpleNamespace(auth_mode="proxy", conduct_proxy_url="https://gateway.conductai.ai/gateway/v1")
    monkeypatch.setenv("GUARD_TRIAL_ANTHROPIC_KEY", "synthetic-not-a-key")
    assert setup_reason(settings) == "deployment_gateway_required"
    settings.conduct_proxy_url = "https://gateway.example.internal/gateway/v1"
    monkeypatch.delenv("GUARD_TRIAL_ANTHROPIC_KEY")
    assert setup_reason(settings) == "deployment_provider_required"
    monkeypatch.setenv("GUARD_TRIAL_ANTHROPIC_KEY", "synthetic-not-a-key")
    assert setup_reason(settings) is None


def test_unconfigured_demo_never_seeds_identity_or_calls_gateway():
    from app.modules.guard.routers import trial
    db = Mock()
    with patch.object(trial, "setup_reason", return_value="deployment_provider_required"):
        session = trial.get_trial_session(workspace_id="test", db=db)
        result = trial.run_demo_verb("allow", workspace_id="test", db=db)
    assert session.setup_required and session.token is None and session.gateway_url == ""
    assert result.upstream_status == 503
    db.execute.assert_not_called()
