"""
Per-block-type compilation templates.
Each template takes extracted slots and produces a final system prompt.
The English description is always canonical — this output is derived.
"""

def brain_prompt(goal: str, constraints: list[str], output_description: str, is_agentic: bool, integration: str | None) -> str:
    constraints_text = "\n".join(f"- {c}" for c in constraints) if constraints else "- Use good judgment"
    tool_hint = f"\n\nThis block is connected to the `{integration}` integration." if integration else ""
    mode_hint = (
        "\n\nYou are running in **agentic mode**. Think through the problem carefully across multiple reasoning steps. "
        "Work iteratively. Stop when the goal is fully achieved or you hit your budget."
        if is_agentic else
        "\n\nYou are running in **single-call mode**. Produce your complete answer in one response."
    )

    return f"""You are a precise AI agent executing a single, well-scoped task.

## Goal
{goal}

## Constraints
{constraints_text}

## Output
{output_description}
{tool_hint}{mode_hint}

Think step by step. Be concise. Do not hallucinate tool names or APIs."""


def tool_prompt(action: str, integration: str | None, parameters: list[str]) -> str:
    params_text = "\n".join(f"- {p}" for p in parameters) if parameters else "- Use context from previous blocks"
    integration_line = f"Use the `{integration}` integration." if integration else "Use available tools."

    return f"""Execute the following action precisely: {action}

{integration_line}

## Parameters to use
{params_text}

Return structured output. Do not perform any action beyond what is described."""


def trigger_config(event: str, conditions: list[str]) -> str:
    conditions_text = "\n".join(f"- {c}" for c in conditions) if conditions else "- No additional filters"
    return f"""Trigger event: {event}

Activation conditions:
{conditions_text}

This block starts the workflow when the above conditions are met."""


def output_prompt(message_template: str, channel_hint: str | None) -> str:
    channel = f" to {channel_hint}" if channel_hint else ""
    return f"""Send the following message{channel}:

{message_template}

Use variables from previous blocks where referenced with {{{{block_id.field}}}} syntax.
Keep the message clear and human-readable."""


def logic_prompt(condition: str, branches: list[str]) -> str:
    branches_text = "\n".join(f"- {b}" for b in branches)
    return f"""Evaluate the following condition and route accordingly:

Condition: {condition}

Possible routes:
{branches_text}

Return only the route label that matches. No explanation needed."""


def generic_prompt(description: str, block_type: str) -> str:
    return f"""Execute the following {block_type} block task:

{description}

Follow the description precisely. Return structured output compatible with downstream blocks."""
