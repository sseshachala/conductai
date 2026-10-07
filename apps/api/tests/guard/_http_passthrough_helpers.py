"""Shared target builders and fake upstream response for the
HTTPPassthroughTransport contract tests (``test_http_passthrough_transport*.py``).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.modules.guard.gateway_config import HTTPPassthroughTarget


ENV = "11111111-1111-1111-1111-111111111111"


def _openrouter_target(**overrides) -> HTTPPassthroughTarget:
    defaults = dict(
        id="openrouter-primary",
        transport="http_passthrough",
        integration="openrouter",
        model="anthropic/claude-sonnet",
        credential_ref=f"vault://{ENV}/openrouter",
    )
    defaults.update(overrides)
    return HTTPPassthroughTarget(**defaults)


def _portkey_target(**overrides) -> HTTPPassthroughTarget:
    defaults = dict(
        id="portkey-primary",
        transport="http_passthrough",
        integration="portkey",
        model="gpt-4o",
        credential_ref=f"vault://{ENV}/portkey",
        provider_options={"virtual_key": "vk-openai-prod"},
    )
    defaults.update(overrides)
    return HTTPPassthroughTarget(**defaults)


def _helicone_openai_target(**overrides) -> HTTPPassthroughTarget:
    defaults = dict(
        id="helicone-openai-primary",
        transport="http_passthrough",
        integration="helicone_openai",
        model="gpt-4o",
        credential_ref=f"vault://{ENV}/helicone",
    )
    defaults.update(overrides)
    return HTTPPassthroughTarget(**defaults)


def _helicone_anthropic_target(**overrides) -> HTTPPassthroughTarget:
    defaults = dict(
        id="helicone-anthropic-primary",
        transport="http_passthrough",
        integration="helicone_anthropic",
        model="claude-sonnet-4-6",
        credential_ref=f"vault://{ENV}/helicone",
    )
    defaults.update(overrides)
    return HTTPPassthroughTarget(**defaults)


def _azure_target(**overrides) -> HTTPPassthroughTarget:
    defaults = dict(
        id="azure-primary",
        transport="http_passthrough",
        integration="azure_openai",
        model="gpt-4o-prod-deploy",   # deployment name, NOT a model id
        credential_ref=f"vault://{ENV}/azure",
        endpoint="https://my-resource.openai.azure.com",
        provider_options={"api_version": "2024-06-01"},
    )
    defaults.update(overrides)
    return HTTPPassthroughTarget(**defaults)


def _custom_target(**overrides) -> HTTPPassthroughTarget:
    """PR 7 review — custom REQUIRES ``provider_options.protocol``.
    Default the fixture to OpenAI-shape unless the caller overrides."""
    defaults = dict(
        id="custom-primary",
        transport="http_passthrough",
        integration="custom",
        model="gpt-4o",
        credential_ref=f"vault://{ENV}/custom",
        endpoint="https://my-llm-proxy.example.com/v1",
        provider_options={"protocol": "openai"},
    )
    defaults.update(overrides)
    return HTTPPassthroughTarget(**defaults)


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json = json_body or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                "upstream error",
                request=MagicMock(),
                response=MagicMock(status_code=self.status_code),
            )
