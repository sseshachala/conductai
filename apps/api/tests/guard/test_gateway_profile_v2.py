"""Schema + capability-catalog contract tests for Gateway Profile v2 (#2001).

Locks the three invariants publishing depends on:

- The discriminated Target union routes correctly on ``transport``.
- ``credential_ref`` shape is enforced (``vault://<uuid>/<name>``).
- The capability catalog rejects uncertified (target, operation) tuples
  at publish time with a specific error string — no silent drops.
"""
from __future__ import annotations

import pytest

from app.modules.guard.capability_catalog import (
    CATALOG_VERSION,
    CapabilityMismatch,
    validate_targets_against_accepts,
)
from app.modules.guard.gateway_config import (
    GatewayProfileV2,
    HTTPPassthroughTarget,
    LiteLLMSDKTarget,
    NativeHTTPTarget,
    parse_credential_ref,
)


ENV = "11111111-1111-1111-1111-111111111111"
CRED_ANTHROPIC = f"vault://{ENV}/anthropic"
CRED_OPENAI    = f"vault://{ENV}/openai"
CRED_PORTKEY   = f"vault://{ENV}/portkey"
CRED_OPENROUTER = f"vault://{ENV}/openrouter"


# ─── Schema shape ─────────────────────────────────────────────────────


def test_litellm_sdk_target_is_picked_by_discriminator():
    """A target with ``transport='litellm_sdk'`` parses as LiteLLMSDKTarget
    even when the raw dict has fields the other subclass rejects."""
    profile = GatewayProfileV2.model_validate({
        "name": "prod",
        "model_alias": "coding",
        "accepts": ["anthropic_messages"],
        "targets": [
            {
                "id": "primary",
                "transport": "litellm_sdk",
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
                "credential_ref": CRED_ANTHROPIC,
                "provider_options": {"region": "us-east-1"},
            },
        ],
    })
    assert isinstance(profile.targets[0], LiteLLMSDKTarget)
    assert profile.targets[0].provider == "anthropic"


def test_http_passthrough_target_is_picked_by_discriminator():
    profile = GatewayProfileV2.model_validate({
        "name": "via-openrouter",
        "model_alias": "coding",
        "accepts": ["openai_chat_completions"],
        "targets": [
            {
                "id": "openrouter",
                "transport": "http_passthrough",
                "integration": "openrouter",
                "model": "anthropic/claude-sonnet",
                "credential_ref": CRED_OPENROUTER,
            },
        ],
    })
    assert isinstance(profile.targets[0], HTTPPassthroughTarget)
    assert profile.targets[0].integration == "openrouter"


def test_ordered_targets_expose_priority_order():
    """List order = priority. Publish + resolver both rely on this."""
    profile = GatewayProfileV2.model_validate({
        "name": "prod",
        "model_alias": "coding",
        "accepts": ["anthropic_messages"],
        "targets": [
            {"id": "primary",  "transport": "litellm_sdk", "provider": "anthropic",
             "model": "claude-sonnet-4-6", "credential_ref": CRED_ANTHROPIC},
            {"id": "fallback", "transport": "litellm_sdk", "provider": "anthropic",
             "model": "claude-haiku-4-5-20251001", "credential_ref": CRED_ANTHROPIC},
        ],
    })
    assert [t.id for t in profile.targets] == ["primary", "fallback"]


def test_duplicate_target_ids_are_rejected():
    with pytest.raises(ValueError, match=r"duplicate target id"):
        GatewayProfileV2.model_validate({
            "name": "prod",
            "model_alias": "coding",
            "accepts": ["anthropic_messages"],
            "targets": [
                {"id": "same", "transport": "litellm_sdk", "provider": "anthropic",
                 "model": "claude-sonnet-4-6", "credential_ref": CRED_ANTHROPIC},
                {"id": "same", "transport": "litellm_sdk", "provider": "anthropic",
                 "model": "claude-haiku-4-5-20251001", "credential_ref": CRED_ANTHROPIC},
            ],
        })


def test_credential_ref_shape_is_enforced():
    """Wrong shape at publish time is easier to fix than at resolve time."""
    for bad in (
        "vault:anthropic",                          # missing //
        "vault://not-a-uuid/anthropic",             # env id must be UUID
        f"vault://{ENV}/",                          # empty name
        f"vault://{ENV}/name with space",           # invalid char
    ):
        with pytest.raises(ValueError, match=r"vault://"):
            LiteLLMSDKTarget(
                id="t", transport="litellm_sdk", provider="anthropic",
                model="claude-sonnet-4-6", credential_ref=bad,
            )


def test_parse_credential_ref_returns_env_and_name():
    env, name = parse_credential_ref(CRED_ANTHROPIC)
    assert str(env) == ENV
    assert name == "anthropic"


def test_at_least_one_target_required():
    """Zero targets is a publish that can never resolve. Reject at parse."""
    with pytest.raises(ValueError):
        GatewayProfileV2.model_validate({
            "name": "prod",
            "model_alias": "coding",
            "accepts": ["anthropic_messages"],
            "targets": [],
        })


def test_at_least_one_accepts_required():
    """Empty ``accepts`` = no operations served = publish is a no-op."""
    with pytest.raises(ValueError):
        GatewayProfileV2.model_validate({
            "name": "prod",
            "model_alias": "coding",
            "accepts": [],
            "targets": [
                {"id": "t", "transport": "litellm_sdk", "provider": "anthropic",
                 "model": "claude-sonnet-4-6", "credential_ref": CRED_ANTHROPIC},
            ],
        })


def test_unknown_operation_string_rejected():
    """``accepts`` values are literal-typed. Unknown ops caught here so a
    misconfigured client never gets a runtime 500."""
    with pytest.raises(ValueError):
        GatewayProfileV2.model_validate({
            "name": "prod",
            "model_alias": "coding",
            "accepts": ["anthropic_hallucinated_operation"],
            "targets": [
                {"id": "t", "transport": "litellm_sdk", "provider": "anthropic",
                 "model": "claude-sonnet-4-6", "credential_ref": CRED_ANTHROPIC},
            ],
        })


# ─── Capability catalog ───────────────────────────────────────────────


def test_catalog_certifies_anthropic_messages_via_litellm_sdk():
    target = LiteLLMSDKTarget(
        id="t", transport="litellm_sdk", provider="anthropic",
        model="claude-sonnet-4-6", credential_ref=CRED_ANTHROPIC,
    )
    validate_targets_against_accepts(
        accepts=["anthropic_messages", "anthropic_count_tokens"],
        targets=[target],
    )


def test_catalog_certifies_anthropic_messages_via_native_http():
    """PR 2: native_http is preferred over litellm_sdk for Anthropic +
    OpenAI. Both are certified for the same launch operations; publish
    accepts either."""
    target = NativeHTTPTarget(
        id="t", transport="native_http", provider="anthropic",
        model="claude-sonnet-4-6", credential_ref=CRED_ANTHROPIC,
    )
    validate_targets_against_accepts(
        accepts=["anthropic_messages", "anthropic_count_tokens"],
        targets=[target],
    )


def test_catalog_certifies_openai_chat_via_native_http():
    target = NativeHTTPTarget(
        id="t", transport="native_http", provider="openai",
        model="gpt-4o", credential_ref=CRED_OPENAI,
    )
    validate_targets_against_accepts(
        accepts=["openai_chat_completions"], targets=[target],
    )


def test_catalog_rejects_native_http_for_uncertified_provider():
    """Perplexity has no vendor endpoint in _ENDPOINTS and no entry
    in _NATIVE_HTTP_CERTIFIED. Publish must reject."""
    target = NativeHTTPTarget(
        id="t", transport="native_http", provider="perplexity",
        model="sonar-pro", credential_ref=CRED_ANTHROPIC,
    )
    with pytest.raises(CapabilityMismatch) as excinfo:
        validate_targets_against_accepts(
            accepts=["anthropic_messages"], targets=[target],
        )
    assert "native_http" in str(excinfo.value)
    assert "perplexity" in str(excinfo.value)


def test_catalog_rejects_uncertified_provider_operation_pair():
    """OpenRouter passthrough is certified for chat completions, NOT for
    Anthropic Messages. Publishing that combination must fail loudly."""
    target = HTTPPassthroughTarget(
        id="t", transport="http_passthrough", integration="openrouter",
        model="anthropic/claude-sonnet", credential_ref=CRED_OPENROUTER,
    )
    with pytest.raises(CapabilityMismatch) as excinfo:
        validate_targets_against_accepts(
            accepts=["anthropic_messages"], targets=[target],
        )
    msg = str(excinfo.value)
    assert "openrouter" in msg
    assert "anthropic_messages" in msg
    assert CATALOG_VERSION in msg
    assert "Either remove the operation" in msg or "drop the target" in msg


def test_catalog_rejects_when_any_target_in_fallback_chain_is_incompatible():
    """Every target must serve every accepted operation. If target[1]
    can't back everything target[0] can, that's a publish-time bug —
    clients cannot know in advance which target their request lands on."""
    primary = LiteLLMSDKTarget(
        id="primary", transport="litellm_sdk", provider="anthropic",
        model="claude-sonnet-4-6", credential_ref=CRED_ANTHROPIC,
    )
    fallback = HTTPPassthroughTarget(
        id="fallback", transport="http_passthrough", integration="openrouter",
        model="anthropic/claude-sonnet", credential_ref=CRED_OPENROUTER,
    )
    with pytest.raises(CapabilityMismatch) as excinfo:
        validate_targets_against_accepts(
            accepts=["anthropic_messages", "anthropic_count_tokens"],
            targets=[primary, fallback],
        )
    # Failure names the second target — publish reports the *specific*
    # target that broke the guarantee.
    assert "fallback" in str(excinfo.value)


def test_catalog_certifies_openrouter_for_openai_chat_completions():
    """PR 5 — OpenRouter is the reference passthrough integration,
    certified for ``openai_chat_completions``. Publishing that combo
    succeeds now that the transport executor has landed."""
    target = HTTPPassthroughTarget(
        id="via-openrouter", transport="http_passthrough",
        integration="openrouter", model="anthropic/claude-sonnet",
        credential_ref=CRED_OPENROUTER,
    )
    validate_targets_against_accepts(
        accepts=["openai_chat_completions"], targets=[target],
    )


def test_catalog_still_rejects_other_passthrough_integrations():
    """Portkey / Helicone / Azure OpenAI stay uncertified until each
    ships its per-integration auth-header semantics (follow-up PRs).
    Publish rejects them all — the loud rejection is what stops an
    admin from believing a Portkey target is live before its executor
    ships."""
    for integration in ("portkey", "helicone_anthropic",
                        "helicone_openai", "azure_openai"):
        target = HTTPPassthroughTarget(
            id=f"t-{integration}", transport="http_passthrough",
            integration=integration, model="some-model",
            credential_ref=CRED_PORTKEY,
        )
        with pytest.raises(CapabilityMismatch):
            validate_targets_against_accepts(
                accepts=["openai_chat_completions"], targets=[target],
            )


def test_catalog_still_rejects_openrouter_for_uncertified_operation():
    """OpenRouter is certified for chat completions only. Publishing an
    Anthropic Messages target through OpenRouter must still fail."""
    target = HTTPPassthroughTarget(
        id="t", transport="http_passthrough", integration="openrouter",
        model="anthropic/claude-sonnet", credential_ref=CRED_OPENROUTER,
    )
    with pytest.raises(CapabilityMismatch):
        validate_targets_against_accepts(
            accepts=["anthropic_messages"], targets=[target],
        )


def test_catalog_certifies_custom_openai_protocol_for_openai_ops():
    """PR 7 review finding 6 — Custom certification is per-protocol.
    openai-shape targets certify openai_chat_completions + openai_responses
    only; publishing anthropic_messages against an openai proxy would
    silently 4xx at request time, so publish rejects at build time."""
    target = HTTPPassthroughTarget(
        id="c", transport="http_passthrough", integration="custom",
        model="gpt-4o", credential_ref=CRED_PORTKEY,
        endpoint="https://custom.example.com/v1",
        provider_options={"protocol": "openai"},
    )
    validate_targets_against_accepts(
        accepts=["openai_chat_completions", "openai_responses"],
        targets=[target],
    )
    with pytest.raises(CapabilityMismatch):
        validate_targets_against_accepts(
            accepts=["anthropic_messages"], targets=[target],
        )


def test_catalog_certifies_custom_anthropic_protocol_for_anthropic_ops():
    target = HTTPPassthroughTarget(
        id="c", transport="http_passthrough", integration="custom",
        model="claude-sonnet-4-6", credential_ref=CRED_PORTKEY,
        endpoint="https://custom.example.com/v1",
        provider_options={"protocol": "anthropic"},
    )
    validate_targets_against_accepts(
        accepts=["anthropic_messages", "anthropic_count_tokens"],
        targets=[target],
    )
    with pytest.raises(CapabilityMismatch):
        validate_targets_against_accepts(
            accepts=["openai_chat_completions"], targets=[target],
        )


def test_custom_target_requires_endpoint():
    with pytest.raises(ValueError, match=r"endpoint"):
        HTTPPassthroughTarget(
            id="c", transport="http_passthrough", integration="custom",
            model="gpt-4o", credential_ref=CRED_PORTKEY,
            provider_options={"protocol": "openai"},
        )


def test_custom_target_requires_protocol():
    with pytest.raises(ValueError, match=r"protocol"):
        HTTPPassthroughTarget(
            id="c", transport="http_passthrough", integration="custom",
            model="gpt-4o", credential_ref=CRED_PORTKEY,
            endpoint="https://custom.example.com/v1",
            # No provider_options.protocol.
        )


def test_custom_target_rejects_string_bearer_prefix():
    """PR 7 review finding 5 — ``"false"`` (string) previously
    coerced to True via ``bool(...)``. Publish now rejects with a
    specific message so the operator fixes the config, not the
    runtime coercion."""
    with pytest.raises(ValueError, match=r"boolean"):
        HTTPPassthroughTarget(
            id="c", transport="http_passthrough", integration="custom",
            model="gpt-4o", credential_ref=CRED_PORTKEY,
            endpoint="https://custom.example.com/v1",
            provider_options={"protocol": "openai", "bearer_prefix": "false"},
        )


@pytest.mark.parametrize("banned_key", [
    "Authorization", "authorization",
    "X-API-Key", "x-api-key",
    "Cookie", "content-type", "Content-Length",
    "Helicone-Auth", "x-portkey-api-key",
    "my-openai-api-key", "some-vendor-secret", "unknown-token",
])
def test_custom_extra_headers_reject_reserved_names(banned_key):
    """PR 7 review finding 2 — credential-bearing + transport-reserved
    headers can't ride into a profile via extra_headers. Case-insensitive
    reject, plus substring guards for password/secret/token/api-key."""
    with pytest.raises(ValueError, match=r"reserved"):
        HTTPPassthroughTarget(
            id="c", transport="http_passthrough", integration="custom",
            model="gpt-4o", credential_ref=CRED_PORTKEY,
            endpoint="https://custom.example.com/v1",
            provider_options={
                "protocol": "openai",
                "extra_headers": {banned_key: "value"},
            },
        )


def test_custom_extra_headers_reject_crlf_injection():
    with pytest.raises(ValueError, match=r"CR/LF|illegal"):
        HTTPPassthroughTarget(
            id="c", transport="http_passthrough", integration="custom",
            model="gpt-4o", credential_ref=CRED_PORTKEY,
            endpoint="https://custom.example.com/v1",
            provider_options={
                "protocol": "openai",
                "extra_headers": {"X-Team": "line1\r\nX-Injected: true"},
            },
        )


@pytest.mark.parametrize("bad_endpoint", [
    "http://127.0.0.1:8080/v1",
    "http://localhost/v1",
    "https://10.0.0.5/v1",
    "https://192.168.1.1/v1",
    "http://169.254.169.254/latest/meta-data",  # cloud metadata service
    "http://[::1]/v1",
])
def test_custom_endpoint_rejects_private_and_loopback(bad_endpoint):
    """PR 7 review finding 1 — mirror of PR 6's guard for the Custom
    integration. Full egress control is deployment policy; this stops
    the workspace-admin-points-at-127.0.0.1 class of attack."""
    with pytest.raises(ValueError, match=r"loopback|non-public|refused"):
        HTTPPassthroughTarget(
            id="c", transport="http_passthrough", integration="custom",
            model="gpt-4o", credential_ref=CRED_PORTKEY,
            endpoint=bad_endpoint,
            provider_options={"protocol": "openai"},
        )
