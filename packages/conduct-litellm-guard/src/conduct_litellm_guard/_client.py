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
        federation_connection: str | None = None,
        subject_token: str | None = None,
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
        return await self._call(
            "guard_check_prompt", arguments, session_id, federation_connection, subject_token
        )

    async def guard_check_action(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        session_id: str | None = None,
        federation_connection: str | None = None,
        subject_token: str | None = None,
    ) -> str:
        """Call the ``guard_check`` tool (action gate) for an MCP tool call.

        Same envelope as ``guard_check``. Used for LiteLLM ``pre_mcp_call``
        so action-persona rules (tool name + argument patterns, approvals)
        see the real tool, not a prompt-shaped rendering of it.
        """
        return await self._call(
            "guard_check",
            {"tool_name": tool_name, "tool_input": tool_input},
            session_id,
            federation_connection,
            subject_token,
        )

    async def _call(
        self,
        name: str,
        arguments: dict[str, Any],
        session_id: str | None,
        federation_connection: str | None,
        subject_token: str | None,
    ) -> str:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
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
        if federation_connection:
            headers["Conduct-Federation-Connection"] = federation_connection
        if subject_token:
            headers["Conduct-Subject-Token"] = subject_token

        response = await self._client.post(
            f"{self._base}/mcp",
            json=payload,
            headers=headers,
        )
        # Identity denial is never eligible for legacy transport fail-open.
        if response.status_code in (401, 403):
            raise IdentityRequiredError("Conduct identity verification denied")
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            raise GuardCheckError("Invalid Conduct response", {})
        error = body.get("error") or {}
        result = body.get("result") or {}
        if not isinstance(error, dict) or not isinstance(result, dict):
            raise GuardCheckError("Invalid Conduct response", {})
        marker = error.get("data") or result.get("structuredContent") or {}
        if isinstance(marker, dict) and marker.get("identity_required"):
            raise IdentityRequiredError("Conduct identity verification denied")
        response.raise_for_status()

        # JSON-RPC 2.0 error envelope.
        if "error" in body:
            err = body["error"]
            raise GuardCheckError(err.get("message", "guard_check error"), err)

        # tools/call returns {result: {content: [{type: "text", text: "..."}]}}.
        # Fall back to the raw payload if the shape doesn't match — we log
        # the raw string upstream so operators can debug.
        result = body.get("result") or {}
        if result.get("isError"):
            raise GuardCheckError("Conduct policy check failed", {})
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


class IdentityRequiredError(RuntimeError):
    """Non-bypassable identity failure, with no raw remote/token content."""
