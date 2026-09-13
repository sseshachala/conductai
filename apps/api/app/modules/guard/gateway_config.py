"""Canonical gateway configuration contract.

This module is deliberately independent of SQLAlchemy and provider clients.
It is the stable boundary shared by the API, importers, the route planner, and
the local CLI proxy. Legacy proxy settings can be projected into this model
without exposing credential values.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class GatewayProfile(BaseModel):
    """Versioned, secret-free configuration for one workspace gateway."""

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
