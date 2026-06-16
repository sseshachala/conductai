"""SmartCrusher — compress large MCP tool outputs before they reach the model.

Kicks in above THRESHOLD bytes. Three strategies, applied in order:
1. JSON array dedup — keep head + tail, drop middle duplicates
2. Consecutive line dedup — collapse repeated lines into "x N more"
3. Passthrough — content below threshold or unrecognised format

Only reduces size, never changes meaning of first/last entries.
"""
from __future__ import annotations

import json

THRESHOLD = 2048  # bytes — skip crushing below this
_HEAD = 5
_TAIL = 3


def crush(text: str) -> tuple[str, int, int]:
    """Return (crushed_text, original_bytes, crushed_bytes).

    If nothing was saved, returns the original text unchanged.
    """
    original = len(text.encode())
    if original <= THRESHOLD:
        return text, original, original

    result = _try_json_array(text) or _dedup_lines(text)
    crushed = len(result.encode())
    # never return something larger
    if crushed >= original:
        return text, original, original
    return result, original, crushed


# --- strategies ---

def _try_json_array(text: str) -> str | None:
    stripped = text.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return None
    try:
        items = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(items, list) or len(items) <= _HEAD + _TAIL + 1:
        return None

    head = items[:_HEAD]
    tail = items[-_TAIL:]
    dropped = len(items) - _HEAD - _TAIL

    # dedup within head/tail by value
    seen: set[str] = set()
    deduped_head: list = []
    for item in head:
        key = json.dumps(item, sort_keys=True)
        if key not in seen:
            seen.add(key)
            deduped_head.append(item)

    kept = deduped_head + tail
    result = json.dumps(kept, indent=None)
    return f"{result}\n// SmartCrusher: dropped {dropped} middle entries ({len(items)} total)"


def _dedup_lines(text: str) -> str:
    lines = text.splitlines()
    if len(lines) <= 20:
        return text

    out: list[str] = []
    prev: str | None = None
    run = 0

    for line in lines:
        if line == prev:
            run += 1
        else:
            if run > 0:
                out.append(f"// … {run} identical line(s) omitted")
                run = 0
            out.append(line)
            prev = line

    if run > 0:
        out.append(f"// … {run} identical line(s) omitted")

    return "\n".join(out)
