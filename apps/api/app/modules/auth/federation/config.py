"""Workspace-owned trust configuration; application presets do not confer trust."""
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from .contracts import ContractModel, Identifier


def https_endpoint(value: str) -> str:
    try:
        url = urlsplit(value)
        if (value != value.strip() or any(ord(c) < 33 or ord(c) == 127 for c in value)
                or "\\" in value or url.scheme != "https" or not url.hostname
                or url.username is not None or url.password is not None
                or url.fragment or url.query or url.port not in (None, 443)):
            raise ValueError
    except ValueError:
        raise ValueError("expected an HTTPS endpoint without credentials, query or fragment") from None
    return value


class ClaimMapping(ContractModel):
    name: Identifier
    source_claim: Identifier


class TrustConfig(ContractModel):
    # No active state until principal/delegation enforcement is implemented.
    status: Literal["draft", "disabled"] = "draft"
    integration_type: Literal["pcai", "litellm", "generic"] = "generic"
    method: Literal["oauth_access_token"] = "oauth_access_token"
    issuer: Annotated[str, Field(min_length=1, max_length=2048)]
    audience: Identifier
    jwks_uri: Annotated[str, Field(min_length=1, max_length=2048)]
    discovery_uri: Annotated[str, Field(min_length=1, max_length=2048)] | None = None
    token_profile: Literal["at+jwt", "token_use_access"] = "at+jwt"
    algorithms: tuple[Literal["RS256"], ...] = ("RS256",)
    claim_mappings: tuple[ClaimMapping, ...] = Field(default=(), max_length=32)

    @field_validator("issuer", "jwks_uri", "discovery_uri")
    @classmethod
    def valid_endpoint(cls, value):
        return https_endpoint(value) if value is not None else None

    @field_validator("algorithms")
    @classmethod
    def supported_algorithms(cls, value):
        if value != ("RS256",):
            raise ValueError("only the RS256 profile is supported")
        return value

    @field_validator("claim_mappings")
    @classmethod
    def unique_mappings(cls, value):
        if len({m.name for m in value}) != len(value):
            raise ValueError("duplicate mapping name")
        if any(m.name in {"role", "roles", "workspace_id", "principal_id", "agent_identity_id"} for m in value):
            raise ValueError("mapping cannot set authorization identities or roles")
        return value
