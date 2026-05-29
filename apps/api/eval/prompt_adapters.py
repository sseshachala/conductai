"""
Per-model-family prompt adapters for the Conduct eval harness.

Different LLM families have distinct conventions for system prompts, output
formatting, and instruction phrasing.  This module normalises brain block
descriptions so they work well across Anthropic, OpenAI, and Google families.

Usage
-----
  from eval.prompt_adapters import adapt_for_model, detect_family

  family = detect_family("claude-sonnet-4-6")         # "anthropic"
  family = detect_family("gpt-4o")                    # "openai"
  family = detect_family("gemini-2.0-flash")          # "google"

  system, instructions = adapt_for_model(description, model="gpt-4o")
"""
from __future__ import annotations

import re
from typing import NamedTuple


# ── model family detection ────────────────────────────────────────────────────

_FAMILY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"claude|anthropic", re.I), "anthropic"),
    (re.compile(r"gpt|o[1-9](-mini|-pro)?$|chatgpt|openai", re.I), "openai"),
    (re.compile(r"gemini|bison|palm|google", re.I), "google"),
    (re.compile(r"llama|mistral|mixtral|qwen|deepseek|command", re.I), "openai"),  # treat open-weight as openai-style
]


def detect_family(model: str) -> str:
    """
    Return the model family for *model*: ``"anthropic"``, ``"openai"``, or ``"google"``.
    Falls back to ``"anthropic"`` (the platform default) when unrecognised.
    """
    for pattern, family in _FAMILY_PATTERNS:
        if pattern.search(model):
            return family
    return "anthropic"


# ── adapter result ────────────────────────────────────────────────────────────

class AdaptedPrompt(NamedTuple):
    system: str      # System prompt string (empty string if the family doesn't use a separate system prompt)
    user: str        # User message content


# ── family-specific adapters ─────────────────────────────────────────────────

def _adapt_anthropic(description: str) -> AdaptedPrompt:
    """
    Canonical Anthropic adapter.

    - Keeps XML-style tags for structured output instructions
    - Adds explicit JSON-only output reminder at the end
    - Separates context from instruction using <context> / <task> tags
    """
    # Extract the JSON contract line if present (last {...} line)
    json_contract = _extract_json_contract(description)
    body = _strip_json_contract(description) if json_contract else description

    system = (
        "You are an expert AI automation assistant. "
        "Follow the task instructions precisely. "
        "Output ONLY valid JSON when a JSON contract is specified — no prose, no markdown."
    )

    user_parts = [f"<task>\n{body.strip()}\n</task>"]
    if json_contract:
        user_parts.append(
            f"\n<output_contract>\n"
            f"Your response MUST be a single JSON object matching this schema:\n"
            f"{json_contract}\n"
            f"</output_contract>"
        )

    return AdaptedPrompt(system=system, user="\n".join(user_parts))


def _adapt_openai(description: str) -> AdaptedPrompt:
    """
    OpenAI adapter.

    - Uses markdown headers instead of XML tags
    - Explicit "Respond with JSON only" instruction in system prompt
    - Avoids XML-style markup (GPT models handle it but markdown reads cleaner)
    """
    json_contract = _extract_json_contract(description)
    body = _strip_json_contract(description) if json_contract else description

    system = (
        "You are an expert AI automation assistant. "
        "You follow instructions precisely and output structured JSON when requested. "
        "Never add commentary or markdown — output only the raw JSON object."
    )

    user_parts = ["## Task\n\n" + body.strip()]
    if json_contract:
        user_parts.append(
            "\n## Output Format\n\n"
            "Respond with a single JSON object matching this schema exactly:\n\n"
            f"```json\n{json_contract}\n```\n\n"
            "Do not include any text outside the JSON object."
        )

    return AdaptedPrompt(system=system, user="\n".join(user_parts))


def _adapt_google(description: str) -> AdaptedPrompt:
    """
    Google (Gemini) adapter.

    Gemini handles system prompts differently depending on the SDK version.
    We collapse system + user into the user turn when family=="google" to be
    safe, and use plain natural language rather than XML or markdown fencing.
    """
    json_contract = _extract_json_contract(description)
    body = _strip_json_contract(description) if json_contract else description

    preamble = (
        "You are an expert AI automation assistant. "
        "Follow the instructions below carefully and respond only with the requested output.\n\n"
    )

    parts = [preamble + "TASK:\n" + body.strip()]
    if json_contract:
        parts.append(
            "\nOUTPUT REQUIREMENT:\n"
            "Respond with a single JSON object. No explanation, no markdown. "
            f"Schema: {json_contract}"
        )

    return AdaptedPrompt(system="", user="\n".join(parts))


_ADAPTERS = {
    "anthropic": _adapt_anthropic,
    "openai": _adapt_openai,
    "google": _adapt_google,
}


# ── public API ────────────────────────────────────────────────────────────────

def adapt_for_model(description: str, model: str) -> AdaptedPrompt:
    """
    Adapt a brain block *description* for the given *model*.

    Returns an :class:`AdaptedPrompt` with ``system`` and ``user`` fields
    ready to pass to the model's API client.

    Parameters
    ----------
    description:
        Raw brain block description text from the playbook YAML.
    model:
        Target model ID (e.g. ``"claude-sonnet-4-6"``, ``"gpt-4o"``).
    """
    family = detect_family(model)
    adapter = _adapters_for(family)
    return adapter(description)


def adapt_judge_prompt(rubric: str, model: str) -> AdaptedPrompt:
    """
    Adapt a judge rubric prompt for the given judge *model*.

    The judge is always called with Haiku by default, but this allows
    the rubric prompt itself to be optimised for a different judge model.
    """
    family = detect_family(model)
    if family == "anthropic":
        system = (
            "You are a strict, objective evaluator of AI automation outputs. "
            "Output ONLY valid JSON. No markdown, no code blocks, no explanation outside JSON."
        )
        return AdaptedPrompt(system=system, user=rubric)
    elif family == "openai":
        system = (
            "You are a strict, objective evaluator. "
            "Respond with raw JSON only — no prose, no code fences."
        )
        return AdaptedPrompt(system=system, user=rubric)
    else:
        return AdaptedPrompt(
            system="",
            user=(
                "You are a strict, objective evaluator. "
                "Output only valid JSON — no prose.\n\n" + rubric
            ),
        )


def model_token_budget(model: str) -> int:
    """
    Return the recommended max_tokens value for a given model when used as judge.

    Larger models with more verbose outputs need a bigger budget.
    """
    family = detect_family(model)
    model_lower = model.lower()
    if "opus" in model_lower:
        return 1024
    if "sonnet" in model_lower or "gpt-4" in model_lower or "gemini-pro" in model_lower:
        return 768
    return 512  # haiku, mini, flash


def all_eval_models() -> list[str]:
    """
    Return the canonical list of models used for multi-model eval runs.
    Matches the Northstar Layer 2 requirement: ≥3 model coverage.
    """
    return [
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-6",
        "claude-opus-4-7",
    ]


# ── internal helpers ──────────────────────────────────────────────────────────

_JSON_LAST_LINE_RE = re.compile(r'\{[^}]+\}\s*$', re.DOTALL)


def _extract_json_contract(description: str) -> str:
    """Return the JSON contract line from a brain block description, or empty string."""
    m = _JSON_LAST_LINE_RE.search(description.strip())
    return m.group().strip() if m else ""


def _strip_json_contract(description: str) -> str:
    """Remove the trailing JSON contract from a description."""
    return _JSON_LAST_LINE_RE.sub("", description).rstrip()


def _adapters_for(family: str):
    return _ADAPTERS.get(family, _adapt_anthropic)
