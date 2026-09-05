"""HTTP client for Conduct's ``guard_check`` MCP tool.

Copied verbatim from ``conduct_litellm_guard._client`` — the only
surface-specific bit is the ``surface`` default and the ``User-Agent``.
When a third consumer arrives we should extract this into
``packages/shared/``.
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
        tool_name: str,
        tool_input: dict[str, Any],
        session_id: str | None = None,
        prompt: str | None = None,
    ) -> str:
        """Call the ``guard_check`` tool and return the text payload.

        Returns strings that start with ``"ok"``, ``"advisory:"``,
        ``"WARNING —"``, ``"BLOCKED —"``, or ``"PENDING approval —"``.
        Callers parse the prefix via :class:`GuardDecision`.
        """
        arguments: dict[str, Any] = {
            "tool_name": tool_name,
            "tool_input": tool_input,
        }
        if prompt is not None:
            arguments["prompt"] = prompt

        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": "guard_check", "arguments": arguments},
        }

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "User-Agent": "conduct-nemo-guard/0.1.0",
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
            f"{self._base}/guard/mcp",
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
