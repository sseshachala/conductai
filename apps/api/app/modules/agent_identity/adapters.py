from typing import Protocol

from app.core.crypto import decrypt

TOKEN_PREFIX = "cond_agt_"


class AgentIdentityAdapter(Protocol):
    def resolve(self, config: dict) -> str: ...


class ConductAIAdapter:
    def resolve(self, config: dict) -> str:
        return decrypt(config["token_encrypted"])["token"]


_REGISTRY: dict[str, AgentIdentityAdapter] = {
    "conduct": ConductAIAdapter(),
}


def resolve_agent_token(provider: str, config: dict) -> str:
    adapter = _REGISTRY.get(provider)
    if not adapter:
        raise ValueError(f"Unknown agent identity provider: {provider!r}")
    return adapter.resolve(config)
