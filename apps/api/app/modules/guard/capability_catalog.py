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
    Operation,
    Target,
)


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
# The integration preset validates its own endpoint + auth family; here
# we lock which operations we've verified end-to-end.
_HTTP_PASSTHROUGH_CERTIFIED: dict[tuple[Integration, Operation], bool] = {
    ("openrouter",         "openai_chat_completions"): True,
    ("portkey",            "anthropic_messages"):      True,
    ("portkey",            "openai_chat_completions"): True,
    ("portkey",            "openai_responses"):        True,
    ("helicone_anthropic", "anthropic_messages"):      True,
    ("helicone_anthropic", "anthropic_count_tokens"):  True,
    ("helicone_openai",    "openai_chat_completions"): True,
    ("azure_openai",       "openai_chat_completions"): True,
    ("azure_openai",       "openai_responses"):        True,
    # ``custom`` is intentionally absent — a custom passthrough must be
    # explicitly certified per operation before it can be published.
}


CATALOG_VERSION = "2026.09.15.v2-launch"


class CapabilityMismatch(Exception):
    """Raised when a Target claims an Operation the catalog does not certify.

    The message string is the sole audit surface for publish failures.
    Keep it specific: which target id, which operation, which
    transport+provider/integration, and a link/hint to the fix.
    """


def _certified_operations_for_target(target: Target) -> set[Operation]:
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
            if isinstance(target, LiteLLMSDKTarget):
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
