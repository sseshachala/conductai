"""`conduct test-guard` and `conduct memory`."""
from __future__ import annotations

import sys

from conduct_cli import deployment
from conduct_cli.commands.shared import BOLD, CYAN, GRAY, RED, RESET, YELLOW


def cmd_test_guard(args):
    """Test each guard policy rule with a matching synthetic tool call."""
    import json as _json
    import re as _re
    from conduct_cli.guard import _load_guard_config, _load_policy, active_policy_path

    cfg = _load_guard_config()
    pol_path = active_policy_path()  # workspace-scoped

    if not pol_path.exists():
        print(f"{RED}No policy file found. Run: conduct guard sync{RESET}")
        sys.exit(1)

    try:
        policy = _load_policy()
    except Exception as e:
        print(f"{RED}Could not load policy: {e}{RESET}")
        sys.exit(1)

    rules = policy.get("rules", [])
    if not rules:
        print(f"{YELLOW}No rules in local policy. Run: conduct guard sync{RESET}")
        sys.exit(0)

    workspace_id = cfg.get("workspace_id")
    api_key      = cfg.get("agent_token", "")
    api_url      = deployment.api_url(cfg)

    print(f"\n{BOLD}▶ conduct test-guard — {len(rules)} rule(s){RESET}\n")

    import urllib.request

    blocked = 0
    allowed = 0
    errors  = 0
    for rule in rules:
        rule_id  = rule.get("rule_id", "unknown")
        action   = rule.get("action", "audit")
        message  = rule.get("message") or rule_id
        tool     = (rule.get("match_tool") or "bash").split(",")[0].strip()
        pattern  = rule.get("match_pattern") or rule.get("match_path_pattern") or ""

        # Build a synthetic input that satisfies the rule's pattern
        if pattern:
            try:
                # Use the pattern itself as a test input fragment where possible
                test_input = _re.sub(r"[\\^$.*+?()\[\]{}|]", "", pattern)[:80] or rule_id
            except Exception:
                test_input = rule_id
        else:
            test_input = rule_id

        payload = _json.dumps({
            "ai_tool": "claude-code",
            "tool_call": tool,
            "input_summary": f"[TEST] {test_input}",
            "decision": action if action in ("blocked", "warn") else "blocked",
            "rule_id": rule_id,
            "rule_message": f"[TEST] {message}",
        }).encode()

        action_color = RED if action == "blocked" else (YELLOW if action == "warn" else CYAN)
        action_label = action.upper()

        if workspace_id:
            try:
                req = urllib.request.Request(
                    f"{api_url}/guard/events/test?workspace_id={workspace_id}",
                    data=payload,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5):
                    pass
                posted = f"{GRAY}posted{RESET}"
            except Exception:
                posted = f"{GRAY}local only{RESET}"
        else:
            posted = f"{GRAY}no workspace{RESET}"

        print(f"  {action_color}{action_label:<8}{RESET}  {rule_id:<35}  {GRAY}{message[:50]}{RESET}  {posted}")
        if action == "blocked":
            blocked += 1
        else:
            allowed += 1

    print(f"\n  {blocked} would block · {allowed} audit/allow")
    print(f"\n  {CYAN}→ View events: {api_url.replace('api.', 'app.')}/guard/activity{RESET}\n")


def cmd_memory(args):
    from conduct_cli.memory import search_team_memory
    memory_command = getattr(args, "memory_command", None)
    if memory_command == "search":
        query = " ".join(args.query)
        results = search_team_memory(query, repo=getattr(args, "repo", None), limit=args.limit)
        if not results:
            print("No team memories found.")
            return
        for r in results:
            dev = r.get("developer_id") or "unknown"
            repo = r.get("repo_full_name") or ""
            summary = r.get("summary", "")
            tags = ", ".join(r.get("topic_tags") or [])
            created = r.get("created_at", "")[:10]
            heading = f"{dev}  {GRAY}{repo}{RESET}" if repo else dev
            print(f"\n{BOLD}{heading}{RESET}  {GRAY}{created}{RESET}")
            if tags:
                print(f"  Tags: {tags}")
            print(f"  {summary}")
    else:
        print("Usage: conduct memory search <query>")
