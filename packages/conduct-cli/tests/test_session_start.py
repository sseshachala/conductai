from datetime import datetime, timedelta, timezone

import pytest

from conduct_cli.hooks import session_start


@pytest.mark.parametrize("token", ["cond_agt_current-token", "guard-mt-legacy-token"])
def test_proxy_token_check_accepts_current_and_legacy_tokens(tmp_path, monkeypatch, capsys, token):
    env_path = tmp_path / "env"
    env_path.write_text(
        "export ANTHROPIC_BASE_URL=\"https://api.conductai.ai/gateway/v1/anthropic\"\n"
        f"export ANTHROPIC_API_KEY=\"{token}\"\n"
    )
    monkeypatch.setattr(session_start, "CONDUCT_ENV_PATH", env_path)
    monkeypatch.setattr(
        session_start,
        "load_config",
        lambda: {"token_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
    )
    monkeypatch.setattr(session_start, "post_event", lambda *args, **kwargs: pytest.fail("unexpected warning"))

    session_start._check_proxy_token()

    assert "missing or malformed" not in capsys.readouterr().out


def test_proxy_token_check_warns_for_malformed_token(tmp_path, monkeypatch, capsys):
    env_path = tmp_path / "env"
    env_path.write_text(
        "export ANTHROPIC_BASE_URL=\"https://api.conductai.ai/gateway/v1/anthropic\"\n"
        "export ANTHROPIC_API_KEY=\"not-a-conduct-token\"\n"
    )
    monkeypatch.setattr(session_start, "CONDUCT_ENV_PATH", env_path)
    monkeypatch.setattr(session_start, "load_config", lambda: {})
    monkeypatch.setattr(session_start, "post_event", lambda *args, **kwargs: None)

    session_start._check_proxy_token()

    assert "proxy token missing or malformed" in capsys.readouterr().out
