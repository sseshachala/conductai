from types import SimpleNamespace

from app.modules.guard.gateway_runtime import TransportResolver, resolve_profile_runtime
from app.runtime.provider_transport import ProviderTransportRegistry, RawHTTPTransport


class _Query:
    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return [SimpleNamespace(
            name="default",
            environment_id=None,
            config={
                "provider": "litellm",
                "protocol": "openai_compatible",
                "upstream_url": "https://litellm.test/v1",
            },
        )]


class _Db:
    def query(self, model):
        return _Query()


def test_runtime_resolves_litellm_profile_without_profile_secret(monkeypatch):
    monkeypatch.setattr(
        "app.modules.guard.gateway_credentials.get_vault_credential",
        lambda *args, **kwargs: {},
    )
    upstream, key, profile = resolve_profile_runtime(_Db(), "workspace", "openai", None)
    assert upstream == "https://litellm.test/v1"
    assert key is None
    assert profile.provider == "litellm"


def test_transport_resolver_returns_profile_vault_and_registered_transport(monkeypatch):
    monkeypatch.setattr(
        "app.modules.guard.gateway_credentials.get_vault_credential",
        lambda *args, **kwargs: {},
    )

    runtime = TransportResolver().resolve(_Db(), "workspace", "openai", None)

    assert runtime is not None
    assert runtime.upstream_url == "https://litellm.test/v1"
    assert runtime.api_key is None
    assert runtime.profile.provider == "litellm"
    assert isinstance(runtime.transport, RawHTTPTransport)


class _PluginTransport:
    name = "plugin"

    def create_client(self, **kwargs):
        return kwargs

    async def forward(self, **kwargs):
        return kwargs


def test_profile_runtime_builds_client_through_selected_transport(monkeypatch):
    registry = ProviderTransportRegistry()
    registry.register(_PluginTransport(), providers=("litellm",))
    monkeypatch.setattr(
        "app.modules.guard.gateway_runtime.resolve_gateway_key",
        lambda *args: "vault-key",
    )

    runtime = TransportResolver(registry).resolve(_Db(), "workspace", "openai", None)

    assert runtime is not None
    assert runtime.create_client(provider="openai") == {
        "provider": "openai",
        "api_key": "vault-key",
        "pricing_snapshot": None,
        "base_url": "https://litellm.test/v1",
    }
