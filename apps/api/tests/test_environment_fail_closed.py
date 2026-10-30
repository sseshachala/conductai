"""ENVIRONMENT handling fails closed: security gates treat anything that
isn't explicitly local/development as production, and hosted platforms can't
silently run with the development default."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import Settings

API_DIR = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("env,local", [
    ("local", True), ("development", True), ("Development ", True),
    ("production", False), ("prod", False), ("staging", False), ("", False),
])
def test_is_local_environment(env, local):
    assert Settings(environment=env).is_local_environment is local


def _boot_env(**extra: str) -> str:
    """Import app.core.config in a fresh interpreter; return the effective environment."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("RENDER", "KUBERNETES_SERVICE_HOST", "ENVIRONMENT",
                        "CONDUCT_ALLOW_LOCAL_ENV_ON_PLATFORM")}
    env.update(extra)
    out = subprocess.run(
        [sys.executable, "-c", "from app.core.config import settings; print(settings.environment)"],
        cwd=API_DIR, env=env, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip().splitlines()[-1]


def test_off_platform_keeps_development_default():
    assert _boot_env() == "development"


@pytest.mark.parametrize("marker", ["RENDER", "KUBERNETES_SERVICE_HOST"])
def test_hosted_platform_coerces_development_to_production(marker):
    # ENCRYPTION_KEY must be non-default once treated as production.
    assert _boot_env(**{marker: "true", "ENCRYPTION_KEY": "x" * 32}) == "production"


def test_hosted_platform_escape_hatch():
    assert _boot_env(RENDER="true", CONDUCT_ALLOW_LOCAL_ENV_ON_PLATFORM="1") == "development"


def test_explicit_production_untouched():
    assert _boot_env(RENDER="true", ENVIRONMENT="production", ENCRYPTION_KEY="x" * 32) == "production"


def test_local_sandbox_blocked_for_non_local_environment(monkeypatch):
    from app.core.config import settings
    from app.runtime import sandbox_session

    monkeypatch.setattr(settings, "environment", "prod")  # misspelled value
    with pytest.raises(RuntimeError, match="disabled in production"):
        sandbox_session.LocalSession()
