"""
Streaming compiler — generates a system prompt for a single block using Claude's streaming API.
Returns an SSE generator for use with FastAPI StreamingResponse.
"""
import json
import logging
from typing import Generator, Any

import anthropic

from app.core.config import settings

log = logging.getLogger(__name__)

COMPILER_SYSTEM = """You are a system prompt compiler for an AI workflow platform called Delegator.

Given a plain-English block description, generate a precise, well-structured system prompt.
The prompt should:
- Open with a clear goal statement
- List constraints and boundaries
- Specify the exact output format
- Include integration/tool guidance when relevant
- Be concise — no filler, no repetition

Respond ONLY with the system prompt text. No preamble, no explanation."""


def _build_user_message(block: dict[str, Any]) -> str:
    data = block.get("data", {})
    block_type = data.get("type", "tool")
    label = data.get("label", "")
    description = data.get("description", "")
    integration = data.get("integration")
    is_agentic = data.get("isAgentic", False)

    lines = [
        f"Block type: {block_type}",
        f"Block name: {label}",
        f"Description: {description}",
    ]
    if integration:
        lines.append(f"Integration: {integration}")
    if block_type == "brain":
        lines.append(f"Execution mode: {'agentic (tool-calling loop)' if is_agentic else 'single LLM call'}")

    return "\n".join(lines) + "\n\nGenerate the system prompt:"


def stream_compile_block(block: dict[str, Any]) -> Generator[str, None, None]:
    """
    Yields SSE-formatted chunks: data: {"text": "..."}\n\n
    Ends with: data: [DONE]\n\n
    """
    description = block.get("data", {}).get("description", "").strip()

    if not description:
        yield f"data: {json.dumps({'text': '(no description — add one in the Plain English tab)'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    if not settings.anthropic_api_key:
        yield f"data: {json.dumps({'text': '[Set ANTHROPIC_API_KEY to enable compilation]'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=COMPILER_SYSTEM,
            messages=[{"role": "user", "content": _build_user_message(block)}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as e:
        log.error("Stream compile error: %s", e)
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"
