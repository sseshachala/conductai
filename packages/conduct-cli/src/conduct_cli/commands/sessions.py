"""`conduct sessions`: local Claude Code / Codex session table and TUI."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from conduct_cli import api
from conduct_cli.commands.shared import (
    BLUE,
    BOLD,
    CYAN,
    GRAY,
    GREEN,
    RED,
    RESET,
    YELLOW,
    _load_config,
)


_CLAUDE_SESSIONS = Path.home() / ".claude" / "sessions"
_CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
_CODEX_SESSIONS  = Path.home() / ".codex" / "sessions"

# Context window limits by model prefix (tokens)
_CTX_LIMITS = {
    "claude-opus-4":    200_000,
    "claude-sonnet-4":  200_000,
    "claude-haiku-4":   200_000,
    "claude-opus-3":    200_000,
    "claude-sonnet-3":  200_000,
    "claude-haiku-3":   200_000,
}

def _ctx_limit(model: str) -> int:
    for prefix, limit in _CTX_LIMITS.items():
        if model.startswith(prefix):
            return limit
    return 200_000


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _session_stats(session_id: str, project_dir: Path) -> dict:
    """Parse the tail of a session JSONL for model, token counts, and turn count."""
    jsonl = project_dir / f"{session_id}.jsonl"
    if not jsonl.exists():
        return {}

    model = ""
    total_input = 0
    total_output = 0
    turns = 0
    last_usage: dict = {}

    try:
        lines = jsonl.read_bytes().splitlines()
        # Scan last 300 lines for efficiency
        for raw in lines[-300:]:
            try:
                entry = json.loads(raw)
            except Exception:
                continue
            msg = entry.get("message", {})
            if not isinstance(msg, dict):
                continue
            if msg.get("role") == "assistant":
                turns += 1
                if msg.get("model"):
                    model = msg["model"]
                usage = msg.get("usage", {})
                if usage:
                    last_usage = usage
            if msg.get("role") == "assistant" and "usage" in msg:
                u = msg["usage"]
                total_input  += u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                total_output += u.get("output_tokens", 0)
    except Exception:
        pass

    cache_read = last_usage.get("cache_read_input_tokens", 0)
    fresh_in   = last_usage.get("input_tokens", 0)
    ctx_tokens = cache_read + fresh_in
    limit      = _ctx_limit(model)
    ctx_pct    = round(ctx_tokens / limit * 100) if limit else 0

    return {
        "model":      model,
        "turns":      turns,
        "ctx_tokens": ctx_tokens,
        "ctx_pct":    ctx_pct,
        "total_in":   total_input,
        "total_out":  total_output,
    }


def _codex_running_cwds() -> set[str]:
    """Return cwds of any running codex processes via /proc or ps."""
    cwds: set[str] = set()
    try:
        import subprocess as _sp
        out = _sp.run(["ps", "aux"], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if "codex" in line and "grep" not in line:
                # Extract cwd from lsof for each codex PID
                parts = line.split()
                if parts:
                    pid = parts[1]
                    try:
                        r = _sp.run(["lsof", "-p", pid, "-a", "-d", "cwd", "-Fn"],
                                    capture_output=True, text=True, timeout=1)
                        for l in r.stdout.splitlines():
                            if l.startswith("n"):
                                cwds.add(l[1:])
                    except Exception:
                        pass
    except Exception:
        pass
    return cwds


def _codex_session_stats(jsonl_path: Path) -> dict:
    """Parse a Codex JSONL session file for model, ctx window, and turn count."""
    model = ""
    ctx_limit = 0
    turns = 0
    cwd = ""
    try:
        for raw in jsonl_path.read_bytes().splitlines():
            try:
                entry = json.loads(raw)
            except Exception:
                continue
            t = entry.get("type", "")
            p = entry.get("payload", {})
            if t == "session_meta":
                cwd = p.get("cwd", "")
            if t == "turn_context":
                model = p.get("model", model)
                turns += 1
            if t == "event_msg" and not ctx_limit:
                ctx_limit = p.get("model_context_window", 0)
    except Exception:
        pass

    return {"model": model, "ctx_limit": ctx_limit, "turns": turns, "cwd": cwd}


def _load_codex_sessions(active_cwds: set[str]) -> list[dict]:
    """Find recent Codex sessions from ~/.codex/sessions/YYYY/MM/DD/."""
    if not _CODEX_SESSIONS.exists():
        return []

    guard_on  = (Path.home() / ".conduct" / "config.json").exists()

    rows = []
    # Walk the last 2 days of session dirs
    from datetime import datetime, timedelta
    today = datetime.now()
    date_dirs = []
    for delta in (0, 1):
        d = today - timedelta(days=delta)
        date_dirs.append(_CODEX_SESSIONS / str(d.year) / f"{d.month:02d}" / f"{d.day:02d}")

    seen: set[str] = set()
    for date_dir in date_dirs:
        if not date_dir.exists():
            continue
        for f in sorted(date_dir.iterdir(), reverse=True):
            if not f.suffix == ".jsonl":
                continue
            session_id = f.stem.split("-", 1)[-1] if "-" in f.stem else f.stem
            if session_id in seen:
                continue
            seen.add(session_id)

            stats = _codex_session_stats(f)
            cwd   = stats.get("cwd", "")
            alive = cwd in active_cwds

            ctx_limit  = stats.get("ctx_limit", 0) or 200_000
            # Codex doesn't expose per-turn token counts in JSONL — show turns only
            ctx_pct    = 0

            rows.append({
                "pid":        "—",
                "session_id": session_id[:8],
                "project":    Path(cwd).name if cwd else "—",
                "cwd":        cwd,
                "model":      stats.get("model", "—"),
                "turns":      stats.get("turns", 0),
                "ctx_pct":    ctx_pct,
                "ctx_tokens": 0,
                "total_in":   0,
                "total_out":  0,
                "guard":      guard_on,
                "alive":      alive,
                "kind":       "codex",
                "started_at": int(f.stat().st_mtime * 1000),
                "ai":         "CD",
            })

    return rows


def _load_sessions() -> list[dict]:
    """Read ~/.claude/sessions/*.json and join with JSONL stats."""
    if not _CLAUDE_SESSIONS.exists():
        return []

    guard_on  = (Path.home() / ".conduct" / "config.json").exists()

    rows = []
    seen_sessions: set[str] = set()
    for f in sorted(_CLAUDE_SESSIONS.iterdir()):
        if not f.suffix == ".json":
            continue
        try:
            s = json.loads(f.read_text())
        except Exception:
            continue

        pid        = s.get("pid", 0)
        session_id = s.get("sessionId", "")
        cwd        = s.get("cwd", "")
        started_at = s.get("startedAt", 0)
        kind       = s.get("kind", "")

        if session_id in seen_sessions:
            continue
        seen_sessions.add(session_id)

        alive = _is_alive(pid)

        # Claude names project dirs by replacing / with - (keeping leading -)
        project_key = cwd.replace("/", "-").replace("\\", "-")
        project_dir = _CLAUDE_PROJECTS / project_key

        stats = _session_stats(session_id, project_dir) if project_dir.exists() else {}

        rows.append({
            "pid":        pid,
            "session_id": session_id[:8],
            "project":    Path(cwd).name if cwd else "—",
            "cwd":        cwd,
            "model":      stats.get("model", "—"),
            "turns":      stats.get("turns", 0),
            "ctx_pct":    stats.get("ctx_pct", 0),
            "ctx_tokens": stats.get("ctx_tokens", 0),
            "total_in":   stats.get("total_in", 0),
            "total_out":  stats.get("total_out", 0),
            "guard":      guard_on,
            "alive":      alive,
            "kind":       kind,
            "started_at": started_at,
            "ai":         "CC",
        })

    # Merge Codex sessions
    active_cwds = _codex_running_cwds()
    rows += _load_codex_sessions(active_cwds)

    return sorted(rows, key=lambda r: r["started_at"], reverse=True)


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def _ctx_bar(pct: int, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    bar    = "█" * filled + "░" * (width - filled)
    color  = RED if pct >= 80 else YELLOW if pct >= 60 else GREEN
    return f"{color}{bar}{RESET} {pct}%"


def _render_table(rows: list[dict]) -> str:
    if not rows:
        return f"\n{GRAY}  No Claude Code sessions found.{RESET}\n"

    lines = []
    header = (
        f"  {BOLD}{'AI':<4} {'PROJECT':<18} {'SESSION':<10} {'MODEL':<18} "
        f"{'CTX':>14}   {'TOKENS IN':>10} {'TURNS':>6} {'GUARD':>6} {'STATUS':>8}{RESET}"
    )
    lines.append(header)
    lines.append("  " + "─" * 100)

    for r in rows:
        status_str  = f"{GREEN}active{RESET}" if r["alive"] else f"{GRAY}idle{RESET}"
        guard_str   = f"{GREEN}✓{RESET}" if r["guard"] else f"{GRAY}—{RESET}"
        model_short = r["model"].replace("claude-", "").replace("-20", " 20") if r["model"] not in ("—", "") else "—"
        ctx_display = _ctx_bar(r["ctx_pct"]) if r["ctx_pct"] else f"{GRAY}{'—':>14}{RESET}"
        tokens_str  = _fmt_tokens(r["ctx_tokens"]) if r["ctx_tokens"] else "—"
        ai_label    = r.get("ai", "CC")
        ai_color    = CYAN if ai_label == "CD" else BLUE

        lines.append(
            f"  {ai_color}{ai_label:<4}{RESET} {r['project']:<18} {r['session_id']:<10} {model_short:<18} "
            f"{ctx_display}   {tokens_str:>10} {r['turns']:>6} {guard_str:>6}   {status_str}"
        )

    lines.append("")
    return "\n".join(lines)


def _fetch_runs(cfg: dict) -> list[dict]:
    """Fetch recent runs from GET /runs."""
    server  = (cfg.get("server") or cfg.get("api_url") or "").rstrip("/")
    api_key = cfg.get("agent_token", "")
    ws_id   = cfg.get("workspace", "")
    if not all([server, api_key, ws_id]):
        return []
    try:
        hdrs = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        data = api.req("GET", f"{server}/runs?limit=15&workspace_id={ws_id}", hdrs)
        runs = data if isinstance(data, list) else data.get("runs", data.get("items", []))
        return runs[:15]
    except Exception:
        return []


def _fetch_guard_activity(cfg: dict) -> list[dict]:
    """Fetch recent Guard events grouped by developer."""
    server  = (cfg.get("server") or cfg.get("api_url") or "").rstrip("/")
    api_key = cfg.get("agent_token", "")
    ws_id   = cfg.get("workspace", "")
    if not all([server, api_key, ws_id]):
        return []
    try:
        hdrs = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        data = api.req("GET", f"{server}/guard/events?workspace_id={ws_id}&limit=200", hdrs)
        events = data if isinstance(data, list) else data.get("events", [])
        # Group by user_email
        devs: dict[str, dict] = {}
        for e in events:
            email   = e.get("user_email") or e.get("email") or "unknown"
            blocked = e.get("decision") == "block"
            tokens  = e.get("tokens_used") or e.get("tokens", 0) or 0
            if email not in devs:
                devs[email] = {"email": email, "calls": 0, "blocked": 0, "tokens": 0}
            devs[email]["calls"]   += 1
            devs[email]["blocked"] += int(blocked)
            devs[email]["tokens"]  += tokens
        return sorted(devs.values(), key=lambda d: d["calls"], reverse=True)
    except Exception:
        return []


def _render_tui(rows: list[dict]) -> None:
    """Full-screen TUI with live refresh. Uses rich.live if available, else ANSI loop."""

    cfg       = _load_config()
    def _build_rich_display(rows):
        from rich.table import Table
        from rich.panel import Panel
        from rich.columns import Columns
        from rich import box
        from rich.text import Text

        active   = sum(1 for r in rows if r["alive"])
        guard_on = sum(1 for r in rows if r["guard"])
        high_ctx = [r for r in rows if r["ctx_pct"] >= 60 and r["alive"]]

        # Main sessions table
        tbl = Table(box=box.ROUNDED, expand=True, show_header=True, header_style="bold white")
        tbl.add_column("AI",      width=4,  style="bold")
        tbl.add_column("Project", min_width=14)
        tbl.add_column("Session", width=10, style="dim")
        tbl.add_column("Model",   min_width=14)
        tbl.add_column("CTX",     width=16)
        tbl.add_column("Tokens",  width=10, justify="right")
        tbl.add_column("Turns",   width=6,  justify="right")
        tbl.add_column("Guard",   width=6,  justify="center")
        tbl.add_column("Status",  width=8)

        for r in rows:
            ai_text     = Text(r.get("ai", "CC"), style="bold cyan" if r.get("ai") == "CD" else "bold blue")
            status_text = Text("active", style="green") if r["alive"] else Text("idle", style="dim")
            guard_text  = Text("✓", style="green") if r["guard"] else Text("—", style="dim")
            model_short = r["model"].replace("claude-", "").replace("-20", " 20") if r["model"] not in ("—", "") else "—"

            pct = r["ctx_pct"]
            if pct:
                filled = round(pct / 100 * 10)
                bar    = "█" * filled + "░" * (10 - filled)
                color  = "red" if pct >= 80 else "yellow" if pct >= 60 else "green"
                ctx_text = Text(f"{bar} {pct}%", style=color)
            else:
                ctx_text = Text("—", style="dim")

            tbl.add_row(
                ai_text,
                r["project"],
                r["session_id"],
                model_short,
                ctx_text,
                _fmt_tokens(r["ctx_tokens"]) if r["ctx_tokens"] else "—",
                str(r["turns"]),
                guard_text,
                status_text,
            )

        # Summary header
        summary = f"[bold]{active}[/] active  ·  [bold]{guard_on}[/] with Guard  ·  [dim]refreshing every 5s — Ctrl+C to quit[/]"

        panels = [Panel(tbl, title="[bold blue]● My Sessions[/]", subtitle=summary, expand=True)]

        # Context pressure panel
        if high_ctx:
            warnings = "\n".join(
                f"[{'red' if r['ctx_pct'] >= 80 else 'yellow'}]{r['project']}[/]  "
                f"[dim]{r['session_id']}[/]  {r['ctx_pct']}% — consider /compact"
                for r in high_ctx
            )
            panels.append(Panel(warnings, title="[yellow bold]⚠ Context pressure[/]", expand=True))

        # Agent Runs panel
        run_data = _fetch_runs(cfg)
        runs_tbl = Table(box=box.SIMPLE, expand=True, show_header=True, header_style="bold white")
        runs_tbl.add_column("Agent",      min_width=22)
        runs_tbl.add_column("Status",     width=12)
        runs_tbl.add_column("Duration",   width=10, justify="right")
        runs_tbl.add_column("Project",    min_width=14)
        runs_tbl.add_column("Triggered",  width=12)

        if run_data:
            for r in run_data:
                status  = r.get("status", "")
                scolor  = {"running": "green", "succeeded": "dim green", "failed": "red",
                           "paused": "yellow", "pending": "cyan", "cancelled": "dim"}.get(status, "white")
                sicon   = {"running": "●", "succeeded": "✓", "failed": "✗",
                           "paused": "⏸", "pending": "○", "cancelled": "—"}.get(status, "?")
                # Duration — timestamps may be ISO strings or unix floats
                import datetime as _dt
                def _to_ts(val):
                    if not val:
                        return None
                    if isinstance(val, (int, float)):
                        return float(val)
                    try:
                        return _dt.datetime.fromisoformat(str(val).replace("Z", "+00:00")).timestamp()
                    except Exception:
                        return None
                created_ts = _to_ts(r.get("created_at") or r.get("started_at"))
                ended_ts   = _to_ts(r.get("completed_at") or r.get("finished_at"))
                if created_ts and ended_ts:
                    secs = int(ended_ts - created_ts)
                    dur  = f"{secs//60}:{secs%60:02d}"
                elif created_ts and status == "running":
                    secs = int(time.time() - created_ts)
                    dur  = f"{secs//60}:{secs%60:02d}"
                else:
                    dur = "—"
                agent_name   = r.get("workflow_name") or r.get("name") or "—"
                project_name = r.get("project_name") or r.get("project") or "—"
                trigger      = r.get("trigger_type") or r.get("triggered_by") or "manual"
                runs_tbl.add_row(
                    agent_name[:28],
                    Text(f"{sicon} {status}", style=scolor),
                    dur,
                    project_name[:18],
                    trigger[:12],
                )
        else:
            runs_tbl.add_row("[dim]No runs yet or not connected[/]", "", "", "", "")

        panels.append(Panel(runs_tbl, title="[bold green]▶ Agent Runs[/]", expand=True))

        # Team Activity panel (Guard)
        team_data = _fetch_guard_activity(cfg)
        team_tbl  = Table(box=box.SIMPLE, expand=True, show_header=True, header_style="bold white")
        team_tbl.add_column("Developer",  min_width=28)
        team_tbl.add_column("Calls",      width=8,  justify="right")
        team_tbl.add_column("Blocked",    width=8,  justify="right")
        team_tbl.add_column("Tokens",     width=10, justify="right")
        team_tbl.add_column("Guard",      width=7,  justify="center")

        if team_data:
            for d in team_data:
                blocked_text = Text(str(d["blocked"]), style="red bold" if d["blocked"] else "dim")
                guard_text   = Text("✓", style="green")
                team_tbl.add_row(
                    d["email"][:32],
                    str(d["calls"]),
                    blocked_text,
                    _fmt_tokens(d["tokens"]),
                    guard_text,
                )
        else:
            team_tbl.add_row("[dim]No team activity or not connected[/]", "", "", "", "")

        panels.append(Panel(team_tbl, title="[bold magenta]👥 Team Activity (Guard)[/]", expand=True))

        from rich.console import Group
        return Group(*panels)

    # Try rich.live first (works without raw TTY)
    try:
        from rich.live import Live
        from rich.console import Console
        console = Console()
        with Live(console=console, refresh_per_second=0.2, screen=True) as live:
            while True:
                live.update(_build_rich_display(_load_sessions()))
                time.sleep(5)
        return
    except KeyboardInterrupt:
        return
    except ImportError:
        pass  # fall through to ANSI loop

    # ANSI fallback — requires real TTY
    if not sys.stdin.isatty():
        print(f"{YELLOW}TUI requires a real terminal. Run directly in your shell, not via a subprocess.{RESET}")
        print(_render_table(rows))
        return

    import shutil, signal, select, tty, termios
    stop = False
    def _sig(s, f): nonlocal stop; stop = True
    signal.signal(signal.SIGINT, _sig)

    def _frame(rows):
        cols, _ = shutil.get_terminal_size((120, 40))
        title = " conduct sessions  (Ctrl+C or q to quit) "
        pad   = max(0, cols - len(title))
        active   = sum(1 for r in rows if r["alive"])
        guard_on = sum(1 for r in rows if r["guard"])
        out = [
            f"{BOLD}\033[44m{title}{' ' * pad}\033[0m",
            f"\n  {BOLD}{active}{RESET} active  ·  {BOLD}{guard_on}{RESET} with Guard  ·  refreshing every 5s\n",
            _render_table(rows),
        ]
        high = [r for r in rows if r["ctx_pct"] >= 60 and r["alive"]]
        if high:
            out.append(f"  {YELLOW}{BOLD}⚠ Context pressure{RESET}")
            for r in high:
                c = RED if r["ctx_pct"] >= 80 else YELLOW
                out.append(f"    {c}{r['project']}{RESET} ({r['session_id']}) {r['ctx_pct']}% — consider /compact")
        sys.stdout.write("\033[2J\033[H" + "\n".join(out))
        sys.stdout.flush()

    old = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        while not stop:
            _frame(_load_sessions())
            for _ in range(50):
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    if sys.stdin.read(1) in ("q", "Q"):
                        stop = True
                        break
                if stop:
                    break
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        sys.stdout.write("\033[2J\033[H")
        print("conduct sessions exited.")


def cmd_sessions(args):
    tui   = getattr(args, "tui", False)
    watch = getattr(args, "watch", False)

    if tui:
        _render_tui(_load_sessions())
        return

    if watch:
        try:
            import signal
            stop = False
            def _sig(s, f): nonlocal stop; stop = True
            signal.signal(signal.SIGINT, _sig)
            while not stop:
                sys.stdout.write("\033[2J\033[H")
                sys.stdout.flush()
                rows = _load_sessions()
                print(f"\n{BOLD}conduct sessions{RESET}  {GRAY}(Ctrl+C to stop · refreshing every 5s){RESET}")
                print(_render_table(rows))
                for _ in range(50):
                    time.sleep(0.1)
                    if stop: break
        except KeyboardInterrupt:
            pass
        return

    rows = _load_sessions()
    print(f"\n{BOLD}conduct sessions{RESET}")
    print(_render_table(rows))
