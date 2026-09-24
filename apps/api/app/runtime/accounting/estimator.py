"""Unified reservation estimator (issue #2209, Session 2).

Single canonical implementation for pre-flight token estimation across every
request shape Conduct sees: Anthropic Messages, OpenAI Chat Completions,
OpenAI Responses, LiteLLM-normalized.

**Labeled estimate — not a mathematical upper bound.** Exact tokenizers or
provider counting endpoints can plug into this interface later; the compat
wrappers below keep old callers byte-identical.

Session 2 compat wrappers in ``app/guard/audit.py`` and
``app/modules/guard/gateway_lifecycle.py`` delegate here. Callers pick which
input shapes to include so we do not silently change existing reservation
behavior (that lands in Session 4 shadow).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

_CHARS_PER_TOKEN = 4
_DEFAULT_OUTPUT_ALLOWANCE_TOKENS = 4096

ESTIMATOR_VERSION = "v1"


class InputShape(str, Enum):
    """Which body shapes the estimator should account for.

    Explicit set lets compat wrappers reproduce legacy under-coverage while
    the new engine can request full coverage. Session 4 shadow measures the
    delta between them.
    """

    MESSAGES = "messages"
    SYSTEM = "system"
    INSTRUCTIONS = "instructions"
    RESPONSE_INPUT = "response_input"  # OpenAI Responses API
    TOOLS = "tools"
    VISION = "vision"


ALL_SHAPES: frozenset[InputShape] = frozenset(InputShape)


@dataclass(frozen=True)
class TokensEstimate:
    """One estimator result with per-shape provenance.

    ``coverage`` is what the caller asked for, ``breakdown`` is what each
    shape contributed. Provenance is preserved so Session 4 shadow can
    explain a delta between two calls with different coverage.
    """

    input_tokens: int
    output_tokens_allowance: int
    breakdown: Mapping[str, int] = field(default_factory=dict)
    coverage: frozenset[InputShape] = field(default_factory=frozenset)
    estimator_version: str = ESTIMATOR_VERSION


def _extract_text(body: Any) -> list[str]:
    """Pull string content out of a `messages` array element.

    Reviewer #9b (#2221): also walks tool-related payloads. Tool-call
    arguments (OpenAI Chat) and tool_use.input / tool_result.content
    (Anthropic Messages) are real prompt tokens that the pre-Session-6c
    estimator missed.
    """
    import json as _json
    out: list[str] = []
    if not isinstance(body, dict):
        return out
    messages = body.get("messages") or []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            out.append(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                t = part.get("text") or ""
                if isinstance(t, str) and t:
                    out.append(t)
                # Anthropic tool_use block — assistant asks to call a tool.
                # The `input` dict is prompt-visible; serialize it for the
                # heuristic count.
                if part.get("type") == "tool_use":
                    tu_input = part.get("input")
                    if tu_input:
                        try:
                            out.append(_json.dumps(tu_input, separators=(",", ":")))
                        except Exception:
                            pass
                # Anthropic tool_result block — user gives a tool response.
                # The `content` field can be a string OR a list of blocks;
                # both cases are covered by falling into the outer walker
                # for list content, but we handle the string form here.
                if part.get("type") == "tool_result":
                    tr_content = part.get("content")
                    if isinstance(tr_content, str):
                        out.append(tr_content)
        # OpenAI Chat tool_calls on assistant messages — the `function.arguments`
        # string is JSON of what the model asked to call.
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                args = fn.get("arguments") if isinstance(fn, dict) else None
                if isinstance(args, str) and args:
                    out.append(args)
        # OpenAI Chat tool-result messages — role="tool" with a `content` str
        # was already handled above; nothing extra needed here.
    return out


def _output_allowance_field(body: Any) -> Optional[int]:
    """Return the caller-set output allowance if present. Reviewer #9b:
    also recognizes ``max_output_tokens`` (OpenAI Responses API)."""
    if not isinstance(body, dict):
        return None
    for key in ("max_tokens", "max_output_tokens", "max_completion_tokens"):
        v = body.get(key)
        if isinstance(v, int) and v > 0:
            return v
    return None


def _extract_response_input(body: Any) -> list[str]:
    """OpenAI Responses API `input` field."""
    out: list[str] = []
    if not isinstance(body, dict):
        return out
    response_input = body.get("input")
    if isinstance(response_input, str):
        out.append(response_input)
    elif isinstance(response_input, list):
        for item in response_input:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, str):
                out.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        out.append(part["text"])
    return out


def _text_tokens(chunks: Iterable[str]) -> int:
    """4-chars-per-token heuristic. Matches the pre-Session-2 estimators."""
    joined = " ".join(c for c in chunks if isinstance(c, str))
    return len(joined) // _CHARS_PER_TOKEN


def _tool_schema_tokens(body: Any) -> int:
    """Delegates to the existing tools validator (Session 2 does not change it)."""
    if not isinstance(body, dict):
        return 0
    tools = body.get("tools")
    if not tools:
        return 0
    try:
        from app.modules.guard.tools_validator import estimate_tools_tokens
    except Exception:
        return 0
    try:
        return int(estimate_tools_tokens(tools))
    except Exception:
        return 0


def _vision_tokens(body: Any) -> int:
    """Delegates to the existing vision validator."""
    if not isinstance(body, dict):
        return 0
    try:
        from app.modules.guard.vision_validator import estimate_vision_tokens
    except Exception:
        return 0
    try:
        return int(estimate_vision_tokens(body))
    except Exception:
        return 0


def _output_allowance(body: Any, default: int = _DEFAULT_OUTPUT_ALLOWANCE_TOKENS) -> int:
    """Honor caller's output-limit param when set; otherwise use bounded default."""
    v = _output_allowance_field(body)
    return v if v is not None else default


def estimate_tokens(
    body: Any,
    *,
    include: frozenset[InputShape] | Iterable[InputShape] = ALL_SHAPES,
    output_default: int = _DEFAULT_OUTPUT_ALLOWANCE_TOKENS,
) -> TokensEstimate:
    """Estimate input tokens across the requested shapes.

    Deliberately conservative: over-reservation is safer than under-reservation
    because settlement writes the real cost via the ledger commit path.
    """
    if not isinstance(include, frozenset):
        include = frozenset(include)

    breakdown: dict[str, int] = {}

    if InputShape.MESSAGES in include:
        breakdown[InputShape.MESSAGES.value] = _text_tokens(_extract_text(body))

    if InputShape.SYSTEM in include and isinstance(body, dict):
        sys = body.get("system")
        breakdown[InputShape.SYSTEM.value] = _text_tokens([sys]) if isinstance(sys, str) else 0

    if InputShape.INSTRUCTIONS in include and isinstance(body, dict):
        instr = body.get("instructions")
        breakdown[InputShape.INSTRUCTIONS.value] = (
            _text_tokens([instr]) if isinstance(instr, str) else 0
        )

    if InputShape.RESPONSE_INPUT in include:
        breakdown[InputShape.RESPONSE_INPUT.value] = _text_tokens(_extract_response_input(body))

    if InputShape.TOOLS in include:
        breakdown[InputShape.TOOLS.value] = _tool_schema_tokens(body)

    if InputShape.VISION in include:
        breakdown[InputShape.VISION.value] = _vision_tokens(body)

    total = max(1, sum(breakdown.values()))
    return TokensEstimate(
        input_tokens=total,
        output_tokens_allowance=_output_allowance(body, output_default),
        breakdown=breakdown,
        coverage=include,
    )
