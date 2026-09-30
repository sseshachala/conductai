import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("env_check", Path(__file__).with_name("env_check.py"))
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def configuration():
    return {"AUTH_MODE": "proxy", "DATABASE_URL": "postgresql://local/test", "REDIS_URL": "redis://local",
            "ENCRYPTION_KEY": "synthetic-" * 5, "CONSOLE_PROXY_SECRET": "synthetic-" * 5,
            "CONSOLE_OIDC_ISSUER": "https://idp.internal/realms/test", "CONSOLE_OIDC_CLIENT_ID": "console",
            "CONSOLE_OIDC_JWKS_URL": "https://idp.internal/certs", "API_BASE_URL": "https://api.internal",
            "APP_URL": "https://console.internal", "CONDUCT_PROXY_URL": "https://gateway.internal/gateway/v1",
            "ALLOWED_ORIGINS": "https://console.internal", "CONDUCT_WEB_URL": "https://console.internal",
            "CONDUCT_OAUTH_ISSUER": "https://api.internal"}


def test_complete_api_configuration_and_missing_trial_key_warning():
    errors, warnings = check.inspect(configuration(), "api")
    assert not errors
    assert any("GUARD_TRIAL_ANTHROPIC_KEY" in warning for warning in warnings)


def test_reject_saas_and_clerk_without_printing_values():
    cfg = {**configuration(), "CONDUCT_PROXY_URL": "https://gateway.conductai.ai/gateway/v1",
           "CLERK_SECRET_KEY": "sensitive-synthetic-value"}
    errors, _ = check.inspect(cfg, "api")
    assert any("SaaS" in error for error in errors)
    assert any("CLERK_SECRET_KEY" in error for error in errors)
    assert "sensitive-synthetic-value" not in str(errors)


def test_workers_do_not_need_proxy_handoff_secret_or_idp_client():
    cfg = configuration()
    for name in ("CONSOLE_PROXY_SECRET", "CONSOLE_OIDC_CLIENT_ID", "CONSOLE_OIDC_JWKS_URL", "CONSOLE_OIDC_ISSUER"):
        del cfg[name]
    assert not check.inspect(cfg, "worker")[0]
