"""Proves ``_migrate_proxy_env_if_stale`` rewrites ~/.conduct/env from
the old api.conductai.ai/gateway/v1 default to gateway.conductai.ai
without touching user-customised URLs or tokens.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_conduct_dir(tmp_path, monkeypatch):
    """Redirect CONDUCT_DIR and PROXY_ENV_FILE to a tmp path so the
    test does not touch the user's real ~/.conduct."""
    from conduct_cli import guard
    conduct_dir = tmp_path / ".conduct"
    conduct_dir.mkdir()
    monkeypatch.setattr(guard, "CONDUCT_DIR", conduct_dir)
    monkeypatch.setattr(guard, "PROXY_ENV_FILE", conduct_dir / "env")
    monkeypatch.setattr(guard, "PROXY_OVERRIDE", conduct_dir / "env-override")
    yield conduct_dir


def test_migrates_old_default(_isolate_conduct_dir):
    from conduct_cli import guard
    (_isolate_conduct_dir / "env").write_text(
        '# managed\n'
        'export ANTHROPIC_BASE_URL="https://api.conductai.ai/gateway/v1/anthropic"\n'
        'export ANTHROPIC_API_KEY="cond_agt_xxx"\n'
        'export OPENAI_BASE_URL="https://api.conductai.ai/gateway/v1/openai/v1"\n'
        'export PERPLEXITY_BASE_URL="https://api.conductai.ai/gateway/v1/perplexity"\n'
    )
    assert guard._migrate_proxy_env_if_stale() is True

    text = (_isolate_conduct_dir / "env").read_text()
    assert "gateway.conductai.ai/gateway/v1/anthropic" in text
    assert "gateway.conductai.ai/gateway/v1/openai/v1" in text
    assert "gateway.conductai.ai/gateway/v1/perplexity" in text
    assert "api.conductai.ai/gateway/v1" not in text
    # Token untouched.
    assert 'ANTHROPIC_API_KEY="cond_agt_xxx"' in text


def test_leaves_custom_url_alone(_isolate_conduct_dir):
    """Self-hosted / staging deployments must not be silently rewritten."""
    from conduct_cli import guard
    original = (
        'export ANTHROPIC_BASE_URL="https://guard.internal.corp/gateway/v1/anthropic"\n'
        'export ANTHROPIC_API_KEY="cond_agt_xxx"\n'
    )
    (_isolate_conduct_dir / "env").write_text(original)

    assert guard._migrate_proxy_env_if_stale() is False
    assert (_isolate_conduct_dir / "env").read_text() == original


def test_idempotent_no_op_on_already_migrated(_isolate_conduct_dir):
    from conduct_cli import guard
    already = (
        'export ANTHROPIC_BASE_URL="https://gateway.conductai.ai/gateway/v1/anthropic"\n'
    )
    (_isolate_conduct_dir / "env").write_text(already)
    assert guard._migrate_proxy_env_if_stale() is False
    assert (_isolate_conduct_dir / "env").read_text() == already


def test_absent_file_is_no_op(_isolate_conduct_dir):
    from conduct_cli import guard
    # Fresh dir — no env file at all. Migration is a no-op, not an error.
    assert guard._migrate_proxy_env_if_stale() is False


def test_migrates_windows_ps1_too(_isolate_conduct_dir):
    from conduct_cli import guard
    (_isolate_conduct_dir / "env.ps1").write_text(
        '$Env:ANTHROPIC_BASE_URL = "https://api.conductai.ai/gateway/v1/anthropic"\n'
    )
    assert guard._migrate_proxy_env_if_stale() is True
    text = (_isolate_conduct_dir / "env.ps1").read_text()
    assert "gateway.conductai.ai/gateway/v1/anthropic" in text
    assert "api.conductai.ai/gateway/v1" not in text


def test_partial_migration_preserves_untouched_lines(_isolate_conduct_dir):
    """A file with a mix of old-default + user comments/tokens gets only
    the URL lines rewritten; comments and tokens survive intact."""
    from conduct_cli import guard
    (_isolate_conduct_dir / "env").write_text(
        '# managed by conduct — do not edit; use env-override for custom vars\n'
        'export ANTHROPIC_BASE_URL="https://api.conductai.ai/gateway/v1/anthropic"\n'
        'export ANTHROPIC_API_KEY="cond_agt_secret_do_not_touch"\n'
        '# custom user comment\n'
    )
    guard._migrate_proxy_env_if_stale()
    text = (_isolate_conduct_dir / "env").read_text()
    assert "# managed by conduct" in text
    assert "# custom user comment" in text
    assert 'ANTHROPIC_API_KEY="cond_agt_secret_do_not_touch"' in text
    assert "gateway.conductai.ai" in text
