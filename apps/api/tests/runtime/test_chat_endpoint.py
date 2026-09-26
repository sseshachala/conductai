"""Exercise actual adapter requests without provider keys or live inference."""
import json
from contextlib import contextmanager

import httpx
import pytest

from app.runtime.llm_client import OpenAIClient
from app.runtime.adapters.together import TogetherClient


@pytest.mark.parametrize("provider", ["together", "perplexity"])
def test_compatible_provider_does_not_inherit_openai_model_defaults(provider):
    from app.routers.workspace_llm_primitives import tier_map_defaults_for
    from app.runtime.model_router import resolve
    defaults = tier_map_defaults_for(provider)
    selected_provider, model, _ = resolve(provider, {provider: defaults}, "balanced")
    assert selected_provider == provider
    assert not model.startswith("gpt-")


@pytest.mark.parametrize("adapter,base,expected", [
    (OpenAIClient, None, "https://api.openai.com/v1/chat/completions"),
    (TogetherClient, None, "https://api.together.ai/v1/chat/completions"),
    (OpenAIClient, "https://example.test", "https://example.test/v1/chat/completions"),
    (OpenAIClient, "https://example.test/v1/", "https://example.test/v1/chat/completions"),
    (TogetherClient, "https://example.test/gateway/openai/v1", "https://example.test/gateway/openai/v1/chat/completions"),
])
@pytest.mark.parametrize("streaming", [False, True])
def test_endpoint_has_one_version_and_preserves_override(monkeypatch, adapter, base, expected, streaming):
    sent = []
    def post(url, **kwargs):
        sent.append(url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}})
    @contextmanager
    def stream(method, url, **kwargs):
        sent.append(url)
        yield httpx.Response(200, text='data: ' + json.dumps({"choices": [{"delta": {"content": "ok"}}]}) + '\n\ndata: [DONE]\n\n')
    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "stream", stream)
    client = adapter("test-only", base_url=base)
    args = dict(model="test-model", messages=[], system="")
    if streaming:
        assert list(client.stream(**args)) == ["ok"]
    else:
        assert client.create(**args).content[0].text == "ok"
    assert sent == [expected]


@pytest.mark.parametrize("streaming", [False, True])
def test_html_errors_name_real_provider_without_dumping_markup(monkeypatch, streaming):
    response = httpx.Response(404, text='<!DOCTYPE html><html>private upstream page</html>')
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: response)
    @contextmanager
    def stream(*args, **kwargs):
        yield response
    monkeypatch.setattr(httpx, "stream", stream)
    client = TogetherClient("test-only")
    with pytest.raises(Exception, match="Together 404: The model endpoint") as exc:
        if streaming:
            list(client.stream(model="test", messages=[], system=""))
        else:
            client.create(model="test", messages=[], system="")
    assert "private" not in str(exc.value)
    assert "<html" not in str(exc.value)
