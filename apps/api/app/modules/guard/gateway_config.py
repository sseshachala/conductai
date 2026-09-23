"""Canonical gateway configuration contract.

This module is deliberately independent of SQLAlchemy and provider clients.
It is the stable boundary shared by the API, importers, the route planner, and
the local CLI proxy. Legacy proxy settings can be projected into this model
without exposing credential values.

Two schemas live here side by side:

- ``GatewayProfile`` (schema_version=1) — the historical shape. Kept intact
  so existing callers do not have to change during the #2001 rollout. The
  legacy resolver in ``gateway_runtime.TransportResolver`` reads this shape.
- ``GatewayProfileV2`` (schema_version=2) — the simplified shape from the
  #2001 design. One ordered ``targets`` list, one client-facing
  ``model_alias``, no ``deployments``/``routing.fallback_aliases`` split,
  no profile-level credential overload. The new resolver + immutable
  publishing tables read this shape.

New code should import ``GatewayProfileV2`` explicitly. Nothing is
auto-migrated — a workspace stays on v1 until an admin publishes a v2
profile behind the ``guard_gateway_profile_v2`` flag.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any, Literal, Union
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _reject_private_endpoint(url: str) -> None:
    """Reject endpoints that resolve to loopback / private / link-local
    address literals.

    PR 6 review finding 1 — the transport HTTPX-forwards ``target.endpoint``
    verbatim for integrations with ``allows_endpoint_override=True``
    (currently ``azure_openai`` + ``custom``). Without this guard a
    workspace admin can point at any service reachable from the hosted
    gateway (127.0.0.1, RFC 1918, 169.254.169.254 for cloud metadata,
    ::1, etc.). Full network-level egress protection is deployment
    policy; this schema-level guard blocks the obvious literal-IP
    cases so a hostile profile can't ship without an admin explicitly
    disabling the check.

    Does NOT resolve hostnames — DNS rebinding is out of scope for
    schema validation. Deployment-level egress firewalls remain the
    authoritative boundary; this is defense in depth.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"endpoint URL malformed: {exc}") from exc
    host = (parsed.hostname or "").strip()
    if not host:
        raise ValueError("endpoint URL has no hostname")
    # Literal IP checks (v4 + v6).
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        # Not an IP literal — hostname. Block the obvious loopback
        # aliases anyway; DNS-based blocking is deployment policy.
        if host.lower() in {"localhost", "localhost.localdomain", "ip6-localhost"}:
            raise ValueError(
                f"endpoint hostname {host!r} is a loopback alias — refused. "
                f"Point at a public hostname or use a hosted deployment "
                f"policy to opt-in to internal endpoints."
            )
        return
    if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_reserved or addr.is_multicast:
        raise ValueError(
            f"endpoint {url!r} resolves to a non-public address "
            f"({addr}). Refused. Public endpoints only; internal "
            f"destinations require a deployment-level egress policy."
        )


# ─── Schema v1 (legacy — retained for the current resolver path) ────────


class Deployment(BaseModel):
    """One provider deployment behind a stable model alias."""

    model_config = ConfigDict(extra="forbid")

    alias: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=256)
    weight: float = Field(default=1, gt=0, le=100)
    provider_options: dict[str, Any] = Field(default_factory=dict)


class RoutingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["ordered", "weighted", "latency", "cost"] = "ordered"
    fallback_aliases: list[str] = Field(default_factory=list, max_length=16)


class ReliabilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: float = Field(default=60, gt=0, le=600)
    max_retries: int = Field(default=0, ge=0, le=5)


class RateLimitPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests_per_minute: int | None = Field(default=None, gt=0)
    tokens_per_minute: int | None = Field(default=None, gt=0)


class StreamingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    no_retry_after_first_byte: bool = True


class LiteLLMOptions(BaseModel):
    """Provider-agnostic LiteLLM knobs kept separate from credentials."""

    model_config = ConfigDict(extra="forbid")

    api_base: str | None = Field(default=None, max_length=2048)
    api_version: str | None = Field(default=None, max_length=128)
    custom_llm_provider: str | None = Field(default=None, max_length=64)
    drop_params: bool = False
    request_timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    num_retries: int = Field(default=0, ge=0, le=5)
    stream_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("api_base")
    @classmethod
    def validate_api_base(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("https://", "http://")):
            raise ValueError("api_base must use http:// or https://")
        return value.rstrip("/") if value else value


class GatewayProfile(BaseModel):
    """Versioned, secret-free configuration for one workspace gateway (v1)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    protocol: Literal["anthropic", "openai", "openai_compatible"]
    upstream_url: str | None = Field(default=None, max_length=2048)
    credential_ref: str | None = Field(default=None, max_length=512)
    environment_id: str | None = None
    deployments: list[Deployment] = Field(default_factory=list, max_length=100)
    routing: RoutingPolicy = Field(default_factory=RoutingPolicy)
    reliability: ReliabilityPolicy = Field(default_factory=ReliabilityPolicy)
    limits: RateLimitPolicy = Field(default_factory=RateLimitPolicy)
    streaming: StreamingPolicy = Field(default_factory=StreamingPolicy)
    litellm: LiteLLMOptions = Field(default_factory=LiteLLMOptions)
    provider_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return str(value).strip().lower()

    @field_validator("upstream_url")
    @classmethod
    def validate_upstream_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("https://", "http://")):
            raise ValueError("upstream_url must use http:// or https://")
        return value.rstrip("/") if value else value


def profile_from_legacy(
    *,
    proxy_config: dict[str, Any] | None = None,
    llm_primitives: dict[str, Any] | None = None,
    environment_id: str | None = None,
) -> GatewayProfile:
    """Project current proxy and model-primitives records into one profile.

    ``proxy_config`` may include a key-presence flag, but callers must not pass
    raw secrets into this function. Credential values are intentionally never
    copied into the resulting profile.
    """
    proxy = proxy_config or {}
    primitives = llm_primitives or {}
    provider = str(primitives.get("preferred_provider") or "anthropic").strip().lower()
    protocol = "anthropic" if provider == "anthropic" else "openai_compatible"
    tier_map = primitives.get("tier_map") or {}
    provider_tiers = tier_map.get(provider) or {}
    deployments = [
        Deployment(alias=tier, model=model)
        for tier, model in provider_tiers.items()
        if isinstance(tier, str) and isinstance(model, str) and model.strip()
    ]
    return GatewayProfile(
        name="default",
        provider=provider,
        protocol=protocol,
        upstream_url=proxy.get("LLM_UPSTREAM") or None,
        credential_ref=proxy.get("credential_ref"),
        environment_id=environment_id,
        deployments=deployments,
    )


# ─── Schema v2 (#2001 — simplified, one profile / one alias / targets) ──


#: Operations a v2 profile may declare it accepts. Catalog reads
#: (``anthropic_models``, ``openai_models``) are intentionally NOT here —
#: those are always available on the Gateway and are not gated by a
#: profile. Extending this list requires a matching capability-catalog
#: entry, otherwise publish will reject.
Operation = Literal[
    "anthropic_messages",
    "anthropic_count_tokens",
    "openai_chat_completions",
    "openai_responses",
]


#: Presets for the ``http_passthrough`` transport. Each maps to a
#: validated endpoint + auth family in the runtime; ``custom`` requires
#: an explicit ``endpoint`` and is subject to capability-catalog review.
Integration = Literal[
    "openrouter",
    "portkey",
    "helicone_anthropic",
    "helicone_openai",
    "azure_openai",
    "custom",
]


_CREDENTIAL_REF_RE = re.compile(
    r"^vault://(?P<env>[0-9a-f-]{36})/(?P<name>[A-Za-z0-9_\-\.]{1,128})$"
)


def _validate_credential_ref(value: str) -> str:
    """Enforce the ``vault://<environment-id>/<name>`` shape used by v2.

    Kept separate from the field validators so both target subclasses share
    identical error messages and so unit tests can exercise it directly.
    """
    if not _CREDENTIAL_REF_RE.match(value):
        raise ValueError(
            "credential_ref must look like 'vault://<environment-uuid>/<name>'"
        )
    return value


class LiteLLMSDKTarget(BaseModel):
    """A target executed through the embedded LiteLLM SDK.

    LiteLLM performs the protocol translation; Conduct owns the retry ladder
    (``num_retries=0`` inside LiteLLM by design) and pins the credential to
    this single attempt only.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    transport: Literal["litellm_sdk"]
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=256)
    credential_ref: str = Field(min_length=1, max_length=512)
    provider_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return str(value).strip().lower()

    @field_validator("credential_ref")
    @classmethod
    def validate_credential(cls, value: str) -> str:
        return _validate_credential_ref(value)


class NativeHTTPTarget(BaseModel):
    """A target forwarded via native HTTP directly to the vendor.

    The client's request is proxied to the vendor's endpoint with only the
    credential swapped in — no SDK translation. Preserves the vendor's own
    contract end-to-end. Preferred for Anthropic + OpenAI where the vendor's
    protocol is authoritative and translation risks are unacceptable.

    Same shape as ``LiteLLMSDKTarget`` (id / transport / provider / model /
    credential_ref / provider_options) so the coordinator can accept either
    without a discriminator on any field other than ``transport``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    transport: Literal["native_http"]
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=256)
    credential_ref: str = Field(min_length=1, max_length=512)
    provider_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return str(value).strip().lower()

    @field_validator("credential_ref")
    @classmethod
    def validate_credential(cls, value: str) -> str:
        return _validate_credential_ref(value)


class HTTPPassthroughTarget(BaseModel):
    """A target forwarded verbatim to an external gateway.

    The ``integration`` picks a validated endpoint + auth preset; ``endpoint``
    is only required when ``integration='custom'`` and is otherwise treated
    as an override where the preset permits it. Publish-time capability
    check must confirm the integration supports every operation the
    parent profile advertises in ``accepts``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    transport: Literal["http_passthrough"]
    integration: Integration
    model: str = Field(min_length=1, max_length=256)
    credential_ref: str = Field(min_length=1, max_length=512)
    endpoint: str | None = Field(default=None, max_length=2048)
    # Opaque per-integration tuning bag. Symmetric with the field on
    # the native + LiteLLM target subclasses; persisted as JSON inside
    # the profile row so no Alembic migration is required.
    # - PR 4: Portkey reads ``virtual_key`` / ``provider`` / ``config``
    #   to drive the ``x-portkey-*`` routing headers.
    # - PR 6: Azure OpenAI uses ``api_version`` (added as a URL query
    #   parameter by the transport via
    #   ``IntegrationConfig.query_params_from_options``).
    provider_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith(("https://", "http://")):
            raise ValueError("endpoint must use http:// or https://")
        _reject_private_endpoint(value)
        return value.rstrip("/")

    @field_validator("credential_ref")
    @classmethod
    def validate_credential(cls, value: str) -> str:
        return _validate_credential_ref(value)

    @model_validator(mode="after")
    def _validate_per_integration_requirements(self):
        """PR 6 review — integrations with ``allows_endpoint_override``
        actually REQUIRE an endpoint (Azure OpenAI: per-tenant Resource
        URL). Azure additionally requires ``provider_options.api_version``.
        Both were previously optional; missing them was accepted at
        publish and would only surface as a 4xx at request time."""
        if self.integration == "azure_openai":
            if not self.endpoint:
                raise ValueError(
                    "azure_openai target requires an ``endpoint`` — set "
                    "the per-tenant Azure OpenAI Resource URL "
                    "(e.g. https://my-resource.openai.azure.com)."
                )
            api_version = (self.provider_options or {}).get("api_version")
            if not isinstance(api_version, str) or not api_version.strip():
                raise ValueError(
                    "azure_openai target requires "
                    "``provider_options.api_version`` (e.g. \"2024-06-01\") "
                    "— the Azure REST API does not honour requests without one."
                )
        return self


# Discriminated union — target shape depends on ``transport``. Pydantic
# picks the right subclass from the literal without an explicit tag field.
Target = Union[NativeHTTPTarget, LiteLLMSDKTarget, HTTPPassthroughTarget]


class GatewayProfileV2(BaseModel):
    """One workspace profile, one client-facing alias, ordered targets.

    Publishing model lives outside this class — the ``profiles`` table stores
    the mutable ``working_copy``; ``profile_revisions`` stores immutable
    snapshots; ``profile_bindings`` selects which snapshot serves live traffic
    for a given (workspace, environment, model_alias).

    Everything Guard owns (agent permissions, spend, allowed destinations),
    everything the Gateway runtime owns (retry classification, backoff), and
    everything LiteLLM owns (translation) is deliberately absent here.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    name: str = Field(min_length=1, max_length=128)
    model_alias: str = Field(min_length=1, max_length=128)
    accepts: list[Operation] = Field(min_length=1, max_length=8)
    timeout_seconds: int = Field(default=60, gt=0, le=600)
    max_attempts: int = Field(default=1, ge=1, le=5)
    targets: list[Target] = Field(min_length=1, max_length=8)

    @field_validator("model_alias", mode="before")
    @classmethod
    def normalize_alias(cls, value: str) -> str:
        return str(value).strip()

    @field_validator("targets")
    @classmethod
    def unique_target_ids(cls, value: list[Target]) -> list[Target]:
        seen: set[str] = set()
        for target in value:
            if target.id in seen:
                raise ValueError(f"duplicate target id: {target.id!r}")
            seen.add(target.id)
        return value


def parse_credential_ref(value: str) -> tuple[UUID, str]:
    """Return the (environment_id, name) tuple from a v2 credential_ref.

    Callers that resolve the credential need both parts; keeping the parse
    here means the regex + shape live in one place across UI + resolver +
    the CLI gateway.
    """
    match = _CREDENTIAL_REF_RE.match(value)
    if not match:
        raise ValueError(
            "credential_ref must look like 'vault://<environment-uuid>/<name>'"
        )
    return UUID(match.group("env")), match.group("name")


__all__ = [
    # v1
    "Deployment",
    "GatewayProfile",
    "LiteLLMOptions",
    "RateLimitPolicy",
    "ReliabilityPolicy",
    "RoutingPolicy",
    "StreamingPolicy",
    "profile_from_legacy",
    # v2
    "GatewayProfileV2",
    "HTTPPassthroughTarget",
    "Integration",
    "LiteLLMSDKTarget",
    "Operation",
    "Target",
    "parse_credential_ref",
]
