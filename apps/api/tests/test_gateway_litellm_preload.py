"""GATEWAY_PRELOAD_LITELLM: import LiteLLM at boot on the gateway only."""
from unittest.mock import MagicMock

import pytest

from app.runtime import gateway_transports


@pytest.fixture
def log(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    monkeypatch.setattr(gateway_transports, "log", fake)
    return fake


def test_off_by_default(monkeypatch: pytest.MonkeyPatch, log: MagicMock) -> None:
    monkeypatch.delenv("GATEWAY_PRELOAD_LITELLM", raising=False)
    gateway_transports.preload_if_enabled()
    log.info.assert_not_called()


def test_preloads_when_enabled(monkeypatch: pytest.MonkeyPatch, log: MagicMock) -> None:
    monkeypatch.setenv("GATEWAY_PRELOAD_LITELLM", "true")
    gateway_transports.preload_if_enabled()
    log.info.assert_called_once_with("gateway.v2.litellm_preloaded")


def test_import_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch, log: MagicMock) -> None:
    import builtins

    real_import = builtins.__import__

    def broken(name, *a, **kw):  # noqa: ANN001, ANN202
        if name == "litellm":
            raise ImportError("boom")
        return real_import(name, *a, **kw)

    monkeypatch.setenv("GATEWAY_PRELOAD_LITELLM", "true")
    monkeypatch.setattr(builtins, "__import__", broken)
    gateway_transports.preload_if_enabled()
    log.warning.assert_called_once_with("gateway.v2.litellm_preload_failed", error_type="ImportError")
