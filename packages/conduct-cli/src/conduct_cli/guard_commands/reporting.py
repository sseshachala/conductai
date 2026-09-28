"""Guard CLI: reporting."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sys
import time
import urllib.error
import urllib.request

from . import hooks as _guard_hooks
from . import policy as _guard_policy
from . import shared as _guard_shared


def _report_savings(cfg: dict, base_url: str, agent_token: str = "") -> None:
    import subprocess

    rtk_data = {}
    booster_data = {}

    # Read RTK savings — rtk gain -f json nests under "summary" key
    try:
        r = subprocess.run(["rtk", "gain", "-f", "json"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            raw = json.loads(r.stdout)
            summary = raw.get("summary", raw)
            rtk_data = {
                "saved_tokens": summary.get("total_saved", 0),
                "savings_pct": summary.get("avg_savings_pct", 0.0),
                "total_commands": summary.get("total_commands", 0),
            }
    except Exception:
        pass

    # Read Agent Booster savings
    try:
        r = subprocess.run(["booster", "gain", "-f", "json"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            raw = json.loads(r.stdout)
            booster_data = {
                "saved_tokens": raw.get("saved_tokens", 0),
                "savings_pct": raw.get("savings_pct", 0.0),
                "total_reads": raw.get("total_reads", 0),
                "crusher": raw.get("crusher", {}),
                "cache_align": raw.get("cache_align", {}),
            }
    except Exception:
        pass

    # If neither tool returned data, skip silently
    if not rtk_data and not booster_data:
        return

    # Load baseline to compute period_start
    baseline_path = _guard_shared.GUARD_DIR / "savings_baseline.json"
    period_start = None
    try:
        if baseline_path.exists():
            baseline = json.loads(baseline_path.read_text())
            period_start = baseline.get("recorded_at")
    except Exception:
        pass

    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "workspace_id": cfg.get("workspace_id", ""),
        "member_email": cfg.get("user_email", ""),
        "rtk": rtk_data,
        "booster": booster_data,
        "period_start": period_start,
        "period_end": now_iso,
    }

    try:
        agent_token_evt = cfg.get("agent_token", "") or agent_token
        headers = {"Content-Type": "application/json"}
        if agent_token_evt:
            headers["Authorization"] = f"Bearer {agent_token_evt}"
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{base_url}/guard/savings",
            data=data,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        # Save baseline for next diff
        baseline_path.write_text(json.dumps({"recorded_at": now_iso, "rtk": rtk_data, "booster": booster_data}))
        print(f"  {_guard_shared.GREEN}Savings reported{_guard_shared.RESET}")
    except Exception:
        pass  # Never fail sync because savings POST failed

    # Push booster symbol index to team workspace (best-effort)
    try:
        r = subprocess.run(["booster", "index-push"], capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            print(f"  {_guard_shared.GREEN}Booster index:{_guard_shared.RESET} {r.stdout.strip()}")
    except Exception:
        pass


def cmd_guard_replay_events(args):
    """Requeue retained hook events after the authenticated ingest rollout."""
    if args.limit is not None and args.limit < 1:
        print(f"{_guard_shared.RED}--limit must be at least 1.{_guard_shared.RESET}")
        sys.exit(2)
    cfg = _guard_shared._require_guard_config()
    if not cfg.get("agent_token"):
        print(f"{_guard_shared.RED}No Agent Identity token found. Run `conduct login` first.{_guard_shared.RESET}")
        sys.exit(1)

    from conduct_cli.hooks.base import (
        JOURNAL_DEAD_DIR,
        ensure_drain_daemon,
        requeue_dead_letters,
    )

    available = len(list(JOURNAL_DEAD_DIR.glob("*.json"))) if JOURNAL_DEAD_DIR.exists() else 0
    selected = min(available, args.limit) if args.limit is not None else available
    if args.dry_run:
        print(f"{selected} of {available} dead-letter event(s) ready to replay")
        return
    moved = requeue_dead_letters(limit=args.limit)
    if moved:
        ensure_drain_daemon(_guard_shared.GUARD_DIR / "hook.py")
    print(f"Requeued {moved} dead-letter event(s)")


def cmd_guard_status(args):
    cfg          = _guard_shared._require_guard_config()
    workspace_id = cfg.get("workspace_id")
    user_email   = cfg.get("user_email", "")
    agent_token  = cfg.get("agent_token", "")
    base_url     = _guard_shared._api_url(cfg)

    # Auto-refresh user_email + clerk_user_id into config if missing
    if (not user_email or not cfg.get("clerk_user_id")) and agent_token:
        try:
            installed = _guard_shared._req("GET", f"{base_url}/guard/config/installed", token=agent_token or None)
            fetched_email = installed.get("user_email") or ""
            fetched_clerk = installed.get("clerk_user_id") or ""
            if fetched_email:
                cfg["user_email"] = fetched_email
                user_email = fetched_email
            if fetched_clerk:
                cfg["clerk_user_id"] = fetched_clerk
            _guard_shared._save_guard_config(cfg)
            # Rewrite hook script so future events carry the email
            hook_path = _guard_shared.GUARD_DIR / "hook.py"
            _guard_hooks._write_hook(hook_path)
        except Exception:
            pass

    # Load local policy for rule count
    rule_count = len(_guard_policy._load_policy().get("rules", []))

    # Fetch today's spend
    spend = {}
    try:
        spend = _guard_shared._req(
            "GET",
            f"{base_url}/guard/spend?workspace_id={workspace_id}",
            token=agent_token or None,
        )
    except SystemExit:
        pass

    # Fetch recent violations (today)
    today_iso = datetime.now(tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    events: list = []
    try:
        events = _guard_shared._req(
            "GET",
            (
                f"{base_url}/guard/events"
                f"?workspace_id={workspace_id}"
                f"&user_email={user_email}"
                f"&since={today_iso}"
                f"&limit=20"
            ),
            token=agent_token or None,
        )
        if not isinstance(events, list):
            events = events.get("events", [])
    except SystemExit:
        pass

    violations = [e for e in events if e.get("decision") == "blocked"]

    # Format spend figures
    proxy_sessions  = spend.get("sessions", 0)
    hook_sessions   = spend.get("hook_sessions", 0)
    tokens_used     = spend.get("tokens_used", 0)
    token_saved_pct = spend.get("token_saved_pct", 0)
    cost            = spend.get("cost_usd", 0.0)
    cost_saved      = spend.get("cost_saved_usd", 0.0)

    viol_summary = ""
    if violations:
        rule_names = ", ".join(v.get("rule_id") or v.get("rule", "unknown") for v in violations[:3])
        viol_summary = f"  ({rule_names} — blocked)"

    session_str = f"{proxy_sessions} proxy  ·  {hook_sessions} direct"

    # Drain daemon health
    try:
        from conduct_cli.hooks.base import drain_daemon_status
        d_status, d_pid = drain_daemon_status()
    except Exception:
        d_status, d_pid = "unknown", None

    if d_status == "running":
        daemon_line = f"{_guard_shared.GREEN}running{_guard_shared.RESET} (pid {d_pid})"
    elif d_status == "stale":
        daemon_line = f"{_guard_shared.YELLOW}stale{_guard_shared.RESET} (pid {d_pid}, not flushing — will restart on next tool call)"
    else:
        daemon_line = f"{_guard_shared.RED}not running{_guard_shared.RESET} — will start on next tool call"

    journal_dir = Path.home() / ".conduct" / "journal"
    queued_events = len(list(journal_dir.glob("*.json"))) if journal_dir.exists() else 0
    dead_events = len(list((journal_dir / "dead-letter").glob("*.json"))) if (journal_dir / "dead-letter").exists() else 0
    heartbeat_path = Path.home() / ".conduct" / "hook-heartbeat.json"
    heartbeat_line = "never observed"
    try:
        heartbeat = json.loads(heartbeat_path.read_text())
        age = max(0, int(time.time() - float(heartbeat["ts"])))
        heartbeat_line = f"{heartbeat.get('event', 'hook')} · {age}s ago"
    except Exception:
        pass

    # Proxy coverage — check active env vars in this shell
    _env           = os.environ
    def _conduct_proxy_url(value: str) -> bool:
        return "api.conductai.ai" in value and ("/gateway/v1" in value or "/proxy" in value)
    anthropic_ok   = _conduct_proxy_url(_env.get("ANTHROPIC_BASE_URL", ""))
    openai_ok      = _conduct_proxy_url(_env.get("OPENAI_BASE_URL", ""))
    perplexity_ok  = _conduct_proxy_url(_env.get("PERPLEXITY_BASE_URL", ""))
    env_file_exists = (Path.home() / ".conduct" / "env").exists()

    def _cov(ok: bool, name: str) -> str:
        return f"{_guard_shared.GREEN}{name}{_guard_shared.RESET}" if ok else f"{_guard_shared.YELLOW}{name}{_guard_shared.RESET}"

    covered   = [n for n, ok in [("Anthropic", anthropic_ok), ("OpenAI", openai_ok), ("Perplexity", perplexity_ok)] if ok]
    uncovered = [n for n, ok in [("Anthropic", anthropic_ok), ("OpenAI", openai_ok), ("Perplexity", perplexity_ok)] if not ok]

    if covered and not uncovered:
        proxy_line = f"{_guard_shared.GREEN}active{_guard_shared.RESET} — {', '.join(covered)} routed through Guard proxy"
    elif covered:
        proxy_line = f"{_guard_shared.YELLOW}partial{_guard_shared.RESET} — {', '.join(covered)} covered · {', '.join(uncovered)} NOT intercepted"
    elif env_file_exists:
        proxy_line = f"{_guard_shared.YELLOW}inactive{_guard_shared.RESET} — ~/.conduct/env exists but not sourced in this shell. Run: {_guard_shared.BOLD}. ~/.conduct/env{_guard_shared.RESET}"
    else:
        proxy_line = f"{_guard_shared.RED}not configured{_guard_shared.RESET} — run: {_guard_shared.BOLD}conduct guard sync{_guard_shared.RESET}"

    print(f"\n{_guard_shared.BOLD}Guard status{_guard_shared.RESET} — {user_email}")
    _active_cfg = _guard_shared._load_guard_config()
    if _active_cfg.get("current_goal_id"):
        print(f"  Active goal: {_guard_shared.CYAN}{_active_cfg.get('current_goal_name', 'unnamed')}{_guard_shared.RESET}  ({_active_cfg['current_goal_id'][:8]}...)")
    print(f"{rule_count} polic{'y' if rule_count == 1 else 'ies'} active")
    print()
    print(f"Proxy coverage: {proxy_line}")
    print(f"Drain daemon:   {daemon_line}")
    print(f"Event journal:  {queued_events} queued · {dead_events} dead-letter")
    print(f"Hook heartbeat: {heartbeat_line}")
    print()
    print(f"Today:")
    print(f"  Sessions: {session_str}")
    print(f"  Tokens used: {tokens_used:,}  (saved {token_saved_pct}% via optimization)")
    print(f"  Cost: ${cost:.2f}  (saved ${cost_saved:.2f})")
    print(f"  Violations: {len(violations)}{viol_summary}")
    print()


def cmd_guard_savings(args):
    cfg          = _guard_shared._require_guard_config()
    workspace_id = cfg.get("workspace_id")
    agent_token  = cfg.get("agent_token", "")
    base_url     = _guard_shared._api_url(cfg)

    try:
        data = _guard_shared._req(
            "GET",
            f"{base_url}/guard/savings/team-summary?workspace_id={workspace_id}",
            token=agent_token or None,
        )
    except Exception:
        print(f"{_guard_shared.RED}Failed to fetch team savings.{_guard_shared.RESET}")
        return
    if not isinstance(data, dict):
        print(f"{_guard_shared.RED}Failed to fetch team savings.{_guard_shared.RESET}")
        return

    dev_count   = data.get("developer_count", 0)
    total_tok   = data.get("total_tokens_saved", 0)
    total_usd   = data.get("total_cost_saved_usd", 0.0)
    per_day     = data.get("per_day_usd", 0.0)
    per_month   = data.get("per_month_usd", 0.0)
    per_year    = data.get("per_year_usd", 0.0)
    days_obs    = data.get("days_observed", 1)
    tools       = data.get("tools_installed", [])
    avg_tok     = total_tok // dev_count if dev_count else 0
    avg_day_usd = round(per_day / dev_count, 2) if dev_count else 0.0

    print()
    print(f"{_guard_shared.BOLD}Team Token Savings{_guard_shared.RESET}  ({dev_count} developer{'s' if dev_count != 1 else ''})")
    print("─" * 52)
    print(f"  Total tokens saved:    {total_tok:>14,}    (${total_usd:,.2f} over {days_obs} day{'s' if days_obs != 1 else ''})")
    print(f"  Daily rate:            ${per_day:>8.2f}/day  ·  projected ${per_month:,.0f}/month  ·  ${per_year:,.0f}/year")
    if dev_count:
        print(f"  Avg per developer:     {avg_tok:>14,} tokens  ·  ${avg_day_usd:.2f}/day")
    if tools:
        print(f"  Tools contributing:    {', '.join(tools)}")
    print()


def cmd_guard_session(args):
    sub = getattr(args, "session_cmd", None)
    if sub == "start":
        import uuid as _uuid
        goal = getattr(args, "goal", "") or ""
        goal_id = str(_uuid.uuid4())
        cfg = _guard_shared._load_guard_config()
        cfg["current_goal_id"] = goal_id
        cfg["current_goal_name"] = goal
        _guard_shared._save_guard_config(cfg)
        print(f"  {_guard_shared.GREEN}Session started{_guard_shared.RESET}")
        if goal:
            print(f"  Goal: {_guard_shared.CYAN}{goal}{_guard_shared.RESET}")
        print(f"  ID:   {goal_id}")
        print(f"\nAll Guard events in this session will be tagged with this goal.")
        print(f"Run {_guard_shared.BOLD}conduct guard session stop{_guard_shared.RESET} when done.")
    elif sub == "stop":
        cfg = _guard_shared._load_guard_config()
        name = cfg.pop("current_goal_name", "")
        cfg.pop("current_goal_id", None)
        _guard_shared._save_guard_config(cfg)
        print(f"  {_guard_shared.GREEN}Session stopped{_guard_shared.RESET}" + (f" — {name}" if name else ""))
    else:
        print("Usage: conduct guard session start [--goal GOAL] | stop")


def cmd_guard_audit(args):
    cfg          = _guard_shared._require_guard_config()
    workspace_id = cfg.get("workspace_id")
    user_email   = cfg.get("user_email", "")
    agent_token  = cfg.get("agent_token", "")
    base_url     = _guard_shared._api_url(cfg)

    since_str = getattr(args, "since", None) or "24h"
    since_iso = _guard_shared._parse_since(since_str)

    events_resp = _guard_shared._req(
        "GET",
        (
            f"{base_url}/guard/events"
            f"?workspace_id={workspace_id}"
            f"&user_email={user_email}"
            f"&since={since_iso}"
            f"&limit=50"
        ),
        token=agent_token or None,
    )
    events = events_resp if isinstance(events_resp, list) else events_resp.get("events", [])

    if not events:
        print(f"{_guard_shared.GRAY}No events in the last {since_str}.{_guard_shared.RESET}")
        return

    # Table header
    ts_w     = 22
    tool_w   = 14
    action_w = 28
    dec_w    = 10
    print()
    print(
        f"{_guard_shared.BOLD}"
        f"{'Timestamp':<{ts_w}} "
        f"{'Tool':<{tool_w}} "
        f"{'Action':<{action_w}} "
        f"{'Decision':<{dec_w}} "
        f"{'Rule'}"
        f"{_guard_shared.RESET}"
    )
    print("─" * (ts_w + tool_w + action_w + dec_w + 20))

    for ev in events:
        ts_raw   = ev.get("timestamp", ev.get("created_at", ""))
        ts       = ts_raw[:19].replace("T", " ") if ts_raw else "—"
        tool     = (ev.get("ai_tool") or "—")[:tool_w - 1]
        action   = (ev.get("tool_call") or "—")[:action_w - 1]
        decision = ev.get("decision", "—")
        rule     = (ev.get("rule_id") or ev.get("rule_message") or "—")

        # policy_signature_invalid events get a distinct BLOCK prefix line.
        if rule == "policy_signature_invalid":
            hostname = ""
            try:
                import json as _j
                payload = _j.loads(ev.get("input_summary") or "{}")
                hostname = payload.get("hostname", ev.get("hostname") or "")
            except Exception:
                pass
            ws_slug = cfg.get("workspace_id", "")
            print(
                f"  {_guard_shared.RED}[BLOCK]{_guard_shared.RESET} {_guard_shared.GRAY}{ts}{_guard_shared.RESET} "
                f"policy_signature_invalid "
                f"host={hostname} workspace={ws_slug}"
            )
            continue

        dec_color = _guard_shared.RED if decision == "blocked" else _guard_shared.GREEN if decision == "allowed" else _guard_shared.GRAY
        print(
            f"  {_guard_shared.GRAY}{ts:<{ts_w}}{_guard_shared.RESET} "
            f"{tool:<{tool_w}} "
            f"{action:<{action_w}} "
            f"{dec_color}{decision:<{dec_w}}{_guard_shared.RESET} "
            f"{_guard_shared.GRAY}{rule}{_guard_shared.RESET}"
        )

    print()
