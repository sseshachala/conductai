"""Thin async client for Conduct Guard's ``guard_check_prompt`` MCP tool.

Isolated from the guardrail class so the transport can be swapped for a
mock in tests. Speaks JSON-RPC 2.0 over HTTP against the new ``/mcp``
endpoint (the legacy ``/guard/mcp`` deprecation is #1230).

Why ``guard_check_prompt`` and not ``guard_check``? Per Guard architecture
§8, MCP is an *action*-gate PEP. LiteLLM sits at the LLM egress boundary —
a *prompt*-gate concern. Calling ``guard_check`` (action gate) makes
every proxy-persona rule (credential-leak patterns, prompt-injection
canaries, PII filters) silently miss. ``guard_check_prompt`` runs the
same evaluator against proxy-persona rules and returns the same envelope.
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx

DEFAULT_TIMEOUT_S = 8.0


class GuardCheckClient:
    """One instance per ``ConductGuard`` guardrail. Reuses the same
    ``httpx.AsyncClient`` across calls so the connection pool stays warm."""

    def __init__(
        self,
        *,
        api_url: str,
        agent_token: str,
        workspace_id: str | None = None,
        surface: str = "litellm",
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
        Callers parse the prefix to decide what to do.

        Method name kept as ``guard_check`` for source-compat with existing
        guardrail callers; the wire-level tool is ``guard_check_prompt``.
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
            "User-Agent": "conduct-litellm-guard/0.2.4",
            # Server reads this to populate the DEVELOPER/TOOL column
            # in the audit dashboard. Defaults to 'litellm' so audit
            # rows land under a clear surface name instead of 'unknown'.
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
        # Fall back to the raw payload if the shape doesn't match — we log
        # the raw string upstream so operators can debug.
        result = body.get("result") or {}
        for item in result.get("content", []) or []:
            if item.get("type") == "text":
                return item.get("text", "")
        return ""


class GuardCheckError(RuntimeError):
    """Raised when the ``guard_check`` MCP call returns a JSON-RPC error
    envelope. Distinct from network errors so the guardrail can decide
    whether fail_closed applies (network) vs. this is a policy-eval error
    (which we treat as fail_closed by default too)."""

    def __init__(self, message: str, envelope: dict[str, Any]) -> None:
        super().__init__(message)
        self.envelope = envelope
