"""HTTP client for Conduct's ``guard_check_prompt`` MCP tool.

Copied from ``conduct_litellm_guard._client`` — the only surface-specific
bits are the ``surface`` default (``"nemo"``) and the ``User-Agent``.
When a third consumer arrives we should extract this into
``packages/shared/``.

Why ``guard_check_prompt`` and not ``guard_check``? NeMo Guardrails
intercepts input rails at the LLM egress boundary — a prompt-gate
concern. Calling the action-gate ``guard_check`` verb loads only
agent-persona rules, so proxy-persona rules (credential leaks, prompt
injection, PII, dual-use framing) silently pass through. Mirrors the
LiteLLM 0.2.0 fix.
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx

DEFAULT_TIMEOUT_S = 8.0


class GuardCheckClient:
    """One instance per plugin. Reuses the same ``httpx.AsyncClient``
    across calls so the connection pool stays warm."""

    def __init__(
        self,
        *,
        api_url: str,
        agent_token: str,
        workspace_id: str | None = None,
        surface: str = "nemo",
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        # Strip trailing slash so ``/guard/mcp`` concatenation is predictable.
        self._base = api_url.rstrip("/")
        self._token = agent_token
        self._workspace_id = workspace_id
        self._surface = surface
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def guard_check(
        self,
        *,
        prompt: str,
        model: str | None = None,
        provider: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Call the ``guard_check_prompt`` tool and return the text payload.

        Returns strings that start with ``"ok"``, ``"advisory:"``,
        ``"WARNING —"``, ``"BLOCKED —"``, or ``"PENDING approval —"``.
        Callers parse the prefix via :class:`GuardDecision`.

        Method name kept as ``guard_check`` for source-compat with existing
        actions callers; the wire-level MCP tool is ``guard_check_prompt``
        (per Guard architecture §8 — NeMo is a prompt-gate PEP).
        """
        arguments: dict[str, Any] = {"prompt": prompt}
        if model is not None:
            arguments["model"] = model
        if provider is not None:
            arguments["provider"] = provider

        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": "guard_check_prompt", "arguments": arguments},
        }

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "User-Agent": "conduct-nemo-guard/0.2.0",
            # Server reads this to populate the DEVELOPER/TOOL column
            # in the audit dashboard. Defaults to 'nemo' so audit rows
            # land under a clear surface name.
            "X-Claude-Surface": self._surface,
        }
        if self._workspace_id:
            headers["X-Workspace-Id"] = self._workspace_id
        if session_id:
            headers["X-Conduct-Session-Id"] = session_id

        response = await self._client.post(
            f"{self._base}/mcp",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        body = response.json()

        # JSON-RPC 2.0 error envelope.
        if "error" in body:
            err = body["error"]
            raise GuardCheckError(err.get("message", "guard_check error"), err)

        # tools/call returns {result: {content: [{type: "text", text: "..."}]}}.
        result = body.get("result") or {}
        for item in result.get("content", []) or []:
            if item.get("type") == "text":
                return item.get("text", "")
        return ""


class GuardCheckError(RuntimeError):
    """Raised when the ``guard_check`` MCP call returns a JSON-RPC error
    envelope. Distinct from network errors so callers can decide whether
    fail_closed applies (network) vs. this is a policy-eval error (which
    we also treat as fail_closed by default)."""

    def __init__(self, message: str, envelope: dict[str, Any]) -> None:
        super().__init__(message)
        self.envelope = envelope
