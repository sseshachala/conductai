"""Framework-neutral tool-call check against Conduct's ``guard_check`` action gate.

Every adapter in this package translates its SDK's pre-tool hook into one
``ToolGuard.check(tool_name, tool_input)`` call. Adapters translate; Conduct
decides. No policy logic lives here.
"""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Literal

from conduct_litellm_guard import GuardDecision
from conduct_litellm_guard._client import GuardCheckClient, IdentityRequiredError
from conduct_litellm_guard.guardrail import _tool_input

log = logging.getLogger(__name__)

FailMode = Literal["fail_open", "fail_closed"]
_BLOCKING = frozenset({"block", "approval"})


@dataclass(frozen=True)
class ToolVerdict:
    """What an adapter needs: block or not, and a reason the model can read."""

    blocked: bool
    reason: str
    decision: GuardDecision


class ToolGuard:
    """Holds Conduct config and checks one tool call at a time.

    Config falls back to ``CONDUCT_API_URL`` / ``CONDUCT_AGENT_TOKEN`` /
    ``CONDUCT_WORKSPACE_ID``. ``surface`` labels the audit row so the
    dashboard shows which agent builder made the call.
    """

    def __init__(
        self,
        *,
        surface: str,
        api_url: str | None = None,
        agent_token: str | None = None,
        workspace_id: str | None = None,
        unreachable_fallback: FailMode = "fail_closed",
        timeout: float = 8.0,
    ) -> None:
        token = agent_token or os.environ.get("CONDUCT_AGENT_TOKEN")
        if not token:
            raise ValueError("ToolGuard: set CONDUCT_AGENT_TOKEN or pass agent_token.")
        self._kwargs = {
            "api_url": api_url or os.environ.get("CONDUCT_API_URL", "https://gateway.conductai.ai"),
            "agent_token": token,
            "workspace_id": workspace_id or os.environ.get("CONDUCT_WORKSPACE_ID"),
            "surface": surface,
            "timeout": timeout,
        }
        self._fallback = unreachable_fallback

    async def check(
        self, tool_name: str, tool_input: Any, session_id: str | None = None
    ) -> ToolVerdict:
        # ponytail: one HTTP client per call, so the guard is safe across event
        # loops (sync SDKs run each check in its own loop). Pool it per loop if
        # TLS setup ever shows up in latency.
        client = GuardCheckClient(**self._kwargs)
        try:
            raw = await client.guard_check_action(
                tool_name=tool_name, tool_input=_tool_input(tool_input), session_id=session_id
            )
            decision = GuardDecision.parse(raw)
        except IdentityRequiredError:
            decision = GuardDecision(verdict="block", raw="identity_required",
                                     message="Conduct identity verification required or denied.")
        except Exception as e:  # noqa: BLE001 — transport + policy-eval errors share the fallback
            log.warning("conduct_agent_guard: %s — applying %s", type(e).__name__, self._fallback)
            if self._fallback == "fail_open":
                decision = GuardDecision(verdict="allow", raw="fail_open")
            else:
                decision = GuardDecision(verdict="block", raw="unreachable",
                                         message="Conduct Guard is unreachable (fail_closed).")
        finally:
            await client.aclose()
        blocked = decision.verdict in _BLOCKING
        reason = decision.message or decision.raw or ("Blocked by Conduct Guard" if blocked else "")
        if decision.verdict == "approval":
            reason = f"Requires human approval in Conduct: {reason}"
        return ToolVerdict(blocked=blocked, reason=reason, decision=decision)

    def check_sync(
        self, tool_name: str, tool_input: Any, session_id: str | None = None
    ) -> ToolVerdict:
        """For SDKs with synchronous hooks (CrewAI, LangChain ``invoke``)."""
        coro = self.check(tool_name, tool_input, session_id)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        # Called from inside a running loop (notebooks, async hosts): run in a thread.
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(asyncio.run, coro).result()

