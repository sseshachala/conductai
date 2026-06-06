from __future__ import annotations

from pathlib import Path

from booster.indexer import SymbolIndexer

_MAX_OUTPUT_BYTES = 5_000


def smart_read(file_path: Path, task: str, indexer: SymbolIndexer) -> str:
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

    chunks: list[str] = []
    for sym in matched:
        start = sym["start_line"] - 1
        end = sym["end_line"]
        header = f"# {sym['kind']} {sym['name']} (lines {sym['start_line']}-{sym['end_line']})"
        body = "\n".join(source_lines[start:end])
        chunks.append(f"{header}\n{body}")

    result = "\n\n".join(chunks)

    # 5KB gate: trim to top-3 symbols if still too large
    if len(result.encode()) > _MAX_OUTPUT_BYTES and len(chunks) > 3:
        result = "\n\n".join(chunks[:3])
        result += f"\n\n# [Truncated: showing top 3 of {len(matched)} matched symbols — use get_symbols for full list]"

    return result
