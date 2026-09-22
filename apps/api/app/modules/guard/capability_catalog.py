"""Publish-time capability catalog for Gateway Profile v2 (#2001).

The catalog answers one question: given a Target's ``transport``,
``provider`` or ``integration``, and ``model``, which of the operations
declared in the parent profile's ``accepts`` list are certified?

Publishing a profile calls ``validate_targets_against_accepts()``; any
uncertified combination fails the publish with a specific error string,
never a silent drop.

This is a static list, not a runtime probe. Two reasons:

1. **Deterministic publish** — an admin publishes at ``T``, deploys
   clients at ``T+1s``, and knows what will and won't work. A runtime
   probe would give inconsistent answers depending on upstream health.
2. **One version bump per LiteLLM release** — the catalog is generated
   from LiteLLM's shipped provider matrix + our own tested overrides,
   pinned to the LiteLLM version we integrate. Certifying a new
   provider is a one-line addition here, not a runtime change.

The rows below are the intentionally-narrow v2 launch set. Expanding
requires (a) a test proving the operation works end-to-end through the
listed transport, and (b) a doc entry.
"""
from __future__ import annotations

from typing import Iterable

from app.modules.guard.gateway_config import (
    HTTPPassthroughTarget,
    Integration,
    LiteLLMSDKTarget,
    NativeHTTPTarget,
    Operation,
    Target,
)


# Native HTTP certified matrix — vendor's own protocol, no translation.
# Preferred for Anthropic + OpenAI. Same set as LiteLLM's launch matrix,
# but the transports are different: native_http proxies the request body
# to the vendor with only the credential swapped in.
_NATIVE_HTTP_CERTIFIED: dict[tuple[str, Operation], list[str] | None] = {
    ("anthropic", "anthropic_messages"): None,
    ("anthropic", "anthropic_count_tokens"): None,
    ("openai", "openai_chat_completions"): None,
    ("openai", "openai_responses"): None,
}


# LiteLLM SDK certified matrix — one entry per (provider, operation).
# Model wildcard ``*`` means "any model the provider supports"; a
# concrete list narrows to specific model IDs. Absent tuples are
# uncertified and will fail publish.
_LITELLM_SDK_CERTIFIED: dict[tuple[str, Operation], list[str] | None] = {
    ("anthropic", "anthropic_messages"): None,          # any Anthropic model
    ("anthropic", "anthropic_count_tokens"): None,
    ("openai", "openai_chat_completions"): None,        # any OpenAI chat model
    ("openai", "openai_responses"): None,               # /v1/responses supported
}


# HTTP passthrough certified matrix — one entry per (integration, operation).
#
# PR 5 lands the executor (see ``runtime/http_passthrough_transport.py``)
# with OpenRouter as the first supported integration. Extending this
# matrix requires (a) a matching entry in
# ``_INTEGRATION_ENDPOINTS`` in the transport module, and (b) a test
# proving the (integration, operation) tuple works end-to-end. The
# publish check + the coordinator's ``_dispatch`` both key off this
# table, so they can't drift out of alignment.
#
# Portkey / Helicone / Azure OpenAI / Custom are staged for follow-up
# PRs — they need per-integration auth-header semantics that the
# OpenRouter reference implementation deliberately punts on.
_HTTP_PASSTHROUGH_CERTIFIED: dict[tuple[Integration, Operation], bool] = {
    ("openrouter", "openai_chat_completions"): True,
    # PR 4 — Portkey certified for OpenAI-compat chat completions.
    # Auth = raw ``x-portkey-api-key`` (see ``_INTEGRATION_ENDPOINTS``);
    # virtual-key config on the Portkey side selects the upstream.
    ("portkey", "openai_chat_completions"): True,
}


CATALOG_VERSION = "2026.09.22.v2-portkey-passthrough"


class CapabilityMismatch(Exception):
    """Raised when a Target claims an Operation the catalog does not certify.

    The message string is the sole audit surface for publish failures.
    Keep it specific: which target id, which operation, which
    transport+provider/integration, and a link/hint to the fix.
    """


def _certified_operations_for_target(target: Target) -> set[Operation]:
    if isinstance(target, NativeHTTPTarget):
        return {
            op
            for (prov, op) in _NATIVE_HTTP_CERTIFIED
            if prov == target.provider
        }
    if isinstance(target, LiteLLMSDKTarget):
        return {
            op
            for (prov, op) in _LITELLM_SDK_CERTIFIED
            if prov == target.provider
        }
    if isinstance(target, HTTPPassthroughTarget):
        return {
            op
            for (integration, op), certified in _HTTP_PASSTHROUGH_CERTIFIED.items()
            if certified and integration == target.integration
        }
    return set()


def validate_targets_against_accepts(
    *,
    accepts: Iterable[Operation],
    targets: Iterable[Target],
) -> None:
    """Fail publish if any target can't serve every operation in ``accepts``.

    Every listed target must be able to serve every advertised operation.
    An ordered fallback list where target[1] cannot serve one of the
    operations target[0] serves is a publish-time bug — clients cannot
    tell in advance which target their request will land on.
    """
    accepts_set = set(accepts)
    for target in targets:
        certified = _certified_operations_for_target(target)
        missing = accepts_set - certified
        if missing:
            if isinstance(target, NativeHTTPTarget):
                where = f"transport=native_http, provider={target.provider}"
            elif isinstance(target, LiteLLMSDKTarget):
                where = f"transport=litellm_sdk, provider={target.provider}"
            elif isinstance(target, HTTPPassthroughTarget):
                where = f"transport=http_passthrough, integration={target.integration}"
            else:  # unreachable — narrow the union
                where = "transport=unknown"
            raise CapabilityMismatch(
                f"target {target.id!r} cannot serve "
                f"{sorted(missing)!r} on ({where}) — capability catalog "
                f"version {CATALOG_VERSION}. "
                f"Either remove the operation from ``accepts`` or drop the "
                f"target from ``targets``."
            )


__all__ = [
    "CATALOG_VERSION",
    "CapabilityMismatch",
    "validate_targets_against_accepts",
]
