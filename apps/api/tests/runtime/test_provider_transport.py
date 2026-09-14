import pytest

from app.runtime import llm_client
from app.runtime.provider_transport import (
    ProviderTransportRegistry,
    RawHTTPTransport,
)


class _PluginTransport:
    name = "plugin"

    def create_client(self, **kwargs):
        return kwargs

    async def forward(self, **kwargs):
        return kwargs


def test_registry_supports_replaceable_provider_bindings():
    registry = ProviderTransportRegistry()
    plugin = _PluginTransport()
    registry.register(plugin, providers=("example",))

    assert registry.for_provider(" EXAMPLE ") is plugin


def test_client_for_uses_shared_transport_registry(monkeypatch):
    plugin = _PluginTransport()
    monkeypatch.setattr(
        "app.runtime.provider_transport.get_provider_transport_registry",
        lambda: type("Registry", (), {"for_provider": lambda self, provider: plugin})(),
    )

    client = llm_client.client_for("openai", "secret", base_url="https://provider.test")

    assert client == {
        "provider": "openai",
        "api_key": "secret",
        "pricing_snapshot": None,
        "base_url": "https://provider.test",
    }


def test_client_for_preserves_unknown_provider_error():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        llm_client.client_for("missing", "secret")


@pytest.mark.anyio
async def test_raw_http_transport_preserves_forward_arguments():
    calls = []

    async def sender(**kwargs):
        calls.append(kwargs)
        return "response"

    transport = RawHTTPTransport()
    result = await transport.forward(sender=sender, body={"model": "test"}, is_stream=True)

    assert result == "response"
    assert calls == [{"body": {"model": "test"}, "is_stream": True}]
