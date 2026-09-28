"""Guard CLI: booster."""
from __future__ import annotations

from pathlib import Path
import json

from . import shared as _guard_shared


def _ensure_booster(root: Path) -> None:
    """Auto-init and background-index booster if installed but not yet set up."""
    import shutil
    import subprocess
    import sys

    if not shutil.which("booster"):
        if sys.version_info < (3, 10):
            print(
                f"  {_guard_shared.GRAY}Agent Booster:{_guard_shared.RESET} requires Python 3.10+ "
                f"(you have {sys.version_info.major}.{sys.version_info.minor}). "
                f"Upgrade Python then: pip install 'conduct-cli[booster]'"
            )
            return
        print(f"  {_guard_shared.GRAY}Agent Booster:{_guard_shared.RESET} installing…")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "conduct-cli[booster]"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            print(f"  {_guard_shared.RED}Agent Booster:{_guard_shared.RESET} install failed — {r.stderr.strip()[:120]}")
            return
        print(f"  {_guard_shared.GREEN}Agent Booster:{_guard_shared.RESET} installed")
        if not shutil.which("booster"):
            print(f"  {_guard_shared.YELLOW}Agent Booster:{_guard_shared.RESET} 'booster' not on PATH yet — restart shell or re-run sync")
            return

    # Upgrade booster to latest in background (non-blocking)
    # Use [booster] extra only on Python 3.10+ — agent-booster requires 3.10+
    _pkg = "conduct-cli[booster]" if sys.version_info >= (3, 10) else "conduct-cli"
    try:
        subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", _pkg],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

    db_path = root / ".booster" / "symbols.db"
    hooks_path = root / ".claude" / "hooks" / "booster-gate.py"

    # Init (writes hook scripts + wires settings.json) — fast, idempotent
    if not hooks_path.exists():
        try:
            r = subprocess.run(
                ["booster", "init", "claude", "--yes"],
                capture_output=True, timeout=15, cwd=str(root),
            )
            if r.returncode == 0:
                print(f"  {_guard_shared.GREEN}Agent Booster:{_guard_shared.RESET} hooks installed")
            else:
                print(f"  {_guard_shared.GRAY}Agent Booster:{_guard_shared.RESET} init failed — {r.stderr.strip()[:120]}")
                return
        except Exception:
            return

    # Index in background — may take 10-60s on large repos, never blocks sync
    if not db_path.exists():
        try:
            subprocess.Popen(
                ["booster", "index", "--embed"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd=str(root),
            )
            print(f"  {_guard_shared.GREEN}Agent Booster:{_guard_shared.RESET} indexing in background (Read/Grep intercept active shortly)")
        except Exception:
            pass
    else:
        symbols_count = 0
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            symbols_count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            conn.close()
        except Exception:
            pass
        print(f"  {_guard_shared.GREEN}Agent Booster:{_guard_shared.RESET} {symbols_count} symbols indexed — Read/Grep intercept active")

    # Keep BOOSTER_SECRET in .mcp.json in sync with ~/.booster/.secret
    secret_file = Path.home() / ".booster" / ".secret"
    mcp_json = root / ".mcp.json"
    if secret_file.exists() and mcp_json.exists():
        try:
            expected = secret_file.read_text().strip()
            data = json.loads(mcp_json.read_text())
            server = data.get("mcpServers", {}).get("agent-booster", {})
            if server.get("env", {}).get("BOOSTER_SECRET") != expected:
                server.setdefault("env", {})["BOOSTER_SECRET"] = expected
                mcp_json.write_text(json.dumps(data, indent=2) + "\n")
                print(f"  {_guard_shared.GREEN}Agent Booster:{_guard_shared.RESET} refreshed BOOSTER_SECRET in .mcp.json")
        except Exception:
            pass


def cmd_guard_booster_status(args):
    """Show whether booster is intercepting Read/Grep in this project."""
    import shutil, sqlite3, subprocess

    root = Path.cwd()
    db_path    = root / ".booster" / "symbols.db"
    hooks_path = root / ".claude" / "hooks" / "booster-gate.py"
    settings_p = root / ".claude" / "settings.json"

    booster_bin = shutil.which("booster")
    print(f"\n{_guard_shared.BOLD}Agent Booster intercept status — {root.name}{_guard_shared.RESET}\n")

    # 1. Binary
    if booster_bin:
        print(f"  {_guard_shared.GREEN}✓{_guard_shared.RESET} booster installed  ({booster_bin})")
    else:
        print(f"  {_guard_shared.RED}✗{_guard_shared.RESET} booster not found on PATH — run: pip install agent-booster")
        return

    # 2. Hook scripts written
    if hooks_path.exists():
        print(f"  {_guard_shared.GREEN}✓{_guard_shared.RESET} hook scripts present  (.claude/hooks/booster-gate.py)")
    else:
        print(f"  {_guard_shared.RED}✗{_guard_shared.RESET} hook scripts missing — run: conduct guard sync")

    # 3. Wired in settings.json
    wired = False
    if settings_p.exists():
        import json as _json
        s = _json.loads(settings_p.read_text())
        for h in s.get("hooks", {}).get("PreToolUse", []):
            if h.get("matcher") == "Read":
                wired = True
                break
    if wired:
        print(f"  {_guard_shared.GREEN}✓{_guard_shared.RESET} Read hook wired in .claude/settings.json")
    else:
        print(f"  {_guard_shared.RED}✗{_guard_shared.RESET} Read hook NOT in .claude/settings.json — run: conduct guard sync")

    # 4. Index
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            files = conn.execute("SELECT COUNT(DISTINCT file) FROM symbols").fetchone()[0]
            conn.close()
            print(f"  {_guard_shared.GREEN}✓{_guard_shared.RESET} symbols.db  — {count} symbols across {files} files")
        except Exception:
            print(f"  {_guard_shared.YELLOW}?{_guard_shared.RESET} symbols.db exists but could not be read")
    else:
        print(f"  {_guard_shared.RED}✗{_guard_shared.RESET} symbols.db missing — Read calls fall through unintercepted")
        print(f"       run: booster index --embed  (or: conduct guard sync to trigger it)")
        return

    # 5. Live intercept test — try reading a known file and check if smart-read fires
    print(f"\n  {_guard_shared.BOLD}Live intercept test:{_guard_shared.RESET}")
    if not hooks_path.exists():
        print(f"  {_guard_shared.YELLOW}~{_guard_shared.RESET} Skipped — hook script not present")
        print()
        return
    try:
        import tempfile, json as _json
        # Pick the first indexed file
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT file FROM symbols LIMIT 1").fetchone()
        conn.close()
        if row:
            # Prefer a .py/.ts file — more likely to have symbols and trigger smart-read
            conn = sqlite3.connect(str(db_path))
            src = conn.execute(
                "SELECT file FROM symbols WHERE file LIKE '%.py' OR file LIKE '%.ts' LIMIT 1"
            ).fetchone() or row
            conn.close()
            test_file = str(root / src[0])
            payload = _json.dumps({"tool_name": "Read", "tool_input": {"file_path": test_file}})
            r = subprocess.run(
                ["python3", str(hooks_path)],
                input=payload, capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 2:
                lines = r.stdout.strip().splitlines()
                print(f"  {_guard_shared.GREEN}✓{_guard_shared.RESET} Read intercepted → smart-read fired ({len(lines)} lines returned)")
                print(f"    tested on: {row[0]}")
            elif r.returncode == 0:
                print(f"  {_guard_shared.YELLOW}~{_guard_shared.RESET} Hook ran but passed through (file may not have symbols)")
            else:
                print(f"  {_guard_shared.RED}✗{_guard_shared.RESET} Hook errored (exit {r.returncode})")
    except Exception as e:
        print(f"  {_guard_shared.YELLOW}?{_guard_shared.RESET} Could not run live test: {e}")

    print()
