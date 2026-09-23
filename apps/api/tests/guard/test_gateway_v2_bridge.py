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
    build_vendor_credential_resolver,
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


def test_build_credential_resolver_pre_resolves_http_passthrough_targets():
    """PR 5 — passthrough targets are executable now (OpenRouter is the
    reference integration). Their credentials must be pre-resolved just
    like native + litellm targets, so the coordinator's resolver stays a
    pure callable and the request-scoped DB session isn't held open
    across the network call.

    The ``provider`` argument passed to the Vault lookup falls back to
    the target's ``integration`` for passthrough targets (they don't
    carry a ``provider`` field).
    """
    profile = GatewayProfileV2.model_validate({
        "name": "prod",
        "model_alias": "coding",
        "accepts": ["openai_chat_completions"],
        "targets": [
            {
                "id": "sdk-target", "transport": "litellm_sdk",
                "provider": "openai", "model": "gpt-4o",
                "credential_ref": f"vault://{ENV}/openai",
            },
            {
                "id": "passthrough", "transport": "http_passthrough",
                "integration": "openrouter",
                "model": "anthropic/claude-sonnet",
                "credential_ref": f"vault://{ENV}/openrouter",
            },
        ],
    })
    calls: list[tuple[str, str]] = []
    with patch(
        "app.runtime.gateway_v2_bridge.resolve_gateway_key",
        side_effect=lambda db, ws, ref, provider, env: (
            calls.append((ref, provider)) or "key"
        ),
    ):
        build_credential_resolver(
            db=object(), workspace_id="ws", environment_id=ENV,
            provider="openai", profile=profile,
        )
    refs = [c[0] for c in calls]
    assert refs == [f"vault://{ENV}/openai", f"vault://{ENV}/openrouter"]
    # Passthrough target's provider hint falls back to its integration.
    provider_for_passthrough = next(
        p for ref, p in calls if ref.endswith("/openrouter")
    )
    assert provider_for_passthrough == "openrouter"


# ─── build_vendor_credential_resolver (PR 5) ──────────────────────────


def test_vendor_resolver_none_when_no_helicone_targets():
    """Non-Helicone-only profiles get None so the coordinator hot path
    stays clear of extra indirection."""
    profile = GatewayProfileV2.model_validate({
        "name": "prod", "model_alias": "coding",
        "accepts": ["openai_chat_completions"],
        "targets": [{
            "id": "or", "transport": "http_passthrough",
            "integration": "openrouter", "model": "anthropic/claude-sonnet",
            "credential_ref": f"vault://{ENV}/openrouter",
        }],
    })
    assert build_vendor_credential_resolver(
        db=object(), workspace_id="ws", environment_id=ENV, profile=profile,
    ) is None


def test_vendor_resolver_pre_resolves_helicone_vendor_keys():
    """Helicone targets pre-resolve BOTH keys from the same vault
    entry. The returned callable takes the credential_ref and hands
    back the vendor key (OpenAI or Anthropic) — the coordinator threads
    it to the passthrough transport for the second auth header."""
    profile = GatewayProfileV2.model_validate({
        "name": "prod", "model_alias": "coding",
        "accepts": ["openai_chat_completions"],
        "targets": [{
            "id": "hel", "transport": "http_passthrough",
            "integration": "helicone_openai", "model": "gpt-4o",
            "credential_ref": f"vault://{ENV}/helicone",
        }],
    })
    with patch(
        "app.runtime.gateway_v2_bridge.resolve_vendor_key",
        return_value="sk-openai-live",
    ):
        vendor = build_vendor_credential_resolver(
            db=object(), workspace_id="ws", environment_id=ENV, profile=profile,
        )
    assert vendor is not None
    assert vendor(f"vault://{ENV}/helicone") == "sk-openai-live"


def test_vendor_resolver_raises_when_helicone_vault_missing_vendor_key():
    """If the Helicone vault entry doesn't hold a vendor key, raise
    the same CredentialsUnavailable shape the primary resolver uses so
    the handler returns 503 with the specific target id."""
    profile = GatewayProfileV2.model_validate({
        "name": "prod", "model_alias": "coding",
        "accepts": ["anthropic_messages"],
        "targets": [{
            "id": "hel-ant", "transport": "http_passthrough",
            "integration": "helicone_anthropic", "model": "claude-sonnet-4-6",
            "credential_ref": f"vault://{ENV}/helicone",
        }],
    })
    with patch(
        "app.runtime.gateway_v2_bridge.resolve_vendor_key",
        return_value=None,
    ):
        with pytest.raises(CredentialsUnavailable) as excinfo:
            build_vendor_credential_resolver(
                db=object(), workspace_id="ws", environment_id=ENV, profile=profile,
            )
    assert excinfo.value.target_id == "hel-ant"


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
