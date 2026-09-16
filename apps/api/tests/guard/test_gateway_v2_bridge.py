"""Bridge tests for #2004 Phase 1.

Locks the three invariants the ``gateway_handler`` v2 hook-in relies on:

- Operation mapping only matches the launch matrix — anything else
  returns None so the handler falls through to v1.
- Credential pre-resolution reads every LiteLLM SDK target once, keys
  by ``credential_ref`` so a fallback attempt in the coordinator hits
  the map without a DB call.
- A missing credential raises ``CredentialsUnavailable`` with the
  offending target id — never a silent empty api_key downstream.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.modules.guard.gateway_config import GatewayProfileV2
from app.runtime.gateway_v2_bridge import (
    CredentialsUnavailable,
    build_credential_resolver,
    coerce_response_body,
    map_operation,
)


ENV = "11111111-1111-1111-1111-111111111111"


def _profile(*, provider: str = "anthropic", model: str = "claude-sonnet-4-6", targets=None):
    return GatewayProfileV2.model_validate({
        "name": "prod",
        "model_alias": "coding",
        "accepts": ["anthropic_messages"],
        "targets": targets or [
            {
                "id": "primary",
                "transport": "litellm_sdk",
                "provider": provider,
                "model": model,
                "credential_ref": f"vault://{ENV}/{provider}",
            },
        ],
    })


# ─── map_operation ────────────────────────────────────────────────────


@pytest.mark.parametrize("provider,path,expected", [
    ("anthropic", "/v1/messages",              "anthropic_messages"),
    ("anthropic", "/v1/messages/count_tokens", "anthropic_count_tokens"),
    ("openai",    "/v1/chat/completions",      "openai_chat_completions"),
    ("openai",    "/v1/responses",             "openai_responses"),
    ("openai",    "/chat/completions",         "openai_chat_completions"),
])
def test_map_operation_covers_launch_matrix(provider, path, expected):
    assert map_operation(provider, path) == expected


@pytest.mark.parametrize("provider,path", [
    ("perplexity", "/v1/chat/completions"),   # unlisted provider
    ("anthropic",  "/v1/messages/batches"),   # unlisted path
    ("openai",     "/v1/embeddings"),         # not in launch set
])
def test_map_operation_returns_none_for_uncertified_routes(provider, path):
    """None = handler falls through to v1. A hard-fail here would
    surprise workspaces that haven't published a v2 profile."""
    assert map_operation(provider, path) is None


# ─── build_credential_resolver ────────────────────────────────────────


def test_build_credential_resolver_pre_resolves_every_litellm_target():
    """Multiple targets → one Vault lookup per credential_ref. The
    resolver returned is a pure dict-lookup closure, so the coordinator
    can retry to a fallback target without touching the DB."""
    profile = _profile(targets=[
        {
            "id": "primary", "transport": "litellm_sdk",
            "provider": "anthropic", "model": "claude-sonnet-4-6",
            "credential_ref": f"vault://{ENV}/anthropic",
        },
        {
            "id": "fallback", "transport": "litellm_sdk",
            "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
            "credential_ref": f"vault://{ENV}/anthropic_backup",
        },
    ])
    calls: list[str] = []

    def fake_resolve(db, ws, ref, provider, env_id):
        calls.append(ref)
        return f"key-for-{ref}"

    with patch("app.runtime.gateway_v2_bridge.resolve_gateway_key", side_effect=fake_resolve):
        resolver = build_credential_resolver(
            db=object(), workspace_id="ws", environment_id=ENV,
            provider="anthropic", profile=profile,
        )

    assert calls == [
        f"vault://{ENV}/anthropic",
        f"vault://{ENV}/anthropic_backup",
    ]
    # Resolver is a pure closure — no DB needed after build.
    assert resolver(f"vault://{ENV}/anthropic") == f"key-for-vault://{ENV}/anthropic"
    assert resolver(f"vault://{ENV}/anthropic_backup") == f"key-for-vault://{ENV}/anthropic_backup"


def test_build_credential_resolver_raises_for_missing_credential():
    """A target with an unresolvable ref → CredentialsUnavailable with
    the offending target id. Handler maps this to a 503 so ops sees
    the target-id in the response detail and can fix Vault in one click."""
    profile = _profile()
    with patch("app.runtime.gateway_v2_bridge.resolve_gateway_key", return_value=None):
        with pytest.raises(CredentialsUnavailable) as excinfo:
            build_credential_resolver(
                db=object(), workspace_id="ws", environment_id=ENV,
                provider="anthropic", profile=profile,
            )
    assert excinfo.value.target_id == "primary"
    assert excinfo.value.credential_ref == f"vault://{ENV}/anthropic"


def test_build_credential_resolver_skips_http_passthrough_targets():
    """Passthrough targets aren't executable in the launch set. Don't
    burn a Vault lookup on one — the coordinator will raise
    UnsupportedTransport before it needs a key anyway."""
    profile = GatewayProfileV2.model_validate({
        "name": "prod",
        "model_alias": "coding",
        "accepts": ["anthropic_messages"],
        "targets": [
            {
                "id": "sdk-target", "transport": "litellm_sdk",
                "provider": "anthropic", "model": "claude-sonnet-4-6",
                "credential_ref": f"vault://{ENV}/anthropic",
            },
            {
                "id": "passthrough", "transport": "http_passthrough",
                "integration": "portkey", "model": "some-model",
                "credential_ref": f"vault://{ENV}/portkey",
            },
        ],
    })
    calls: list[str] = []
    with patch(
        "app.runtime.gateway_v2_bridge.resolve_gateway_key",
        side_effect=lambda db, ws, ref, provider, env: (calls.append(ref) or "key"),
    ):
        build_credential_resolver(
            db=object(), workspace_id="ws", environment_id=ENV,
            provider="anthropic", profile=profile,
        )
    assert calls == [f"vault://{ENV}/anthropic"]


# ─── coerce_response_body ─────────────────────────────────────────────


def test_coerce_response_body_uses_model_dump_when_available():
    """LiteLLM's Pydantic v2 model instances expose ``model_dump()``."""
    seen = {"called": False}
    class _PydanticLike:
        def model_dump(self):
            seen["called"] = True
            return {"content": "ok"}
    assert coerce_response_body(_PydanticLike()) == {"content": "ok"}
    assert seen["called"] is True


def test_coerce_response_body_passes_dicts_through():
    """``anthropic_messages`` already returns a dict; don't wrap it."""
    payload = {"content": [{"type": "text", "text": "hello"}]}
    assert coerce_response_body(payload) is payload
