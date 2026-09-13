from types import SimpleNamespace

from app.modules.guard.gateway_runtime import resolve_profile_runtime


class _Query:
    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return [SimpleNamespace(
            name="default",
            environment_id=None,
            config={"provider": "litellm", "protocol": "openai_compatible", "upstream_url": "https://litellm.test/v1"},
        )]


class _Db:
    def query(self, model):
        return _Query()


def test_runtime_resolves_litellm_profile_without_profile_secret(monkeypatch):
    monkeypatch.setattr("app.modules.guard.gateway_runtime.get_credential", lambda *args, **kwargs: {})
    upstream, key, profile = resolve_profile_runtime(_Db(), "workspace", "openai", None)
    assert upstream == "https://litellm.test/v1"
    assert key is None
    assert profile.provider == "litellm"
