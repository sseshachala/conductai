"""Parallel tool dispatch helper.

When an LLM turn returns N `tool_use` blocks (Anthropic/OpenAI both support
this), the app used to run each dispatch serially:

    for block in tool_blocks:
        result = dispatcher(block.name, args_json)

That serialised N independent DB reads even though SQLAlchemy handles
concurrent sessions on separate connections. This helper runs them
concurrently via ThreadPoolExecutor, preserving input order in the
returned list so tool_use_id ↔ tool_result pairing stays intact.

Uses:
- Lens chat (`_resolve_tools` in glens/routers/chat.py) — main consumer,
  Lens LLM often calls 2-4 read tools per turn.
- MCP core (`_handle_tools_call` in mcp/server.py) — single tool per
  request today, so this helper is a no-op for that path; kept generic
  so future batched MCP requests get the parallel path for free.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

from app.runtime.llm_client import LLMToolUseBlock


def dispatch_tool_blocks(
    blocks: Iterable[LLMToolUseBlock],
    dispatcher: Callable[[str, str], str],
    *,
    max_workers: int | None = None,
) -> list[tuple[str, str]]:
    """Dispatch each tool_use block via `dispatcher(name, args_json)` and
    return `[(tool_use_id, result_str), ...]` in the SAME order as the
    input blocks — critical because the LLM correlates tool_result entries
    back to tool_use blocks by id, and some providers get confused by
    reordered results.

    Args:
        blocks:     LLMToolUseBlock instances from the LLM response.
        dispatcher: Callable that takes (tool_name, args_json_string) and
                    returns a result string. Typically
                    `app.mcp.lens_adapter.dispatch` bound to a lens_ctx.
        max_workers: Optional cap on concurrent dispatches. Defaults to
                    the number of blocks. Cap it if downstream calls
                    contend for a shared resource (DB pool, external API
                    rate limits).

    Returns:
        A list of `(tool_use_id, result_str)` tuples matching the input
        order of `blocks`.

    Ordering guarantee:
        Results are collected using `future.result()` on futures held in
        the SAME order as blocks — so completion order doesn't affect
        the returned list.

    Single-block fast path:
        Skip the ThreadPoolExecutor entirely when there's only one block.
        Avoids pool spin-up overhead for the common LLM turn.
    """
    blocks_list = list(blocks)
    if not blocks_list:
        return []
    if len(blocks_list) == 1:
        b = blocks_list[0]
        return [(b.id, dispatcher(b.name, json.dumps(b.input)))]

    workers = max_workers or len(blocks_list)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(dispatcher, b.name, json.dumps(b.input)) for b in blocks_list]
        return [(b.id, f.result()) for b, f in zip(blocks_list, futures)]
