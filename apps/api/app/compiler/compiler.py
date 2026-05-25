"""
Compiler — turns plain-English block descriptions into structured prompts + tool schemas.

Two-step process for Brain blocks:
  1. Extraction call (Claude Sonnet): English → structured slots (goal, constraints, output)
  2. Template assembly: slots + block config → final system prompt

All other block types use lighter single-step compilation.
"""
import json
import structlog
from typing import Any

import anthropic

from app.core.config import settings
from app.compiler.templates import (
    brain_prompt, tool_prompt, trigger_config,
    output_prompt, logic_prompt, generic_prompt,
)

log = structlog.get_logger(__name__)

EXTRACTION_TOOL = {
    "name": "extract_block_slots",
    "description": "Extract structured slots from a plain-English block description",
    "input_schema": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "One sentence: the primary objective of this block"
            },
            "constraints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific rules, limits, or boundaries the block must respect"
            },
            "output_description": {
                "type": "string",
                "description": "What the block should return or produce"
            },
            "key_actions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The main verbs / actions this block will perform"
            },
            "parameters": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Inputs or variables this block needs from context"
            }
        },
        "required": ["goal", "constraints", "output_description", "key_actions"]
    }
}


def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _extract_slots(description: str, client: anthropic.Anthropic) -> dict[str, Any]:
    """Step 1: extract structured slots from plain English using Claude."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=(
            "You are a compiler for an AI agent workflow platform. "
            "Extract structured information from plain-English block descriptions. "
            "Be precise and literal — do not add information not present in the description."
        ),
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "extract_block_slots"},
        messages=[{"role": "user", "content": f'Block description: "{description}"'}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_block_slots":
            return block.input

    return {"goal": description, "constraints": [], "output_description": "Produce relevant output", "key_actions": []}


def compile_block(block: dict[str, Any]) -> dict[str, Any] | None:
    """
    Compile a single block. Returns a compiled artifact dict or None if nothing to compile.
    Artifact shape: { system_prompt, model, mode, raw_slots }
    """
    data = block.get("data", {})
    block_type = data.get("type", "")
    description = data.get("description", "").strip()
    label = data.get("label", "")
    integration = data.get("integration")
    is_agentic = data.get("isAgentic", False)

    if not description:
        return None

    if not settings.anthropic_api_key:
        # No API key — return a placeholder so the UI still shows something
        return {
            "system_prompt": f"[Compiler not configured — set ANTHROPIC_API_KEY]\n\nDescription: {description}",
            "model": "claude-sonnet-4-6",
            "mode": "agentic" if is_agentic else "single",
            "raw_slots": {},
        }

    client = get_client()

    try:
        if block_type == "brain":
            slots = _extract_slots(description, client)
            prompt = brain_prompt(
                goal=slots.get("goal", description),
                constraints=slots.get("constraints", []),
                output_description=slots.get("output_description", "Produce relevant output"),
                is_agentic=is_agentic,
                integration=integration,
            )
            return {
                "system_prompt": prompt,
                "model": "claude-sonnet-4-6",
                "mode": "agentic" if is_agentic else "single",
                "raw_slots": slots,
            }

        elif block_type == "tool":
            slots = _extract_slots(description, client)
            prompt = tool_prompt(
                action=slots.get("goal", description),
                integration=integration,
                parameters=slots.get("parameters", []),
            )
            return {"system_prompt": prompt, "model": None, "mode": "tool", "raw_slots": slots}

        elif block_type == "trigger":
            slots = _extract_slots(description, client)
            prompt = trigger_config(
                event=slots.get("goal", label),
                conditions=slots.get("constraints", []),
            )
            return {"system_prompt": prompt, "model": None, "mode": "trigger", "raw_slots": slots}

        elif block_type == "output":
            slots = _extract_slots(description, client)
            prompt = output_prompt(
                message_template=slots.get("goal", description),
                channel_hint=integration,
            )
            return {"system_prompt": prompt, "model": None, "mode": "output", "raw_slots": slots}

        elif block_type == "logic":
            slots = _extract_slots(description, client)
            prompt = logic_prompt(
                condition=slots.get("goal", description),
                branches=slots.get("key_actions", ["pass", "fail"]),
            )
            return {"system_prompt": prompt, "model": None, "mode": "logic", "raw_slots": slots}

        else:
            return {
                "system_prompt": generic_prompt(description, block_type),
                "model": None,
                "mode": block_type,
                "raw_slots": {},
            }

    except Exception as e:
        log.error("compile.block_error", block_id=block.get("id"), error=str(e))
        return {
            "system_prompt": f"[Compiler error: {e}]\n\nOriginal description: {description}",
            "model": None,
            "mode": block_type,
            "raw_slots": {},
        }


def compile_workflow(graph: dict[str, Any]) -> dict[str, Any]:
    """
    Compile all blocks in a workflow graph.
    Returns compiled_artifacts: { block_id -> artifact }
    """
    nodes = graph.get("nodes", [])
    artifacts: dict[str, Any] = {}

    for node in nodes:
        block_id = node.get("id")
        if not block_id:
            continue
        artifact = compile_block(node)
        if artifact:
            artifacts[block_id] = artifact
            log.info("compile.block_done", block_id=block_id, block_type=node.get("data", {}).get("type"))

    return artifacts
