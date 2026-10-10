"""Git helpers: changed-line ranges and per-line blame."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _changed_lines_since(root: Path, since: str) -> dict[str, set[int]]:
    """Return {file_rel: {changed_line_numbers}} for files modified since git ref.

    Empty dict if git is unavailable, ref is invalid, or any error occurs.
    Uses git diff --unified=0 against the current working tree (includes uncommitted).
    """
    try:
        r = subprocess.run(
            ["git", "diff", "--unified=0", since, "--"],
            cwd=str(root), capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return {}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}

    out: dict[str, set[int]] = {}
    cur_file = ""
    for line in r.stdout.splitlines():
        if line.startswith("+++ b/"):
            cur_file = line[6:]
            out.setdefault(cur_file, set())
        elif line.startswith("+++ /dev/null"):
            cur_file = ""  # file deletion; skip
        elif line.startswith("@@ ") and cur_file:
            # @@ -X,Y +A,B @@  → we want lines A through A+B-1 on the new side
            try:
                plus = line.split("+", 1)[1].split(" ", 1)[0]
                if "," in plus:
                    start_s, count_s = plus.split(",")
                    start, count = int(start_s), int(count_s)
                else:
                    start, count = int(plus), 1
                if count > 0:
                    out[cur_file].update(range(start, start + count))
            except (IndexError, ValueError):
                continue
    return out


def _filter_by_changed_lines(
    symbols: list[dict], changed: dict[str, set[int]]
) -> list[dict]:
    """Keep symbols whose [start_line, end_line] overlaps the changed line set for their file."""
    out: list[dict] = []
    for s in symbols:
        file_changes = changed.get(s["file"])
        if not file_changes:
            continue
        for ln in range(s["start_line"], s["end_line"] + 1):
            if ln in file_changes:
                out.append(s)
                break
    return out


def _blame_file(path: Path, root: Path) -> dict[int, tuple[str, int]]:
    """Return {line_number: (commit_sha, author_unix_ts)} for every line in path.

    One `git blame --line-porcelain` subprocess per file. Returns empty dict if
    git is absent, file is untracked, or any error occurs (callers should treat
    missing entries as "unknown last_modified" and leave the symbol fields at default).
    """
    try:
        rel = str(path.relative_to(root))
        r = subprocess.run(
            ["git", "blame", "--line-porcelain", "--", rel],
            cwd=str(root), capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return {}
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return {}

    out: dict[int, tuple[str, int]] = {}
    cur_sha = ""
    cur_ts = 0
    for raw in r.stdout.splitlines():
        if not raw:
            continue
        if raw.startswith("\t"):
            # content line — nothing to do, just consumes the chunk
            continue
        parts = raw.split(" ", 3)
        first = parts[0]
        # header line: <sha> <orig_line> <final_line> [<count>]
        # 40-char hex sha, followed by digits in parts[1..]
        if len(first) == 40 and all(c in "0123456789abcdef" for c in first):
            cur_sha = first
            try:
                final_line = int(parts[2])
                out[final_line] = (cur_sha, cur_ts)
            except (IndexError, ValueError):
                pass
        elif first == "author-time" and len(parts) >= 2:
            try:
                cur_ts = int(parts[1])
                # backfill the most-recent header (header came before metadata)
                if out:
                    last_line = next(reversed(out))
                    sha_at_last = out[last_line][0]
                    if sha_at_last == cur_sha:
                        out[last_line] = (sha_at_last, cur_ts)
            except (IndexError, ValueError):
                pass
    return out


def _symbol_last_modified(blame: dict[int, tuple[str, int]], start: int, end: int) -> tuple[str, int]:
    """Pick the most recent (sha, ts) across the symbol's line range."""
    best_ts = 0
    best_sha = ""
    for ln in range(start, end + 1):
        entry = blame.get(ln)
        if entry and entry[1] > best_ts:
            best_sha, best_ts = entry
    return best_sha, best_ts

