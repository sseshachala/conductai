"""booster learn — mine local stats + Guard run traces → CLAUDE.md rules.

Two data sources:
1. Local .booster/stats.db (always available)
2. Guard API failed runs (optional — needs CONDUCT_API_TOKEN + CONDUCT_API_URL)

Writes under a <!-- booster:learned:start/end --> block in CLAUDE.md so it
doesn't collide with the main booster init block.
"""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

_BLOCK_START = "<!-- booster:learned:start -->"
_BLOCK_END = "<!-- booster:learned:end -->"

# Thresholds
_MIN_READS = 3          # file must be read this many times to appear in suggestions
_LOW_SAVINGS = 0.40     # slice/full ratio above this = file resists smart_read
_MAX_RULES = 10         # cap rules written to avoid bloating CLAUDE.md


def mine(root: Path) -> list[str]:
    """Return list of learned rule strings. Empty list = nothing useful found."""
    rules: list[str] = []
    rules.extend(_mine_local(root))
    rules.extend(_mine_guard())
    return rules[:_MAX_RULES]


def write_to_claude_md(root: Path, rules: list[str]) -> str:
    """Upsert learned rules block in CLAUDE.md. Returns status message."""
    if not rules:
        return "Nothing learned yet — run more sessions first."

    block = _build_block(rules)
    claude_md = root / "CLAUDE.md"
    existing = claude_md.read_text() if claude_md.exists() else ""

    if _BLOCK_START in existing:
        # replace existing learned block
        start = existing.index(_BLOCK_START)
        end = existing.index(_BLOCK_END) + len(_BLOCK_END)
        updated = existing[:start] + block + existing[end:]
    else:
        sep = "\n\n" if existing and not existing.endswith("\n\n") else ""
        updated = existing + sep + block + "\n"

    claude_md.write_text(updated)
    return f"Wrote {len(rules)} rule(s) to CLAUDE.md"


# --- local mining ---

def _mine_local(root: Path) -> list[str]:
    db_path = root / ".booster" / "stats.db"
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    rules: list[str] = []

    # Hot files — read frequently → suggest reading early
    cur = conn.execute(
        """SELECT file, COUNT(*) as reads, AVG(slice_tokens * 1.0 / NULLIF(full_tokens, 0)) as ratio
           FROM reads GROUP BY file HAVING reads >= ? ORDER BY reads DESC LIMIT 5""",
        (_MIN_READS,),
    )
    for file, reads, ratio in cur.fetchall():
        name = Path(file).name
        if ratio is not None and ratio > _LOW_SAVINGS:
            rules.append(
                f"Always use `smart_read` with a specific task description for `{name}` "
                f"— full file resists slicing (read {reads}×, {int(ratio*100)}% of tokens sent)"
            )
        else:
            rules.append(
                f"`{name}` is a hot file (read {reads}×) — consider pinning it in CLAUDE.md context"
            )

    # Top token-saving files → reinforce using smart_read
    cur = conn.execute(
        """SELECT file, SUM(full_tokens - slice_tokens) as saved
           FROM reads GROUP BY file ORDER BY saved DESC LIMIT 3"""
    )
    for file, saved in cur.fetchall():
        if saved and saved > 500:
            name = Path(file).name
            rules.append(
                f"`smart_read` saves ~{saved:,} tokens on `{name}` — always prefer it over full reads"
            )

    conn.close()
    return rules


# --- Guard API mining ---

def _mine_guard() -> list[str]:
    token = os.environ.get("CONDUCT_API_TOKEN") or os.environ.get("CONDUCT_TOKEN")
    base = os.environ.get("CONDUCT_API_URL", "https://api.conductai.ai")
    workspace = os.environ.get("CONDUCT_WORKSPACE_ID")

    if not token or not workspace:
        return []

    try:
        url = f"{base}/api/workspaces/{workspace}/runs?status=failed&limit=20"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, KeyError):
        return []

    runs = data if isinstance(data, list) else data.get("runs", [])
    rules: list[str] = []
    turn_limit_count = 0
    error_files: dict[str, int] = {}

    for run in runs:
        error = (run.get("error") or "").lower()
        if "turn limit" in error or "max_turns" in error:
            turn_limit_count += 1
        # extract file mentions from error messages
        for word in (run.get("error") or "").split():
            if "/" in word and "." in word:
                error_files[word] = error_files.get(word, 0) + 1

    if turn_limit_count >= 2:
        rules.append(
            f"{turn_limit_count} recent runs hit turn limits — "
            "use `route_model` at task start to ensure opus is selected for complex tasks"
        )

    for path, count in sorted(error_files.items(), key=lambda x: -x[1])[:2]:
        if count >= 2:
            rules.append(
                f"`{Path(path).name}` appeared in {count} failed run errors — "
                "read it early with `smart_read` before making changes"
            )

    return rules


# --- block builder ---

def _build_block(rules: list[str]) -> str:
    lines = [_BLOCK_START, "## Learned from booster (auto-generated — do not edit)\n"]
    for rule in rules:
        lines.append(f"- {rule}")
    lines.append(f"\n{_BLOCK_END}")
    return "\n".join(lines)
