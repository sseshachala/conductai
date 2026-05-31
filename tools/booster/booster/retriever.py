from __future__ import annotations

from pathlib import Path

from booster.indexer import SymbolIndexer


def smart_read(file_path: Path, task: str, indexer: SymbolIndexer) -> str:
    rel = str(file_path.relative_to(indexer.root))
    keywords = [w.lower() for w in task.split() if len(w) > 2]

    all_symbols = indexer.get_symbols(rel)
    matched = [
        s for s in all_symbols
        if any(kw in s["name"].lower() or kw in s["signature"].lower() for kw in keywords)
    ]

    source_lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()

    if not matched:
        return "\n".join(source_lines)

    chunks: list[str] = []
    for sym in matched:
        start = sym["start_line"] - 1
        end = sym["end_line"]
        header = f"# {sym['kind']} {sym['name']} (lines {sym['start_line']}-{sym['end_line']})"
        body = "\n".join(source_lines[start:end])
        chunks.append(f"{header}\n{body}")

    return "\n\n".join(chunks)
