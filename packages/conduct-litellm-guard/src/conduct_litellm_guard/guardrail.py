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
import re
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from conduct_litellm_guard._client import GuardCheckClient, GuardCheckError

log = logging.getLogger(__name__)

# LiteLLM ships its own CustomGuardrail base class. Import lazily so the
# package installs and imports on a machine that only wants the client
# (e.g. running the unit tests without a real LiteLLM install).
try:
    from litellm.integrations.custom_guardrail import CustomGuardrail  # type: ignore
    from litellm.types.guardrails import GuardrailEventHooks as _LiteLLMHooks  # type: ignore
    _LITELLM_AVAILABLE = True
    # LiteLLM's guardrail registry scans SUPPORTED_EVENT_HOOKS and calls
    # ``.value`` on each entry — must be the ``GuardrailEventHooks`` enum,
    # not a bare string. Regression fix in 0.2.4 (BerriAI/litellm#38143).
    _PRE_CALL_HOOK: Any = _LiteLLMHooks.pre_call
except Exception:  # pragma: no cover — exercised via test double
    _LITELLM_AVAILABLE = False

    class CustomGuardrail:  # type: ignore[no-redef]
        """Fallback base used only when litellm isn't installed. Lets tests
        exercise the adapter without pulling the whole LiteLLM tree in."""

        def __init__(self, **kwargs: Any) -> None:
            self.guardrail_name = kwargs.get("guardrail_name")
            self.event_hook = kwargs.get("event_hook")
            self.default_on = kwargs.get("default_on", True)

    _PRE_CALL_HOOK = "pre_call"


Verdict = Literal["allow", "advisory", "warning", "block", "approval", "unknown"]
FailMode = Literal["fail_open", "fail_closed"]

# Server prefixes tool responses with "[ws:xxxxxxxx] " for debug context
# (apps/api/app/modules/guard/routers/mcp.py:_text). Strip before matching or
# every verdict falls through to "unknown" and BLOCKED responses never fire.
_WS_PREFIX = re.compile(r"^\[ws:[^\]]+\]\s*")


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
        stripped = _WS_PREFIX.sub("", (text or "").strip())
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


try:
    # Prefer FastAPI's HTTPException so LiteLLM's exception handler maps
    # the block to HTTP 400 instead of the default 500 "internal error".
    # A guardrail block is a bad-request semantic — the caller sent
    # something disallowed by policy. LiteLLM already depends on FastAPI.
    from fastapi import HTTPException as _BlockBase  # type: ignore[import-not-found]
    _BLOCK_STATUS = 400
except ImportError:  # pragma: no cover — FastAPI is always present under LiteLLM
    _BlockBase = Exception  # type: ignore[misc,assignment]
    _BLOCK_STATUS = None


class ConductGuardBlocked(_BlockBase):
    """Raised inside the pre-call hook to abort a LiteLLM request.

    Inherits from ``fastapi.HTTPException`` when available so LiteLLM's
    exception handler surfaces the block as HTTP 400 (bad-request semantic
    for a policy violation) — not the misleading 500 default that a plain
    ``Exception`` subclass falls through to. Falls back to a plain
    ``Exception`` if FastAPI isn't importable (won't happen inside the
    LiteLLM proxy, but keeps the module importable in bare unit tests).
    """

    def __init__(self, decision: GuardDecision):
        self.decision = decision
        msg = decision.message or decision.raw or "Blocked by Conduct Guard"
        if _BLOCK_STATUS is not None:
            # HTTPException signature: (status_code, detail)
            super().__init__(status_code=_BLOCK_STATUS, detail=msg)
        else:
            super().__init__(msg)


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

    # ── Event-hook advertisement ─────────────────────────────────────
    # LiteLLM's guardrail-registration flow calls
    # ``get_supported_event_hooks`` to validate the ``mode:`` in the
    # config block. Ship the tuple + classmethod here so upstream shims
    # (the ``litellm/proxy/guardrails/guardrail_hooks/conduct`` module)
    # can be pure aliases with no subclass — keeps their type-discipline
    # gates satisfied. Add ``response`` when ``guard_check_response``
    # ships (plugin 0.3.x).
    # LiteLLM's registry scan calls ``.value`` on each entry — must be
    # the ``GuardrailEventHooks`` enum member when LiteLLM is installed
    # (the only case anyone actually uses this class in prod).
    SUPPORTED_EVENT_HOOKS: ClassVar[tuple[Any, ...]] = (_PRE_CALL_HOOK,)

    @classmethod
    def get_supported_event_hooks(cls) -> list:
        """Return the ``mode:`` values LiteLLM should accept for this
        guardrail. LiteLLM rejects any config that requests an
        unsupported mode at load time — prevents silent bypass of
        e.g. ``during_call`` configurations."""
        return list(cls.SUPPORTED_EVENT_HOOKS)

    def __init__(
        self,
        *,
        api_url: str | None = None,
        agent_token: str | None = None,
        workspace_id: str | None = None,
        # Rename per BerriAI/litellm#38143 (yucheng-berri, Sep 2026).
        # `fail_mode` silently defaulted to fail-open on typo in the config
        # field name. `unreachable_fallback` matches the typed field in
        # LitellmParams (Pydantic-validated), so a typo now surfaces a
        # config error instead of quietly bypassing the safe default.
        unreachable_fallback: FailMode | None = None,
        # Deprecated alias — keep for one release cycle (through 0.2.x).
        # Callers using the old name get a DeprecationWarning; combined
        # with the ``or`` chain below, an unset value falls through to
        # the ``fail_closed`` default.
        fail_mode: FailMode | None = None,
        tool_name: str = "llm_call",
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
        if fail_mode is not None:
            import warnings as _w
            _w.warn(
                "ConductGuard: `fail_mode=` is deprecated in favor of "
                "`unreachable_fallback=` and will be removed in v0.3.0.",
                DeprecationWarning,
                stacklevel=2,
            )
        self._unreachable_fallback: FailMode = unreachable_fallback or fail_mode or "fail_closed"
        # Kept for config-compat; no longer used. The plugin now routes
        # through guard_check_prompt (prompt-gate → proxy-persona rules),
        # so match_tool is not the filter — match_pattern on the prompt is.
        # Existing configs that set `tool_name: llm_call` (or workflow /
        # action) continue to load without error; the value is ignored.
        self._tool_name = tool_name
        self._client = GuardCheckClient(
            api_url=self._api_url,
            agent_token=self._agent_token,
            workspace_id=self._workspace_id,
            surface="litellm",
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
        # Normalise call_type so every LiteLLM invocation reports as
        # tool_name=llm_call. Granularity (acompletion / embedding /
        # image / etc) lives inside tool_input.call_type, matching the
        # existing Guard rule ergonomics for CLI tools.
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
        """Run one ``guard_check_prompt`` for the given LiteLLM request payload."""
        session_id = _extract_session_id(data)
        prompt = _extract_prompt_text(data) or ""
        model = data.get("model") or None
        provider = _extract_provider(data)

        try:
            raw = await self._client.guard_check(
                prompt=prompt,
                model=model,
                provider=provider,
                session_id=session_id,
            )
        except GuardCheckError as e:
            log.warning("conduct_guard: eval error %s — applying %s", e, self._unreachable_fallback)
            if self._unreachable_fallback == "fail_closed":
                return GuardDecision(
                    verdict="block",
                    raw=str(e),
                    message="Conduct Guard policy-eval error (fail_closed).",
                )
            return GuardDecision(verdict="allow", raw="fail_open")
        except Exception as e:  # network, timeout, unexpected
            log.warning("conduct_guard: transport error %s — applying %s", e, self._unreachable_fallback)
            if self._unreachable_fallback == "fail_closed":
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


_MAX_PROMPT_CHARS = 200_000  # ~50k tokens; larger than any single-turn prompt
                             # a modern model accepts. Effectively unbounded
                             # for the scan while still capping runaway payloads.


def _extract_prompt_text(data: dict[str, Any]) -> str | None:
    """Return the prompt text so it lands in the audit trail AND is
    scanned by Guard's proxy-persona rules.

    Handles both LiteLLM request shapes:
      - chat_completion: ``messages[]`` — scans every user message,
        concatenated, so an attacker can't hide payload in an earlier
        turn (BerriAI/litellm#38143 review, veria-ai finding).
      - text_completion: ``prompt`` — the raw prompt string or list
        (veria-ai finding — this path was previously bypassed entirely).

    Length cap raised to 200k chars so realistic long-context prompts
    are not silently truncated; policy scan sees the whole payload.
    The audit trail's ``input_summary`` still redacts + trims to a
    short preview at write time (Property 9), so no raw payload
    lands in a receipt.
    """
    text_parts: list[str] = []

    # text_completion path — prompt can be str or list[str] or list[list[int]]
    prompt = data.get("prompt")
    if isinstance(prompt, str):
        text_parts.append(prompt)
    elif isinstance(prompt, list):
        for p in prompt:
            if isinstance(p, str):
                text_parts.append(p)
            # token-id lists (list[int]) are unmodelled — pass on, they don't
            # carry policy-relevant string content.

    # chat_completion path — every user turn, not just the last one.
    # Earlier turns can carry credential leaks / injection payloads that a
    # last-message-only scan would miss.
    for m in data.get("messages") or []:
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            # OpenAI-style multipart: concat the text parts, skip images.
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    text_parts.append(p.get("text", ""))

    if not text_parts:
        return None
    joined = "\n".join(text_parts)
    return joined[:_MAX_PROMPT_CHARS] if joined else None


def _extract_provider(data: dict[str, Any]) -> str | None:
    """Best-effort read of the upstream provider name from a LiteLLM request.

    LiteLLM sometimes routes purely by ``model`` (``anthropic/claude-3-5-...``);
    sometimes callers pass ``custom_llm_provider`` explicitly. Prefer the
    explicit value; else split the model prefix on the first ``/``.
    """
    explicit = data.get("custom_llm_provider") or data.get("provider")
    if explicit:
        return str(explicit)
    model = data.get("model") or ""
    if "/" in model:
        return model.split("/", 1)[0]
    return None
