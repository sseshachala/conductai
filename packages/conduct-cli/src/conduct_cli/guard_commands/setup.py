"""Guard CLI: setup."""
from __future__ import annotations

from pathlib import Path
import json
import os
import sys
import urllib.error
import urllib.request

from . import booster as _guard_booster
from . import discovery as _guard_discovery
from . import gateway as _guard_gateway
from . import hooks as _guard_hooks
from . import instructions as _guard_instructions
from . import mcp as _guard_mcp
from . import policy as _guard_policy
from . import reporting as _guard_reporting
from . import shared as _guard_shared
from . import watch as _guard_watch


_PERSONA_LABELS = {
    "conservative": "Conservative  — production-safe, default deny",
    "standard":     "Standard      — engineering teams, balanced",
    "developer":    "Developer     — local dev, audit-first",
}


def _ensure_persona(workspace_id: str, base_url: str) -> str:
    """Prompt for persona if none is set yet. Saves choice to guard config and API.

    Returns the active persona name. Skips prompt silently if already set.
    """
    agent_token = _guard_shared._default_agent_token() or ""
    cfg = _guard_shared._load_guard_config()
    if cfg.get("persona"):
        return cfg["persona"]

    print(f"\n{_guard_shared.BOLD}Choose a policy persona for your agents:{_guard_shared.RESET}")
    choices = list(_PERSONA_LABELS.keys())
    for i, key in enumerate(choices, 1):
        print(f"  {i}. {_PERSONA_LABELS[key]}")

    while True:
        try:
            raw = input(f"\nEnter 1-{len(choices)} [default: 2 — Standard]: ").strip()
            if raw == "":
                raw = "2"
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                chosen = choices[idx]
                break
            print(f"  Enter a number between 1 and {len(choices)}")
        except (ValueError, EOFError):
            chosen = "standard"
            break

    # Push to API
    try:
        _guard_shared._req(
            "PATCH",
            f"{base_url}/guard/config/persona",
            body={"persona": chosen},
            token=agent_token or None,
        )
    except Exception:
        pass  # non-fatal — local config still records the choice

    # Persist locally so we skip the prompt on subsequent syncs
    cfg = _guard_shared._load_guard_config()
    cfg["persona"] = chosen
    _guard_shared._save_guard_config(cfg)

    print(f"  {_guard_shared.GREEN}Persona set:{_guard_shared.RESET} {chosen.capitalize()}")
    return chosen


def cmd_guard_install(args):
    """Called automatically from `conduct login`. Sets up Guard: downloads policies, installs hook + MCP."""
    agent_token = getattr(args, "agent_token", None)
    server      = (getattr(args, "server", None) or "https://api.conductai.ai").rstrip("/")

    # Load workspace_id (and fallback agent_token) from ~/.conduct/config.json
    conduct_cfg_path = Path.home() / ".conduct" / "config.json"
    conduct_cfg: dict = {}
    if conduct_cfg_path.exists():
        try:
            conduct_cfg = json.loads(conduct_cfg_path.read_text())
        except Exception:
            pass

    workspace_id = conduct_cfg.get("workspace")
    if not agent_token:
        agent_token = conduct_cfg.get("agent_token")
    if not workspace_id or not agent_token:
        return  # nothing to do

    print(f"  Setting up Guard…")

    result = _guard_shared._req(
        "GET",
        f"{server}/guard/config/installed?workspace_id={workspace_id}",
        token=agent_token or None,
    )

    if not result.get("installed"):
        print(f"  {_guard_shared.GRAY}Guard not installed for this workspace — skipping{_guard_shared.RESET}")
        return

    resp_agent_token = result.get("agent_token") or agent_token
    user_email       = result.get("user_email") or ""
    clerk_user_id    = result.get("clerk_user_id") or ""

    # Persona selection — prompt once, skip if already chosen

    # Persist unified config — single ~/.conduct/config.json
    import time as _time
    _guard_shared._save_guard_config({
        "workspace_id":          workspace_id,
        "agent_token":           resp_agent_token,
        "user_email":            user_email,
        "clerk_user_id":         clerk_user_id,
        "api_url":               server,
        "last_synced_at":        _time.time(),
    })

    # Download policies
    try:
        policy = _guard_shared._req(
            "GET",
            f"{server}/guard/policies/sync?workspace_id={workspace_id}",
            token=agent_token,
        )
        _guard_policy._save_policy(policy)
        # Mirror fail_mode into guard config so the hook can enforce it
        # even when POLICY_PATH is missing or unreadable.
        cfg = _guard_shared._load_guard_config()
        cfg["fail_mode"] = policy.get("fail_mode", "fail_closed")
        cfg["advisory_mode"] = policy.get("advisory_mode", False)
        _guard_shared._save_guard_config(cfg)
        rule_count = len(policy.get("rules", []))
        advisory_label = " · advisory" if cfg["advisory_mode"] else ""
        print(f"  {_guard_shared.GREEN}Guard policies:{_guard_shared.RESET} {rule_count} rule(s) active · fail mode: {cfg['fail_mode']}{advisory_label}")
    except SystemExit:
        rule_count = 0

    # Write hook script
    hook_path = _guard_shared.GUARD_DIR / "hook.py"
    _guard_hooks._write_hook(hook_path)

    # Install PreToolUse hooks — Claude Code + Codex (real interception)
    _guard_hooks._install_claude_hook(hook_path)
    _guard_hooks._install_codex_hook(hook_path)
    _guard_hooks._install_copilot_hooks(hook_path)

    # Register MCP in all found AI tools — Cursor/Windsurf (advisory)
    _guard_mcp._register_mcp(workspace_id, agent_token or "", server)

    _cd = next((t for t in _guard_discovery._detect_ai_tools() if t["name"] == "claude-desktop" and not t.get("proxy_routed")), None)
    if _cd:
        print(f"  {_guard_shared.CYAN}Claude Desktop detected — patching apiBaseUrl to route through Guard proxy{_guard_shared.RESET}")
        _guard_mcp._patch_claude_desktop_proxy(server, agent_token or "")

    # Install session persistence hooks (PreCompact + SessionStart)
    try:
        _guard_hooks._install_session_hooks()
    except Exception:
        pass

    # Write signing key if provided by the admin at onboarding time.
    signing_key_hex = getattr(args, "signing_key", None)
    if signing_key_hex:
        _write_signing_key(signing_key_hex)

    # Start watch daemon — auto-discovers agents every 15 min, no user action needed.
    try:
        import subprocess as _sp, sys as _sys
        running, _ = _guard_watch._is_watch_running()
        if not running:
            log_file = open(_guard_watch._WATCH_LOG, "a")
            proc = _sp.Popen(
                [_sys.executable, "-c",
                 "from conduct_cli.guard import _watch_loop; _watch_loop()"],
                start_new_session=True,
                stdout=log_file,
                stderr=log_file,
            )
            _guard_watch._WATCH_PID.write_text(str(proc.pid))
            print(f"  {_guard_shared.GREEN}Guard watch:{_guard_shared.RESET} background discovery daemon started (pid {proc.pid})")
        else:
            print(f"  {_guard_shared.GREEN}Guard watch:{_guard_shared.RESET} already running")
    except Exception:
        pass


def _write_signing_key(hex_key: str) -> None:
    """Write a hex-encoded signing key to ~/.conduct/signing.key.

    Validates that the path resolves within GUARD_DIR (no traversal) and
    that the value is a valid 64-char hex string (32 bytes).
    """
    import re as _re
    signing_key_path = _guard_shared.GUARD_DIR / "signing.key"

    # Path traversal guard.
    try:
        resolved = signing_key_path.resolve()
        resolved.relative_to(_guard_shared.GUARD_DIR.resolve())
    except (ValueError, RuntimeError):
        print(f"  {_guard_shared.RED}Signing key path rejected (traversal check failed).{_guard_shared.RESET}")
        return

    # Must be exactly 64 hex characters (32 bytes).
    if not _re.fullmatch(r"[0-9a-fA-F]{64}", hex_key.strip()):
        print(f"  {_guard_shared.RED}Invalid signing key: expected 64 hex characters.{_guard_shared.RESET}")
        return

    _guard_shared.GUARD_DIR.mkdir(parents=True, exist_ok=True)
    signing_key_path.write_text(hex_key.strip())
    print(f"  {_guard_shared.GREEN}Signing key written:{_guard_shared.RESET} {signing_key_path}")


def cmd_guard_join(args):
    invite_code = args.invite_code

    # Prompt for email if not supplied
    email = getattr(args, "email", None) or input("Email address: ").strip()
    if not email:
        print(f"{_guard_shared.RED}Email is required.{_guard_shared.RESET}")
        sys.exit(1)

    # Use configured API URL or default
    existing_cfg = _guard_shared._load_guard_config()
    base_url     = existing_cfg.get("api_url", "https://api.conductai.ai").rstrip("/")

    print(f"\nJoining workspace with invite code {_guard_shared.CYAN}{invite_code}{_guard_shared.RESET}…")

    payload = {"invite_code": invite_code, "email": email}
    result = _guard_shared._req("POST", f"{base_url}/guard/join", body=payload)

    workspace_id = result["workspace_id"]
    agent_token_install = result.get("agent_token", "")
    policy       = result.get("policy", {"workspace_id": workspace_id, "version": "1", "rules": []})

    # Download and persist policy
    _guard_policy._save_policy(policy)
    rule_count = len(policy.get("rules", []))
    print(f"  {_guard_shared.GREEN}Policy downloaded:{_guard_shared.RESET} {rule_count} rule(s)")

    # Persist guard config
    import time as _time
    cfg = {
        "workspace_id":   workspace_id,
        "user_email":     email,
        "api_url":        base_url,
        "last_synced_at": _time.time(),
    }
    if agent_token_install:
        cfg["agent_token"] = agent_token_install
    _guard_shared._save_guard_config(cfg)

    # Write hook script
    hook_path = _guard_shared.GUARD_DIR / "hook.py"
    _guard_hooks._write_hook(hook_path)
    print(f"  {_guard_shared.GREEN}Hook script written:{_guard_shared.RESET} {hook_path}")

    # Install PreToolUse hook in ~/.claude/settings.json
    _guard_hooks._install_claude_hook(hook_path)

    print(
        f"\n{_guard_shared.BOLD}{_guard_shared.GREEN}Guard connected.{_guard_shared.RESET} "
        f"{rule_count} polic{'y' if rule_count == 1 else 'ies'} active.\n"
        f"Your AI tool calls will now be checked against team policies."
    )


def _check_and_upgrade_packages() -> None:
    """Print installed versions and pip-upgrade if PyPI has a newer release."""
    import importlib.metadata
    import urllib.request

    packages = ["conduct-cli", "agent-booster"]
    installed: dict[str, str] = {}
    for pkg in packages:
        try:
            installed[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            # agent-booster may live under a different Python interpreter
            try:
                import subprocess as _sp, shutil
                for py in ["python3.11", "python3.12", "python3.10"]:
                    if shutil.which(py):
                        out = _sp.check_output(
                            [py, "-c", f"import importlib.metadata; print(importlib.metadata.version('{pkg}'))"],
                            stderr=_sp.DEVNULL, text=True,
                        ).strip()
                        if out:
                            installed[pkg] = out
                            break
                else:
                    installed[pkg] = "unknown"
            except Exception:
                installed[pkg] = "unknown"

    print(f"  conduct-cli {installed['conduct-cli']}  ·  agent-booster {installed['agent-booster']}")

    stale = []
    for pkg, current in installed.items():
        if current == "unknown":
            continue
        try:
            with urllib.request.urlopen(f"https://pypi.org/pypi/{pkg}/json", timeout=4) as r:
                latest = __import__("json").loads(r.read())["info"]["version"]
            from packaging.version import Version
            if Version(latest) > Version(current):
                stale.append((pkg, current, latest))
        except Exception:
            pass  # offline or PyPI down — skip silently

    if not stale:
        return

    print(f"  {_guard_shared.YELLOW}Updates available:{_guard_shared.RESET} " + ", ".join(f"{p} {c} → {l}" for p, c, l in stale))
    try:
        import subprocess, shutil
        # agent-booster requires >=3.10; conduct-cli runs on 3.9.
        # Use the right interpreter for each package.
        def _pip_for(pkg: str) -> str:
            if pkg == "agent-booster":
                for py in ["python3.11", "python3.12", "python3.10"]:
                    if shutil.which(py):
                        return py
            return sys.executable

        for pkg, _, latest in stale:
            py = _pip_for(pkg)
            subprocess.run(
                [py, "-m", "pip", "install", "--upgrade", "--quiet", pkg],
                check=True,
            )
        print(f"  {_guard_shared.GREEN}Updated:{_guard_shared.RESET} " + ", ".join(f"{p} → {l}" for p, _, l in stale))
    except Exception as e:
        print(f"  {_guard_shared.YELLOW}Auto-update failed:{_guard_shared.RESET} {e} — run: pip install --upgrade {' '.join(p for p,_,_ in stale)}")


def _proactive_token_refresh() -> None:
    """Refresh agent_token if it expires within 5 min. No-op if no refresh_token."""
    cfg = _guard_shared._load_guard_config()
    if not cfg.get("refresh_token"):
        return
    import datetime as _dt, json as _json
    exp = cfg.get("token_expires_at", "")
    try:
        if exp and _dt.datetime.fromisoformat(exp) >= _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=5):
            return  # still valid
    except ValueError:
        pass
    # Capture prior workspace BEFORE refresh — server returns whichever
    # workspace the refresh token was originally issued for (usually the
    # account default). Without restore, every 5-min token refresh silently
    # blows away the user's active workspace context.
    prior_ws = cfg.get("workspace_id") or cfg.get("workspace") or ""
    api_url = _guard_shared._api_url(cfg)
    try:
        req = urllib.request.Request(
            f"{api_url}/auth/refresh",
            data=_json.dumps({"refresh_token": cfg["refresh_token"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        cfg["agent_token"]      = data["agent_token"]
        cfg["refresh_token"]    = data["refresh_token"]
        cfg["workspace_id"]     = data["workspace_id"]
        cfg["workspace"]        = data["workspace_id"]
        cfg["token_expires_at"] = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=8)).isoformat()
        # Restore prior workspace if refresh returned a different default.
        if prior_ws and str(prior_ws) != str(data["workspace_id"]):
            try:
                _req2 = urllib.request.Request(
                    f"{api_url}/auth/switch-workspace",
                    data=_json.dumps({"workspace_id": prior_ws}).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {cfg['agent_token']}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(_req2, timeout=10) as _resp2:
                    _rd = _json.loads(_resp2.read())
                cfg["agent_token"]      = _rd["agent_token"]
                if _rd.get("refresh_token"):
                    cfg["refresh_token"] = _rd["refresh_token"]
                cfg["workspace"]        = prior_ws
                cfg["workspace_id"]     = prior_ws
                cfg["token_expires_at"] = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=int(_rd.get("expires_in", 28800)))).isoformat()
            except Exception:
                pass  # not a member or endpoint missing — keep server default
        _guard_shared._save_guard_config(cfg)
    except Exception:
        print(f"  {_guard_shared.YELLOW}⚠ Token refresh failed — run `conduct login` if sync fails{_guard_shared.RESET}")


def cmd_guard_sync(args):
    _proactive_token_refresh()
    cfg          = _guard_shared._require_guard_config()
    workspace_id = cfg.get("workspace_id") or cfg.get("workspace")
    agent_token  = cfg.get("agent_token", "")
    base_url     = _guard_shared._api_url(cfg)
    _token       = agent_token or None

    # Persona selection — prompt once, skip if already chosen

    dry_run = getattr(args, "dry_run", False)

    if getattr(args, "reset_instructions", False):
        print("Removing ConductGuard blocks from instruction files…")
        _guard_instructions._reset_tool_instruction_files()
        return

    print(f"{'[dry-run] ' if dry_run else ''}Syncing policy…")
    _check_and_upgrade_packages()

    try:
        policy = _guard_shared._req(
            "GET",
            f"{base_url}/guard/policies/sync?workspace_id={workspace_id}",
            token=_token,
        )
    except Exception as e:
        print(f"Guard sync skipped: {e}", file=sys.stderr)
        sys.exit(0)

    rules = policy.get("rules", [])
    rule_count = len(rules)

    if dry_run:
        current_policy = _guard_policy._load_policy()
        current_rules = {r["rule_id"]: r for r in current_policy.get("rules", [])}
        new_rules = {r["rule_id"]: r for r in rules}

        added   = [r for r in new_rules   if r not in current_rules]
        removed = [r for r in current_rules if r not in new_rules]
        changed = [
            r for r in new_rules
            if r in current_rules and new_rules[r].get("action") != current_rules[r].get("action")
        ]

        print(f"\n  {_guard_shared.BOLD}Dry run — no files written{_guard_shared.RESET}")
        print(f"  Rules in policy: {rule_count}")
        if added:
            print(f"\n  {_guard_shared.GREEN}+ Added ({len(added)}){_guard_shared.RESET}")
            for rid in added:
                r = new_rules[rid]
                print(f"      {rid}  [{r.get('action','?').upper()}]")
        if removed:
            print(f"\n  {_guard_shared.RED}- Removed ({len(removed)}){_guard_shared.RESET}")
            for rid in removed:
                print(f"      {rid}")
        if changed:
            print(f"\n  ~ Changed action ({len(changed)})")
            for rid in changed:
                old_a = current_rules[rid].get("action", "?")
                new_a = new_rules[rid].get("action", "?")
                print(f"      {rid}  {old_a} → {new_a}")
        if not added and not removed and not changed:
            print(f"  {_guard_shared.GREEN}No changes{_guard_shared.RESET}")
        return

    _guard_policy._save_policy(policy)
    print(f"  {_guard_shared.GREEN}Policy refreshed:{_guard_shared.RESET} {rule_count} hook rule(s). Proxy and non-hook rules run server-side.")

    # Installation metadata is not a refresh grant. Keep the access/refresh pair
    # together; another OAuth client's token must never replace this session.
    try:
        installed = _guard_shared._req(
            "GET",
            f"{base_url}/guard/config/installed?workspace_id={workspace_id}",
            token=_token,
        )
        if installed.get("user_email"):
            cfg["user_email"] = installed["user_email"]
        if installed.get("clerk_user_id"):
            cfg["clerk_user_id"] = installed["clerk_user_id"]
        _guard_shared._save_guard_config(cfg)
        if not cfg.get("agent_token"):
            print(f"  {_guard_shared.YELLOW}Warning: server returned no token — proxy env may be stale{_guard_shared.RESET}")
    except Exception as e:
        print(f"  {_guard_shared.YELLOW}Warning: could not fetch installation metadata ({e}){_guard_shared.RESET}")

    # Write LLM proxy env vars so any AI tool (Claude Code, Cursor, Codex, …)
    # routes through Conduct Guard. Customer-overridable via --proxy-url or
    # CONDUCT_PROXY_URL env var; otherwise fetched from server (workspace_config).
    explicit_proxy_url = getattr(args, "proxy_url", None) or os.environ.get("CONDUCT_PROXY_URL")
    proxy_url = explicit_proxy_url
    if not proxy_url:
        try:
            import urllib.request as _ur, urllib.error as _ue
            _headers = {"Content-Type": "application/json"}
            _token = cfg.get("agent_token", "")
            if _token:
                _headers["Authorization"] = f"Bearer {_token}"
            _r = _ur.Request(f"{base_url}/guard/proxy-config", headers=_headers)
            with _ur.urlopen(_r, timeout=10) as _resp:
                proxy_url = json.loads(_resp.read()).get("conduct_proxy_url") or _guard_gateway.DEFAULT_PROXY_URL
        except Exception:
            proxy_url = _guard_gateway.DEFAULT_PROXY_URL
    if not explicit_proxy_url:
        proxy_url = _guard_gateway._gateway_v1_url(proxy_url)
    agent_token = cfg.get("agent_token", "")
    rc_path, newly_sourced = _guard_gateway._write_proxy_env(agent_token, proxy_url)
    if agent_token:
        env_name = "env.ps1" if sys.platform == "win32" else "env"
        activate_cmd = f". {rc_path}" if sys.platform == "win32" else f"source {rc_path}"
        print(f"  {_guard_shared.GREEN}Proxy env written:{_guard_shared.RESET} ~/.conduct/{env_name} → {proxy_url}")
        if newly_sourced:
            print(f"  {_guard_shared.CYAN}Run `{activate_cmd}` (or open a new shell) to activate.{_guard_shared.RESET}")
    if not getattr(args, "no_codex_proxy", False) and agent_token:
        if _guard_gateway._configure_codex_proxy(proxy_url):
            _guard_gateway._configure_codex_launch_env(agent_token)
            print(f"  {_guard_shared.GREEN}Codex proxy enabled:{_guard_shared.RESET} Responses API via Conduct (restart Codex)")
            print(f"  {_guard_shared.CYAN}New terminal sessions load the managed credential. "
                  f"Fully quit and reopen Codex; running apps keep their old environment.{_guard_shared.RESET}")
        else:
            print(f"  {_guard_shared.YELLOW}Codex proxy skipped:{_guard_shared.RESET} ~/.codex is not installed")

    _guard_hooks._install_copilot_hooks(_guard_shared.GUARD_DIR / "hook.py")
    _tools = _guard_discovery._detect_ai_tools()
    if _tools:
        print(f"\n  {'Tool':<20} {'Proxy Routed':<16} {'MCP':<8} {'Hooks'}")
        print(f"  {'─'*20} {'─'*16} {'─'*8} {'─'*8}")
        for t in _tools:
            routed = "✓ Routed" if t.get("proxy_routed") else ("— Partial" if t["name"] == "codex-desktop" else "✗ Not routed")
            mcp  = "✓" if t.get("mcp_registered") else "✗"
            hook = "✓" if t.get("hook_registered") else ("~ soft" if t["name"] in ("copilot", "cursor") else "—")
            print(f"  {t['name']:<20} {routed:<16} {mcp:<8} {hook}")
        print()

    _cd = next((t for t in _tools if t["name"] == "claude-desktop" and not t.get("proxy_routed")), None)
    if _cd:
        print(f"  {_guard_shared.CYAN}Claude Desktop detected — patching apiBaseUrl to route through Guard proxy{_guard_shared.RESET}")
        _guard_mcp._patch_claude_desktop_proxy(cfg.get("api_url", "https://api.conductai.ai"), agent_token)

    # Local key audit — scan known config files for real provider keys that
    # may have been pasted before the dev onboarded onto Conduct. Findings
    # surface in /guard/audit with a 'LOCAL RISK' badge. --no-local-audit
    # skips the scan (CI runners, dev throw-away setups, etc.)
    if not getattr(args, "no_local_audit", False):
        local = _guard_gateway._scan_local_keys()
        if local:
            print(f"  {_guard_shared.YELLOW}Local risk: {len(local)} pre-existing key(s) found{_guard_shared.RESET}")
            for f in local[:5]:
                print(f"    [{f['provider']}] {f['path']}:{f['line']}  {f['masked']}")
            if len(local) > 5:
                print(f"    …{len(local) - 5} more — see /guard/audit")
            _guard_gateway._post_local_findings(cfg, base_url, local)

    if getattr(args, "cursor", False):
        _guard_instructions._write_cursorrules(policy)


    # Refresh hook script + re-register in all tools
    hook_path = _guard_shared.GUARD_DIR / "hook.py"
    _guard_hooks._write_hook(hook_path)
    _guard_hooks._install_claude_hook(hook_path)
    _guard_hooks._install_codex_hook(hook_path)
    cfg2 = _guard_shared._load_guard_config()
    _guard_mcp._register_mcp(workspace_id, cfg2.get("agent_token", ""), base_url, dry_run=dry_run)
    try:
        _guard_hooks._install_session_hooks()
    except Exception:
        pass
    print(f"  {_guard_shared.GREEN}Hook script updated{_guard_shared.RESET}")

    # Auto-init Agent Booster if installed but not yet set up in this project
    _guard_booster._ensure_booster(Path.cwd())

    # Capture savings from RTK and Agent Booster
    _guard_reporting._report_savings(cfg, base_url)

    # Report AI tool coverage
    try:
        _guard_discovery._report_tools_to_server()
    except Exception:
        pass

    # Run shadow agent discovery in background — results pushed to API, visible in /guard/discovery
    try:
        import subprocess as _sp, shutil as _shutil
        _conduct = _shutil.which("conduct") or sys.executable
        _sp.Popen(
            [_conduct, "guard", "discover"],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
        )
        print(f"  {_guard_shared.CYAN}Discovery daemon started{_guard_shared.RESET} — agent inventory updating in background")
    except Exception:
        pass

    print(f"\n{_guard_shared.BOLD}Policy refreshed: {rule_count} hook rule(s). Proxy and non-hook rules run server-side.{_guard_shared.RESET}")

    # Print remote MCP URL for any MCP-compatible client
    agent_token = cfg.get("agent_token", "")
    if workspace_id and agent_token:
        mcp_url = "https://gateway.conductai.ai/mcp"
        masked = agent_token[:13] + "•" * 20
        print(f"\n{_guard_shared.BOLD}MCP server{_guard_shared.RESET} (Claude.ai, Copilot, Cursor, Windsurf, any MCP client):")
        print(f"  URL:    {_guard_shared.CYAN}{mcp_url}{_guard_shared.RESET}")
        print(f"  Auth:   {_guard_shared.CYAN}Bearer {masked}{_guard_shared.RESET}  {_guard_shared.GRAY}(run `conduct token` to reveal){_guard_shared.RESET}\n")
