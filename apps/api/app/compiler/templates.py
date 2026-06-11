"""
Per-block-type compilation templates.
Each template takes extracted slots and produces a final system prompt.
The English description is always canonical — this output is derived.

Prompt text lives in compiler/prompts/*.jinja2.  This module loads every
template at import time and exposes the same public functions as before so
callers (compiler.py) need no changes.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=None)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PROMPTS_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def _render(template_name: str, **kwargs: object) -> str:
    return _env().get_template(template_name).render(**kwargs).rstrip("\n")


# ── public functions — signatures unchanged ────────────────────────────────────

def brain_prompt(
    goal: str,
    constraints: list[str],
    output_description: str,
    is_agentic: bool,
    integration: str | None,
) -> str:
    constraints_text = (
        "\n".join(f"- {c}" for c in constraints) if constraints else "- Use good judgment"
    )
    tool_hint = (
        f"\n\nThis block is connected to the `{integration}` integration."
        if integration
        else ""
    )
    mode_hint = (
        "\n\nYou are running in **agentic mode**. Think through the problem carefully across "
        "multiple reasoning steps. Work iteratively. Stop when the goal is fully achieved or "
        "you hit your budget."
        if is_agentic
        else "\n\nYou are running in **single-call mode**. Produce your complete answer in one response."
    )
    return _render(
        "brain.jinja2",
        goal=goal,
        constraints_text=constraints_text,
        output_description=output_description,
        tool_hint=tool_hint,
        mode_hint=mode_hint,
    )


def tool_prompt(action: str, integration: str | None, parameters: list[str]) -> str:
    params_text = (
        "\n".join(f"- {p}" for p in parameters)
        if parameters
        else "- Use context from previous blocks"
    )
    integration_line = (
        f"Use the `{integration}` integration." if integration else "Use available tools."
    )
    return _render(
        "tool.jinja2",
        action=action,
        integration_line=integration_line,
        params_text=params_text,
    )


def trigger_config(event: str, conditions: list[str]) -> str:
    conditions_text = (
        "\n".join(f"- {c}" for c in conditions) if conditions else "- No additional filters"
    )
    return _render("trigger.jinja2", event=event, conditions_text=conditions_text)


def output_prompt(message_template: str, channel_hint: str | None) -> str:
    channel = f" to {channel_hint}" if channel_hint else ""
    return _render("output.jinja2", channel=channel, message_template=message_template)


def logic_prompt(condition: str, branches: list[str]) -> str:
    branches_text = "\n".join(f"- {b}" for b in branches)
    return _render("logic.jinja2", condition=condition, branches_text=branches_text)


def generic_prompt(description: str, block_type: str) -> str:
    return _render("generic.jinja2", description=description, block_type=block_type)
