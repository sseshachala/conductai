"""LiteLLM ``CustomGuardrail`` adapter for Conduct Guard.

Wire this into your LiteLLM proxy's ``config.yaml`` and every model call
routes through Guard on the way to the upstream provider. Blocks / warns
/ audits / triggers HITL approvals — same rules as the CLI hook, same
audit chain, no extra proxy hop for the model call itself.
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal

from conduct_litellm_guard._client import GuardCheckClient, GuardCheckError

log = logging.getLogger(__name__)

# LiteLLM ships its own CustomGuardrail base class. Import lazily so the
# package installs and imports on a machine that only wants the client
# (e.g. running the unit tests without a real LiteLLM install).
try:
    from litellm.integrations.custom_guardrail import CustomGuardrail  # type: ignore
    _LITELLM_AVAILABLE = True
except Exception:  # pragma: no cover — exercised via test double
    _LITELLM_AVAILABLE = False

    class CustomGuardrail:  # type: ignore[no-redef]
        """Fallback base used only when litellm isn't installed. Lets tests
        exercise the adapter without pulling the whole LiteLLM tree in."""

        def __init__(self, **kwargs: Any) -> None:
            self.guardrail_name = kwargs.get("guardrail_name")
            self.event_hook = kwargs.get("event_hook")
            self.default_on = kwargs.get("default_on", True)


Verdict = Literal["allow", "advisory", "warning", "block", "approval", "unknown"]
FailMode = Literal["fail_open", "fail_closed"]


@dataclass(frozen=True)
class GuardDecision:
    """Structured view of what ``guard_check`` returned. The raw text is
    kept so audit / logging surfaces can quote it verbatim."""

    verdict: Verdict
    raw: str
    rule_id: str | None = None
    message: str | None = None

    @classmethod
    def parse(cls, text: str) -> "GuardDecision":
        """Map the ``guard_check`` string envelope to a verdict.

        Response contract (from apps/api/app/modules/guard/routers/mcp.py):
          * ``"ok"`` or empty → allow silently
          * ``"advisory: ..."`` → allow but log
          * ``"WARNING — ..."`` → allow but surface
          * ``"BLOCKED — ..."`` → hard block
          * ``"PENDING approval — ..."`` → HITL — treat as block for now
        """
        stripped = (text or "").strip()
        # Server emits lowercase "ok" today, but tolerate case + trailing
        # punctuation so a future minor server change doesn't 400 every call.
        if not stripped or stripped.lower().startswith("ok"):
            return cls(verdict="allow", raw=stripped)
        if stripped.startswith("BLOCKED"):
            return cls(
                verdict="block",
                raw=stripped,
                rule_id=_extract_rule_id(stripped),
                message=_strip_prefix(stripped, "BLOCKED"),
            )
        if stripped.startswith("PENDING approval"):
            return cls(
                verdict="approval",
                raw=stripped,
                rule_id=_extract_rule_id(stripped),
                message=_strip_prefix(stripped, "PENDING approval"),
            )
        if stripped.startswith("WARNING"):
            return cls(
                verdict="warning",
                raw=stripped,
                rule_id=_extract_rule_id(stripped),
                message=_strip_prefix(stripped, "WARNING"),
            )
        if stripped.startswith("advisory"):
            return cls(
                verdict="advisory",
                raw=stripped,
                rule_id=_extract_rule_id(stripped),
                message=_strip_prefix(stripped, "advisory"),
            )
        return cls(verdict="unknown", raw=stripped)


def _strip_prefix(text: str, prefix: str) -> str:
    remainder = text[len(prefix):].strip()
    return remainder.lstrip(":—- ").strip() or None  # type: ignore[return-value]


def _extract_rule_id(text: str) -> str | None:
    marker = "[rule:"
    idx = text.find(marker)
    if idx < 0:
        return None
    tail = text[idx + len(marker):]
    end = tail.find("]")
    return tail[:end].strip() if end >= 0 else None


class ConductGuardBlocked(Exception):
    """Raised inside the pre-call hook to abort a LiteLLM request. LiteLLM
    surfaces the message to the caller; keep it short and rule-scoped."""

    def __init__(self, decision: GuardDecision):
        self.decision = decision
        super().__init__(decision.message or decision.raw or "Blocked by Conduct Guard")


class ConductGuard(CustomGuardrail):
    """Conduct Guard, wired as a LiteLLM ``CustomGuardrail``.

    Reads config from LiteLLM's guardrail block. Every pre-call hook
    invocation calls ``guard_check`` on the configured Conduct API using
    the supplied agent token. On block, raises so the LiteLLM proxy
    returns an error to the caller instead of forwarding to the model.

    Session tracking: pulled from the first available of
    ``litellm_metadata.trace_id`` → ``X-Conduct-Session-Id`` header on
    the LiteLLM request → a deterministic hash of the user identifier
    plus the first user message. Documented in ``README.md``."""

    def __init__(
        self,
        *,
        api_url: str | None = None,
        agent_token: str | None = None,
        workspace_id: str | None = None,
        fail_mode: FailMode = "fail_closed",
        timeout: float = 8.0,
        # LiteLLM CustomGuardrail kwargs — accept and forward.
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        # Resolve from env if the config leaves them out — matches
        # LiteLLM's os.environ/VAR pattern (they resolve before us in
        # newer versions but this covers older).
        self._api_url = api_url or os.environ.get("CONDUCT_API_URL", "https://api.conductai.ai")
        token = agent_token or os.environ.get("CONDUCT_AGENT_TOKEN")
        if not token:
            raise ValueError(
                "ConductGuard: agent_token is required. Set CONDUCT_AGENT_TOKEN "
                "in the environment or pass agent_token in the guardrail config."
            )
        self._agent_token = token
        self._workspace_id = workspace_id or os.environ.get("CONDUCT_WORKSPACE_ID")
        self._fail_mode: FailMode = fail_mode
        self._client = GuardCheckClient(
            api_url=self._api_url,
            agent_token=self._agent_token,
            workspace_id=self._workspace_id,
            timeout=timeout,
        )

    # ── LiteLLM contract ───────────────────────────────────────────────

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict[str, Any],
        call_type: str,
    ) -> dict[str, Any]:
        """Pre-call hook. Raises to block, returns the (possibly
        annotated) data to allow. LiteLLM converts our exception into a
        400/403 response to the caller."""
        decision = await self.check(data=data, call_type=call_type)

        if decision.verdict == "block" or decision.verdict == "approval":
            raise ConductGuardBlocked(decision)

        # Warning / advisory / allow all continue. Tag the data so any
        # downstream logger knows the check ran.
        data.setdefault("metadata", {}).setdefault("conduct_guard", {}).update(
            {"verdict": decision.verdict, "rule_id": decision.rule_id}
        )
        return data

    # ── Public helpers usable outside LiteLLM ─────────────────────────

    async def check(self, *, data: dict[str, Any], call_type: str) -> GuardDecision:
        """Run one ``guard_check`` for the given LiteLLM request payload."""
        tool_input = _build_tool_input(data, call_type)
        session_id = _extract_session_id(data)
        prompt = _extract_prompt_text(data)

        try:
            raw = await self._client.guard_check(
                tool_name=call_type or "completion",
                tool_input=tool_input,
                session_id=session_id,
                prompt=prompt,
            )
        except GuardCheckError as e:
            log.warning("conduct_guard: eval error %s — applying %s", e, self._fail_mode)
            if self._fail_mode == "fail_closed":
                return GuardDecision(
                    verdict="block",
                    raw=str(e),
                    message="Conduct Guard policy-eval error (fail_closed).",
                )
            return GuardDecision(verdict="allow", raw="fail_open")
        except Exception as e:  # network, timeout, unexpected
            log.warning("conduct_guard: transport error %s — applying %s", e, self._fail_mode)
            if self._fail_mode == "fail_closed":
                return GuardDecision(
                    verdict="block",
                    raw=str(e),
                    message="Conduct Guard is unreachable (fail_closed).",
                )
            return GuardDecision(verdict="allow", raw="fail_open")

        return GuardDecision.parse(raw)

    async def close(self) -> None:
        """Release the HTTP client. LiteLLM does not call this today; the
        method exists so long-running processes can tear the guardrail
        down cleanly if needed."""
        await self._client.aclose()


# ── Session-ID + prompt helpers ────────────────────────────────────────


def _extract_session_id(data: dict[str, Any]) -> str | None:
    """Preferred → LiteLLM metadata trace_id.
    Fallback → explicit X-Conduct-Session-Id passed through metadata.
    Last resort → deterministic hash of user + first message so
    resume_verdict can still stitch a per-request approval flow together."""
    metadata = data.get("litellm_metadata") or data.get("metadata") or {}
    for key in ("trace_id", "X-Conduct-Session-Id", "conduct_session_id"):
        val = metadata.get(key)
        if val:
            return str(val)

    user = data.get("user") or metadata.get("user") or ""
    first_msg = ""
    for m in (data.get("messages") or []):
        if isinstance(m, dict) and m.get("role") == "user":
            first_msg = str(m.get("content", ""))[:512]
            break
    if not user and not first_msg:
        return None
    digest = hashlib.sha256((user + "|" + first_msg).encode("utf-8")).hexdigest()
    return f"litellm-{digest[:16]}"


def _extract_prompt_text(data: dict[str, Any]) -> str | None:
    """Return the last user message so it lands in the audit trail. We
    intentionally do NOT send the full messages array — Guard only needs
    enough context to render an audit entry."""
    for m in reversed(data.get("messages") or []):
        if isinstance(m, dict) and m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, str):
                return content[:4000]
            if isinstance(content, list):
                # OpenAI-style parts: concat the text ones.
                parts = [
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                return " ".join(parts)[:4000] or None
    return None


def _build_tool_input(data: dict[str, Any], call_type: str) -> dict[str, Any]:
    """Compact payload for the ``tool_input`` field. Guard rules match on
    the model name, provider, and a truncated message digest — we don't
    ship the entire request body."""
    messages = data.get("messages") or []
    return {
        "model": data.get("model"),
        "call_type": call_type,
        "message_count": len(messages),
        "temperature": data.get("temperature"),
        "max_tokens": data.get("max_tokens"),
        "stream": bool(data.get("stream")),
    }
