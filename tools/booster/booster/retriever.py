from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from booster.indexer import SymbolIndexer, _changed_lines_since

_MAX_OUTPUT_BYTES = 5_000


def smart_read(
    file_path: Path,
    task: str,
    indexer: SymbolIndexer,
    since: str | None = None,
) -> str:
    rel = str(file_path.relative_to(indexer.root))
    source_lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()

    # RRF fusion: combines vector + keyword ranks for better symbol selection
    matched = indexer.rrf_search_file(rel, task, limit=5)

    if not matched:
        total = len(source_lines)
        return (
            f"# smart_read: no matching symbols for task in {rel} ({total} lines)\n"
            f"# Use Read tool for full file content."
        )

    # v0.3.0: diff-aware filter — keep only symbols overlapping changed lines.
    if since:
        changed = _changed_lines_since(indexer.root, since)
        file_changes = changed.get(rel, set())
        if not file_changes:
            return f"# smart_read: no changes in {rel} since {since}"
        matched = [
            s for s in matched
            if any(ln in file_changes for ln in range(s["start_line"], s["end_line"] + 1))
        ]
        if not matched:
            return f"# smart_read: no matched symbols overlap changes in {rel} since {since}"

    chunks: list[str] = []
    for sym in matched:
        start = sym["start_line"] - 1
        end = sym["end_line"]
        # v0.3.0 free-fold: staleness header — show last_modified when available
        ts = sym.get("last_modified_ts") or 0
        sha = sym.get("commit_last_modified") or ""
        when = ""
        if ts:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            short = (sha[:8] + " ") if sha else ""
            when = f"  [last_modified: {short}{dt}]"
        header = f"# {sym['kind']} {sym['name']} (lines {sym['start_line']}-{sym['end_line']}){when}"
        body = "\n".join(source_lines[start:end])
        chunks.append(f"{header}\n{body}")

    result = "\n\n".join(chunks)

    # 5KB gate: trim to top-3 symbols if still too large
    if len(result.encode()) > _MAX_OUTPUT_BYTES and len(chunks) > 3:
        result = "\n\n".join(chunks[:3])
        result += f"\n\n# [Truncated: showing top 3 of {len(matched)} matched symbols — use get_symbols for full list]"

    return result
