"""`conduct switch` and `conduct whoami`."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from conduct_cli import api
from conduct_cli import guard as _guard
from conduct_cli.commands.shared import (
    BOLD,
    CONFIG_PATH,
    GRAY,
    GREEN,
    RED,
    RESET,
    YELLOW,
    _atomic_write,
    _load_config,
)


def _build_state(issue: dict, repo_full_name: str) -> dict:
    owner, repo = repo_full_name.split("/", 1)
    trigger = {
        "repo_owner":     owner,
        "repo_name":      repo,
        "repo_full_name": repo_full_name,
        "issue_number":   issue["number"],
        "title":          issue["title"],
        "body":           issue.get("body") or "",
        "url":            issue["url"],
        "author":         issue["author"],
        "labels":         issue["labels"],
        "label_added":    issue["labels"][0] if issue["labels"] else "",
        "default_branch": "main",
        "clone_url":      issue["clone_url"],
    }
    return {"github_issue": trigger, "_trigger": trigger}


def cmd_switch(args):
    cfg = _load_config()
    server  = (cfg.get("server") or cfg.get("api_url") or "").rstrip("/")
    api_key = cfg.get("agent_token", "")
    token   = cfg.get("token", "")

    if not server or (not api_key and not token):
        print(f"{RED}Not logged in. Run: conduct login{RESET}")
        sys.exit(1)

    hdrs = {"Content-Type": "application/json"}
    if api_key:
        hdrs["Authorization"] = f"Bearer {api_key}"
    elif token:
        hdrs["Authorization"] = f"Bearer {token}"

    workspaces = api.req("GET", f"{server}/projects", hdrs)

    current_id = cfg.get("workspace", "")
    target = getattr(args, "workspace", None)

    if not target:
        # List mode — print numbered list with current marked
        if not workspaces:
            print("No workspaces found.")
            return
        print(f"\n{BOLD}Workspaces:{RESET}")
        for i, ws in enumerate(workspaces, 1):
            marker = f"{GREEN}*{RESET}" if str(ws.get("id", "")) == str(current_id) else " "
            wid = str(ws.get("id", ""))
            print(f"  {marker} {i}. {ws['name']:<35} {GRAY}{wid}{RESET}")
        print()
        return

    # Match workspace: exact name (case-insensitive) first
    target_lower = target.lower()

    exact = [ws for ws in workspaces if ws["name"].lower() == target_lower]
    if not exact:
        # Partial name match
        partial = [ws for ws in workspaces if target_lower in ws["name"].lower()]
        if not partial:
            # UUID prefix match
            partial = [ws for ws in workspaces if str(ws.get("id", "")).startswith(target)]
        candidates = partial
    else:
        candidates = exact

    if len(candidates) > 1:
        print(f"{YELLOW}Ambiguous — multiple matches for '{target}':{RESET}")
        for ws in candidates:
            print(f"  {ws['name']}  {GRAY}({ws['id']}){RESET}")
        print("Be more specific.")
        sys.exit(1)

    if not candidates:
        print(f"{RED}No workspace matching '{target}' found. Available:{RESET}")
        for ws in workspaces:
            print(f"  {ws['name']}  {GRAY}({ws['id']}){RESET}")
        sys.exit(1)

    chosen = candidates[0]
    new_id   = str(chosen["id"])
    new_name = chosen["name"]

    # Re-mint agent token bound to the new workspace so server-side attribution
    # follows the switch. Without this, POSTs (discover, audit, heartbeats)
    # keep hitting the workspace the token was originally minted for.
    try:
        _r = api.req("POST", f"{server}/auth/switch-workspace", hdrs, {"workspace_id": new_id})
        if _r and _r.get("agent_token"):
            cfg["agent_token"]      = _r["agent_token"]
            if _r.get("refresh_token"):
                cfg["refresh_token"] = _r["refresh_token"]
            import datetime as _dt
            cfg["token_expires_at"] = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=int(_r.get("expires_in", 28800)))).isoformat()
    except SystemExit:
        print(f"  {RED}✗ Cannot switch to {new_name}: token re-mint failed. Run `conduct login` and try again.{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"  {RED}✗ Cannot switch to {new_name}: {e}. Run `conduct login` and try again.{RESET}")
        sys.exit(1)

    from conduct_cli.guard_commands.copilot import clear_managed
    clear_managed()
    # Update ~/.conduct/config.json atomically
    cfg["workspace"] = new_id; cfg["workspace_id"] = new_id
    _atomic_write(CONFIG_PATH, cfg)

    # Full propagation to every surface — same flow login uses:
    #   proxy env file, MCP client configs (Cursor / Claude Desktop /
    #   Windsurf / Copilot), hook script, coverage POST, policy cache.
    # Without this, MCP clients keep sending the OLD token to /guard/mcp
    # and every tool call attributes to the previous workspace.
    try:
        import types
        _guard.cmd_guard_sync(types.SimpleNamespace())
    except SystemExit:
        pass
    except Exception as e:
        print(f"  {YELLOW}⚠ Guard sync after switch failed: {e}{RESET}")

    print(f"{GREEN}✓ Switched to \"{new_name}\" ({new_id[:8]}){RESET}")


def cmd_whoami(args):
    cfg = _load_config()

    # cfg key drift: canonical keys are workspace_id / api_url, older configs used workspace / server
    workspace_id   = cfg.get("workspace_id") or cfg.get("workspace") or ""
    server         = cfg.get("api_url") or cfg.get("server") or "—"
    api_key        = cfg.get("agent_token", "")

    # Try to resolve workspace name from /projects
    workspace_name = ""
    if workspace_id and server != "—" and api_key:
        try:
            hdrs = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            projects = api.req("GET", f"{server.rstrip('/')}/projects", hdrs)
            match = next((p for p in projects if str(p.get("id", "")) == str(workspace_id)), None)
            if match:
                workspace_name = match["name"]
        except (Exception, SystemExit):
            pass  # server error on /projects (e.g. agent token → 500) is cosmetic

    ws_display = workspace_name if workspace_name else workspace_id
    ws_id_hint = f"  ({workspace_id[:8]})" if workspace_id else ""
    api_key_display = (api_key[:12] + "…  (set)") if api_key else "not set"

    print(f"\n{BOLD}Workspace:{RESET}  {ws_display}{ws_id_hint}")
    print(f"{BOLD}Server:{RESET}     {server}")
    print(f"{BOLD}Agent token:{RESET} {api_key_display}")
    from ..identity import identity_label
    print(f"{BOLD}Agent ID:{RESET}    {identity_label(cfg)}")

    # Guard section — all under ~/.conduct/
    policy_path = Path.home() / ".conduct" / "policy.json"
    hook_path   = Path.home() / ".conduct" / "hook.py"
    guard_email = cfg.get("user_email", "")
    agent_token = cfg.get("agent_token", "")
    if agent_token or hook_path.exists():
        rule_count  = 0
        if policy_path.exists():
            try:
                rule_count = len(json.loads(policy_path.read_text()).get("rules", []))
            except Exception:
                pass
        hook_status = "hook installed" if hook_path.exists() else "hook missing"
        email_part  = f"  |  member: {guard_email}" if guard_email else ""
        print(f"{BOLD}Guard:{RESET}      {GREEN}✓ {hook_status}{RESET}  |  policy: {rule_count} rules{email_part}")
    else:
        print(f"{BOLD}Guard:{RESET}      not configured")

    # Booster section
    booster_paths = [
        Path.home() / ".booster" / "config.json",
        Path.home() / ".agent-booster" / "config.json",
    ]
    booster_found = any(p.exists() for p in booster_paths)
    if booster_found:
        print(f"{BOLD}Booster:{RESET}    {GREEN}✓ configured{RESET}")
    else:
        print(f"{BOLD}Booster:{RESET}    not configured")

    print()
