from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from booster.learner import mine, write_to_claude_md, _BLOCK_START, _BLOCK_END


def _seed_db(root: Path, rows: list[tuple]) -> None:
    db = root / ".booster" / "stats.db"
    db.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reads "
        "(id INTEGER PRIMARY KEY, ts TEXT, file TEXT, full_tokens INTEGER, slice_tokens INTEGER, task TEXT DEFAULT '')"
    )
    conn.executemany("INSERT INTO reads (ts, file, full_tokens, slice_tokens) VALUES (?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_mine_empty_db(tmp_path):
    (tmp_path / ".booster").mkdir()
    db = tmp_path / ".booster" / "stats.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE reads (id INTEGER PRIMARY KEY, ts TEXT, file TEXT, full_tokens INTEGER, slice_tokens INTEGER, task TEXT DEFAULT '')")
    conn.commit()
    conn.close()
    assert mine(tmp_path) == []


def test_mine_hot_file(tmp_path):
    rows = [("2026-06-15", "app/auth.py", 1000, 200)] * 5
    _seed_db(tmp_path, rows)
    rules = mine(tmp_path)
    assert any("auth.py" in r for r in rules)


def test_mine_low_savings_file(tmp_path):
    # slice_tokens close to full_tokens = resists slicing
    rows = [("2026-06-15", "app/big.py", 1000, 900)] * 4
    _seed_db(tmp_path, rows)
    rules = mine(tmp_path)
    assert any("big.py" in r for r in rules)


def test_write_creates_block(tmp_path):
    rules = ["always read auth.py first", "use smart_read on config.py"]
    msg = write_to_claude_md(tmp_path, rules)
    content = (tmp_path / "CLAUDE.md").read_text()
    assert _BLOCK_START in content
    assert _BLOCK_END in content
    assert "auth.py" in content
    assert "Wrote 2 rule(s)" in msg


def test_write_replaces_existing_block(tmp_path):
    md = tmp_path / "CLAUDE.md"
    md.write_text(f"{_BLOCK_START}\n## old\n- old rule\n{_BLOCK_END}\n")
    write_to_claude_md(tmp_path, ["new rule"])
    content = md.read_text()
    assert "old rule" not in content
    assert "new rule" in content
    assert content.count(_BLOCK_START) == 1


def test_write_empty_rules(tmp_path):
    msg = write_to_claude_md(tmp_path, [])
    assert "Nothing learned" in msg
    assert not (tmp_path / "CLAUDE.md").exists()
