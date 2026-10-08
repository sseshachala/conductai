"""Guard gateway — caller-facing exceptions and the tolerant JSON loader.

Re-exported from ``app.guard.gateway`` so existing imports keep working."""

from __future__ import annotations


def _safe_loads(raw: bytes) -> dict:
    import json as _json
    try:
        return _json.loads(raw or b"{}")
    except Exception:
        return {}


class LensUpstreamError(Exception):
    """Upstream provider (OpenAI/Anthropic/etc) returned a non-2xx.

    Semantically distinct from GuardedLLMBlocked — this is a provider
    error, not a policy denial. Callers should surface it as such and
    NOT prefix it with 'Guard blocked'.
    """

    def __init__(self, *, status: int, detail: str, payload: dict | None = None) -> None:
        self.status = status
        self.detail = detail
        self.payload = payload or {}
        super().__init__(f"upstream HTTP {status}: {detail}")


class GuardedLLMBlocked(Exception):
    """Raised by `guarded_llm_call` when policy or router refuses the call."""

    def __init__(self, *, status: int, detail: str, payload: dict) -> None:
        super().__init__(f"Guard blocked ({status}): {detail}")
        self.status = status
        self.detail = detail
        self.payload = payload
