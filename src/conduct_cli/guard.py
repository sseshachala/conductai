from __future__ import annotations
"""conduct guard — team policy + MCP registration subcommand."""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from conduct_cli.tool_groups import expand_match_tool

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
RED    = "\033[31m"
BLUE   = "\033[34m"
GRAY   = "\033[90m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"

CONDUCT_HOME = Path.home() / ".conduct"
GUARD_DIR    = CONDUCT_HOME
CONFIG_PATH  = CONDUCT_HOME / "config.json"    # unified config — shared with main.py
POLICY_PATH  = GUARD_DIR / "policy.json"


def active_policy_path() -> Path:
    return POLICY_PATH

# ── Hook templates — loaded from real .py files (no string embedding) ─────────

# ── Thin launcher content ─────────────────────────────────────────────────────

_THIN_LAUNCHERS = {
    "pretooluse": (
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "_cmd = sys.argv[1] if len(sys.argv) > 1 else ''\n"
        "if _cmd == 'post':\n"
        "    try:\n        from conduct_cli.hooks.posttooluse import main; main()\n"
        "    except (ImportError, ModuleNotFoundError): sys.exit(0)\n"
        "elif _cmd == 'drain':\n"
        "    try:\n        from conduct_cli.hooks.base import run_drain_daemon; run_drain_daemon()\n"
        "    except (ImportError, ModuleNotFoundError): sys.exit(0)\n"
        "else:\n"
        "    try:\n        from conduct_cli.hooks.pretooluse import main; main()\n"
        "    except (ImportError, ModuleNotFoundError): sys.exit(0)\n"
    ),
    "posttooluse": (
        "#!/usr/bin/env python3\n"
        "try:\n    from conduct_cli.hooks.posttooluse import main; main()\n"
        "except (ImportError, ModuleNotFoundError): import sys; sys.exit(0)\n"
    ),
    "stop": (
        "#!/usr/bin/env python3\n"
        "try:\n    from conduct_cli.hooks.stop import main; main()\n"
        "except (ImportError, ModuleNotFoundError): import sys; sys.exit(0)\n"
    ),
    "precompact": (
        "#!/usr/bin/env python3\n"
        "try:\n    from conduct_cli.hooks.precompact import main; main()\n"
        "except (ImportError, ModuleNotFoundError): import sys; sys.exit(0)\n"
    ),
    "session-start": (
        "#!/usr/bin/env python3\n"
        "try:\n    from conduct_cli.hooks.session_start import main; main()\n"
        "except (ImportError, ModuleNotFoundError): import sys; sys.exit(0)\n"
    ),
}

# Detect whether an installed hook is already a thin launcher (contains the import)
def _is_thin_launcher(path: Path) -> bool:
    try:
        text = path.read_text()
        return "from conduct_cli.hooks." in text
    except Exception:
        return False




# ── Policy engine (also embedded in hook_template.py for standalone use) ──────

import json as _json
import re as _re

def _bash_command_words(cmd: str) -> list[str]:
    """First token of each pipeline / conditional / semicolon-separated segment.

    Argument bodies, heredoc contents, and quoted strings are ignored — so a
    privilege-escalation matcher firing on the literal word inside a body
    payload (issue body, commit message, file write) is no longer possible.
    Returns lower-cased command words for case-insensitive matching.
    """
    import shlex as _shlex
    words: list[str] = []
    if not cmd:
        return words
    # Split on bash control operators (||, &&, |, ;, & and bg/fg keywords).
    for segment in _re.split(r"\|\||&&|[|;&\n]+|\bthen\b|\belse\b|\bdo\b", cmd):
        seg = segment.strip()
        if not seg:
            continue
        try:
            parts = _shlex.split(seg)
        except ValueError:
            continue
        if parts:
            # Strip env-var prefixes (FOO=bar bin baz → bin)
            for p in parts:
                if "=" in p and not p.startswith(("-", "/")):
                    continue
                words.append(p.lower())
                break
    return words


def _check_policy(tool_name, tool_input, tokens_before=0, ai_tool=""):
    """Return (matched_rule, action, rule_id, message) or (None, 'allow', None, None)."""
    policy = _load_policy()
    if not policy.get("rules"):
        return None, "allow", None, None

    rules      = policy.get("rules", [])
    input_text = _json.dumps(tool_input)
    path_fields = [str(tool_input.get(f, "")) for f in ["file_path", "path", "command"]]
    # Extract command words only when bash is involved — empty list for other tools.
    command_words = (
        _bash_command_words(str(tool_input.get("command", "")))
        if tool_name.lower() == "bash" else []
    )

    for rule in rules:
        match_tool = (rule.get("match_tool") or "*").lower()
        if match_tool != "*":
            if tool_name not in expand_match_tool(match_tool):
                continue
        match_ai = rule.get("match_ai_tool")
        if match_ai:
            surfaces = [s.strip().lower() for s in match_ai.split(",")]
            if not any(s in ai_tool.lower() for s in surfaces):
                continue
        # New: structural match against the actual binary being invoked.
        # Single string or list of strings; case-insensitive equality.
        cw = rule.get("match_command_word")
        if cw:
            deny = [w.lower() for w in (cw if isinstance(cw, list) else [cw])]
            if not any(w in deny for w in command_words):
                continue
        pattern = rule.get("match_pattern")
        if pattern:
            try:
                if not _re.search(pattern, input_text, _re.IGNORECASE):
                    continue
            except _re.error:
                continue
        path_pattern = rule.get("match_path_pattern")
        if path_pattern:
            try:
                if not any(_re.search(path_pattern, f, _re.IGNORECASE) for f in path_fields if f):
                    continue
            except _re.error:
                continue
        min_tokens = rule.get("match_tokens_before_gt")
        if min_tokens is not None:
            if tokens_before <= int(min_tokens):
                continue
        action  = rule.get("action", "audit")
        rule_id = rule.get("rule_id", "unknown")
        message = rule.get("message") or f"Policy violation: {rule_id}"
        return rule, action, rule_id, message

    return None, "allow", None, None


# ── Python interpreter selection ─────────────────────────────────────────────

def _best_python() -> str:
    """Return the best available Python 3 interpreter path.
    Prefers 3.11+ (Homebrew) over Apple's system Python 3.9 which has
    restrictions that cause the hook to fail silently."""
    import shutil
    for candidate in ("python3.13", "python3.12", "python3.11", "python3.10"):
        found = shutil.which(candidate)
        if found:
            return found
    return sys.executable


# ── Hook write helper ─────────────────────────────────────────────────────────

def _write_hook(path: Path) -> None:
    """Write a thin launcher to path (or legacy template for backward compat), then validate.

    Thin launcher (new default):
        #!/usr/bin/env python3
        from conduct_cli.hooks.pretooluse import main; main()

    If conduct_cli.hooks is not importable (e.g. editable install not set up),
    falls back to writing the full template so hooks still work.
    On syntax failure: restores previous hook (or writes a safe stub) so the
    system is never left without a working hook file.
    """
    import py_compile
    backup = None
    if path.exists():
        backup = path.read_text()
    path.parent.mkdir(parents=True, exist_ok=True)

    content = _THIN_LAUNCHERS["pretooluse"]

    path.write_text(content)
    path.chmod(0o755)
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        if backup is not None:
            path.write_text(backup)
        else:
            path.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n")
        raise RuntimeError(
            f"hook.py failed syntax check — previous hook restored.\n{exc}"
        ) from exc


def _write_session_hook(path: Path, launcher_key: str) -> None:
    content = _THIN_LAUNCHERS[launcher_key]
    path.write_text(content)
    path.chmod(0o755)


def _install_session_hooks() -> None:
    """Write PreCompact + SessionStart + Stop hook scripts and register them in ~/.claude/settings.json."""
    python = _best_python()

    precompact_path    = GUARD_DIR / "guard-precompact.py"
    session_start_path = GUARD_DIR / "guard-session-start.py"
    stop_path          = GUARD_DIR / "guard-stop.py"

    _write_session_hook(precompact_path,    "precompact")
    _write_session_hook(session_start_path, "session-start")
    _write_session_hook(stop_path,          "stop")

    claude_settings = Path.home() / ".claude" / "settings.json"
    settings: dict = {}
    if claude_settings.exists():
        try:
            settings = json.loads(claude_settings.read_text())
        except Exception:
            pass

    hooks = settings.setdefault("hooks", {})

    pre_cmd = f"{python} {precompact_path}"
    compact_hooks = hooks.setdefault("PreCompact", [])
    if not any(pre_cmd in str(e) for h in compact_hooks for e in h.get("hooks", [])):
        compact_hooks.append({"hooks": [{"type": "command", "command": pre_cmd}]})

    start_cmd = f"{python} {session_start_path}"
    start_hooks = hooks.setdefault("SessionStart", [])
    if not any(start_cmd in str(e) for h in start_hooks for e in h.get("hooks", [])):
        start_hooks.append({"hooks": [{"type": "command", "command": start_cmd}]})

    claude_settings.parent.mkdir(parents=True, exist_ok=True)
    claude_settings.write_text(json.dumps(settings, indent=2) + "\n")


# ── Guard config helpers ──────────────────────────────────────────────────────

_PERSONA_LABELS = {
    "conservative": "Conservative  — production-safe, default deny",
    "standard":     "Standard      — engineering teams, balanced",
    "developer":    "Developer     — local dev, audit-first",
}


def _ensure_persona(workspace_id: str, base_url: str) -> str:
    """Prompt for persona if none is set yet. Saves choice to guard config and API.

    Returns the active persona name. Skips prompt silently if already set.
    """
    agent_token = _default_agent_token() or ""
    cfg = _load_guard_config()
    if cfg.get("persona"):
        return cfg["persona"]

    print(f"\n{BOLD}Choose a policy persona for your agents:{RESET}")
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
        _req(
            "PATCH",
            f"{base_url}/guard/config/persona",
            body={"persona": chosen},
            token=agent_token or None,
        )
    except Exception:
        pass  # non-fatal — local config still records the choice

    # Persist locally so we skip the prompt on subsequent syncs
    cfg = _load_guard_config()
    cfg["persona"] = chosen
    _save_guard_config(cfg)

    print(f"  {GREEN}Persona set:{RESET} {chosen.capitalize()}")
    return chosen


def _load_guard_config(workspace_id: str | None = None) -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_guard_config(data: dict, workspace_id: str | None = None):
    CONDUCT_HOME.mkdir(parents=True, exist_ok=True)
    existing = {}
    if CONFIG_PATH.exists():
        try:
            existing = json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    existing.update(data)
    CONFIG_PATH.write_text(json.dumps(existing, indent=2))
    CONFIG_PATH.chmod(0o600)


def _require_guard_config() -> dict:
    cfg = _load_guard_config()
    ws = cfg.get("workspace_id") or cfg.get("workspace")
    if not cfg or not ws:
        print(f"{RED}Guard not connected. Run: conduct login{RESET}", file=sys.stderr)
        sys.exit(0)
    if not cfg.get("agent_token"):
        print(f"{RED}Guard config is missing credentials. Run: conduct login{RESET}", file=sys.stderr)
        sys.exit(0)
    return cfg


def _api_url(cfg: dict) -> str:
    return cfg.get("api_url", "https://api.conductai.ai").rstrip("/")


# ── MCP registration ──────────────────────────────────────────────────────────

# Tools that support mcpServers JSON — only write if the config file already exists
def _vscode_mcp_paths() -> list[tuple[Path, str]]:
    """VS Code Copilot MCP config locations (macOS + Linux). Only if Copilot is installed."""
    ext_dir = Path.home() / ".vscode" / "extensions"
    if not ext_dir.exists() or not any(p.name.startswith("github.copilot") for p in ext_dir.iterdir() if p.is_dir()):
        return []
    candidates = [
        Path.home() / "Library" / "Application Support" / "Code" / "User" / "mcp.json",
        Path.home() / ".config" / "Code" / "User" / "mcp.json",
    ]
    return [(p, "VS Code Copilot") for p in candidates if p.parent.exists()]

_MCP_TARGETS = [
    (Path.home() / ".claude"   / "settings.json", "Claude Code"),
    (Path.home() / ".cursor"   / "mcp.json",       "Cursor"),
    (Path.home() / ".windsurf" / "mcp.json",        "Windsurf"),
    (Path.home() / ".codex"    / "mcp.json",        "Codex"),
    # ~/.copilot/mcp-config.json handled separately by _patch_copilot_mcp (SSE + token)
    # Claude Desktop — only if already installed
    (Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json", "Claude Desktop"),
    (Path.home() / "AppData"  / "Roaming" / "Claude" / "claude_desktop_config.json",             "Claude Desktop"),
]


def _register_mcp(workspace_id: str, agent_token: str, api_url: str, dry_run: bool = False) -> None:
    """Write conductguard + agent-booster MCP entries into every AI tool config found.

    Credentials are NOT stored in the MCP config — the server reads them from
    ~/.conduct/config.json at startup, which is written by guard sync.
    """
    import shutil
    servers: dict[str, dict] = {
        "conductguard": {"command": "conductguard-mcp"},
    }
    # Register agent-booster only if the binary is available
    if shutil.which("booster"):
        servers["agent-booster"] = {"command": "booster", "args": ["serve"]}

    vscode_paths = _vscode_mcp_paths()
    targets = list(_MCP_TARGETS) + vscode_paths
    vscode_cfg_paths = {p for p, _ in vscode_paths}
    found_any = False
    for cfg_path, label in targets:
        if not cfg_path.exists():
            # Create mcp.json for VS Code if Copilot is confirmed installed
            if cfg_path in vscode_cfg_paths:
                cfg_path.write_text("{}")
            else:
                continue
        found_any = True
        try:
            existing = json.loads(cfg_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}
        mcp = existing.setdefault("mcpServers", {})
        changed = False
        for name, entry in servers.items():
            if mcp.get(name) == entry:
                print(f"  {GRAY}{name} MCP already registered in {label}{RESET}")
            else:
                mcp[name] = entry
                changed = True
                print(f"  {GREEN}{name} MCP registered in {label}{RESET}")
        if changed:
            cfg_path.write_text(json.dumps(existing, indent=2))
    if not found_any:
        print(f"  {GRAY}No AI tool configs found for MCP registration{RESET}")

    # GitHub Copilot uses SSE + Bearer token (can't run local stdio process via mcp-config.json)
    _patch_copilot_mcp(agent_token, api_url)

    # Claude Desktop doesn't source shell env — patch apiBaseUrl directly in config
    # so all LLM calls route through the Guard proxy (PII blocking, spend limits, audit).
    _patch_claude_desktop_proxy(api_url, agent_token)

    # Cursor global rules — write Guard policies as user rules so they apply across all projects.
    _patch_cursor_global_rules()
    _patch_tool_instruction_files(agent_token, api_url, dry_run=dry_run)


def _patch_claude_desktop_proxy(api_url: str, agent_token: str) -> None:
    """Patch Claude Desktop config to route LLM calls through the Guard proxy.

    Claude Desktop reads apiBaseUrl from its config JSON — it does not source
    shell env vars, so ANTHROPIC_BASE_URL has no effect. We write the proxy
    URL directly so PII blocking, spend limits, and audit apply to Desktop too.
    """
    proxy_url = f"{api_url}/proxy/anthropic"
    candidates = [
        Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
    ]
    for cfg_path in candidates:
        if not cfg_path.exists():
            continue
        try:
            cfg = json.loads(cfg_path.read_text())
        except (json.JSONDecodeError, OSError):
            cfg = {}
        current = cfg.get("apiBaseUrl", "")
        if current == proxy_url:
            print(f"  {GRAY}Claude Desktop proxy already set → {proxy_url}{RESET}")
            continue
        cfg["apiBaseUrl"] = proxy_url
        cfg_path.write_text(json.dumps(cfg, indent=2))
        print(f"  {GREEN}Claude Desktop proxy set → {proxy_url}{RESET}")
        print(f"  {YELLOW}Restart Claude Desktop for proxy routing to take effect{RESET}")


def _patch_copilot_mcp(agent_token: str, api_url: str) -> None:
    """Keep ~/.copilot/mcp-config.json and any .mcp.json in cwd in sync with current agent token."""
    import shutil
    sse_entry = {
        "type": "http",
        "url": f"{api_url}/guard/mcp",
        "headers": {"Authorization": f"Bearer {agent_token}"},
    }
    booster_entry = {"command": "booster", "args": ["serve"]} if shutil.which("booster") else None

    # ~/.copilot/mcp-config.json (global Copilot config)
    global_path = Path.home() / ".copilot" / "mcp-config.json"
    if global_path.exists():
        _write_mcp_file(global_path, "conduct-guard", sse_entry, booster_entry, "GitHub Copilot (global)")

    # .mcp.json in cwd (project-level, picked up by VS Code Copilot)
    local_path = Path.cwd() / ".mcp.json"
    if local_path.exists():
        _write_mcp_file(local_path, "conduct-guard", sse_entry, booster_entry, "GitHub Copilot (.mcp.json)")


def _write_mcp_file(
    cfg_path: Path,
    guard_key: str,
    sse_entry: dict,
    booster_entry: dict | None,
    label: str,
) -> None:
    try:
        cfg = json.loads(cfg_path.read_text())
    except (json.JSONDecodeError, OSError):
        cfg = {}
    mcp = cfg.setdefault("mcpServers", {})
    changed = False
    if mcp.get(guard_key) != sse_entry:
        mcp[guard_key] = sse_entry
        changed = True
        print(f"  {GREEN}conduct-guard MCP registered in {label}{RESET}")
    else:
        print(f"  {GRAY}conduct-guard MCP already registered in {label}{RESET}")
    if booster_entry and mcp.get("agent-booster") != booster_entry:
        mcp["agent-booster"] = booster_entry
        changed = True
    if changed:
        cfg_path.write_text(json.dumps(cfg, indent=2))


_GUARD_RULES_TEXT = (Path(__file__).parent / "guard_policy.md").read_text().rstrip()


def _patch_cursor_global_rules() -> None:
    """Write ConductGuard policy rules into Cursor's global user rules setting.

    Cursor IDE stores global rules in settings.json under cursor.rules.user —
    a plain text string injected as system context for every conversation.
    This is soft enforcement (prompt-level), not structural like Claude Code hooks,
    but ensures Guard policies are visible to the model across all Cursor projects.
    """
    GUARD_RULES = _GUARD_RULES_TEXT

    candidates = [
        Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "settings.json",
        Path.home() / ".config" / "Cursor" / "User" / "settings.json",
        Path.home() / "AppData" / "Roaming" / "Cursor" / "User" / "settings.json",
    ]
    for settings_path in candidates:
        if not settings_path.exists():
            continue
        try:
            cfg = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            cfg = {}
        existing = cfg.get("cursor.rules.user", "")
        if "ConductGuard" in existing:
            print(f"  {GRAY}Cursor global rules already contain ConductGuard policy{RESET}")
            continue
        cfg["cursor.rules.user"] = (existing + "\n\n" + GUARD_RULES).strip()
        settings_path.write_text(json.dumps(cfg, indent=2))
        print(f"  {GREEN}Cursor global rules updated with ConductGuard policy{RESET}")


def _patch_tool_instruction_files(agent_token: str, api_url: str, dry_run: bool = False) -> None:
    """Write ConductGuard policy block into instruction files for all AI tools.

    Targets:
      CLAUDE.md                         — Claude Code + Claude Desktop
      .github/copilot-instructions.md   — Copilot + VS Code
      AGENTS.md                         — Codex CLI + Codex Desktop
      .cursorrules                      — Cursor
      .windsurfrules                    — Windsurf

    Merge strategy (never clobbers existing content):
      First sync : appends block between <!-- ConductGuard --> markers
      Re-sync    : replaces only the block, leaves surrounding content untouched
    """
    import re as _re

    MARKER_START = "<!-- ConductGuard — managed by conduct guard sync -->"
    MARKER_END   = "<!-- /ConductGuard -->"
    GUARD_RULES  = _GUARD_RULES_TEXT

    # Guard-only for now — team-os instructions are hidden pending redesign.
    # This block just ensures every AI tool knows to invoke Guard via hooks
    # or the conduct-guard MCP before taking action.
    guard_block = "\n".join([MARKER_START, "## ConductGuard Policy", GUARD_RULES, MARKER_END])

    repo_root: Path | None = None
    for parent in [Path.cwd(), *Path.cwd().parents]:
        if (parent / ".git").exists() or (parent / ".github").is_dir():
            repo_root = parent
            break

    # (repo path, global fallback, label)
    targets = [
        (repo_root / "CLAUDE.md"                           if repo_root else None, Path.home() / "CLAUDE.md",                           "CLAUDE.md"),
        (repo_root / ".github" / "copilot-instructions.md" if repo_root else None, Path.home() / ".github" / "copilot-instructions.md", "Copilot instructions"),
        (repo_root / "AGENTS.md"                           if repo_root else None, Path.home() / ".codex"   / "instructions.md",        "AGENTS.md"),
        (repo_root / ".cursorrules"                        if repo_root else None, Path.home() / ".cursor"  / "rules" / "conduct.md",   ".cursorrules"),
        (repo_root / ".windsurfrules"                      if repo_root else None, Path.home() / ".windsurf"/ "rules" / "conduct.md",   ".windsurfrules"),
    ]
    # Tolerate legacy marker variants (e.g. ", do not edit this block") so re-sync
    # replaces old blocks in place instead of appending a second one.
    pattern = _re.compile(r"<!-- ConductGuard[^\n]*-->.*?<!-- /ConductGuard -->", _re.DOTALL)

    for repo_path, global_path, label in targets:
        path = repo_path if (repo_path and repo_path.exists()) else global_path
        if not path.exists() and repo_path:
            path = repo_path
        existing = path.read_text() if path.exists() else ""
        if pattern.search(existing):
            updated = pattern.sub(guard_block, existing)
            if dry_run:
                if updated == existing:
                    print(f"  [dry-run] No change: {path}")
                else:
                    print(f"  [dry-run] Would write: {path}")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                if updated == existing:
                    print(f"  {GRAY}{label} already up to date{RESET}")
                else:
                    path.write_text(updated)
                    print(f"  {GREEN}{label} updated{RESET}")
        else:
            new_content = (existing.rstrip() + ("\n\n" if existing.strip() else "") + guard_block + "\n").lstrip()
            if dry_run:
                if new_content == existing:
                    print(f"  [dry-run] No change: {path}")
                else:
                    print(f"  [dry-run] Would write: {path}")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new_content)
                print(f"  {GREEN}{label} — ConductGuard block added{RESET}")


def _reset_tool_instruction_files() -> None:
    """Remove ConductGuard blocks from all instruction files."""
    import re as _re
    MARKER_RE = _re.compile(
        r"\n?<!-- ConductGuard -->\n.*?<!-- /ConductGuard -->\n?",
        _re.DOTALL,
    )
    targets = [
        Path.home() / "CLAUDE.md",
        Path.cwd() / "CLAUDE.md",
        Path.cwd() / ".github" / "copilot-instructions.md",
        Path.cwd() / "AGENTS.md",
        Path.cwd() / ".cursorrules",
        Path.cwd() / ".windsurfrules",
    ]
    removed = 0
    for p in targets:
        if not p.exists():
            continue
        original = p.read_text(encoding="utf-8")
        cleaned = MARKER_RE.sub("", original).strip()
        if cleaned != original.strip():
            p.write_text(cleaned + "\n", encoding="utf-8")
            print(f"  {GREEN}Removed ConductGuard block: {p}{RESET}")
            removed += 1
        else:
            print(f"  {YELLOW}No ConductGuard block found: {p}{RESET}")
    if removed == 0:
        print("  No ConductGuard blocks found in any instruction files.")


def _install_codex_hook(hook_path: Path) -> None:
    """Register PreToolUse and PostToolUse hooks in ~/.codex/hooks.json."""
    codex_hooks = Path.home() / ".codex" / "hooks.json"
    if not (Path.home() / ".codex").exists():
        return  # Codex not installed

    hooks: dict = {}
    if codex_hooks.exists():
        try:
            hooks = json.loads(codex_hooks.read_text())
        except json.JSONDecodeError:
            hooks = {}

    hook_section = hooks.setdefault("hooks", {})

    # PreToolUse
    pre_cmd = f"{_best_python()} {hook_path}"
    hook_path_str = str(hook_path)
    pre = hook_section.setdefault("PreToolUse", [])
    # Match by hook path so old python3/python3.11 entries are treated as already registered
    pre_already = any(
        hook_path_str in e.get("command", "")
        for h in pre
        for e in h.get("hooks", [])
    )
    changed = False
    if not pre_already:
        pre.append({"matcher": ".*", "hooks": [{"type": "command", "command": pre_cmd}]})
        changed = True
    else:
        # Update existing entry to use current sys.executable
        for h in pre:
            for e in h.get("hooks", []):
                if hook_path_str in e.get("command", "") and e["command"] != pre_cmd:
                    e["command"] = pre_cmd
                    changed = True

    # PostToolUse
    post_cmd = f"{_best_python()} {hook_path} post"
    post = hook_section.setdefault("PostToolUse", [])
    # Remove stale conductguard-post entries registered by older CLI versions
    stale = "conductguard-post"
    cleaned = False
    for h in post:
        before = len(h.get("hooks", []))
        h["hooks"] = [e for e in h.get("hooks", []) if e.get("command") != stale]
        if len(h["hooks"]) < before:
            cleaned = True
    post[:] = [h for h in post if h.get("hooks")]
    post_already = any(
        hook_path_str in e.get("command", "")
        for h in post
        for e in h.get("hooks", [])
    )
    if not post_already:
        post.append({"matcher": ".*", "hooks": [{"type": "command", "command": post_cmd}]})
        changed = True
    if cleaned:
        changed = True

    if changed:
        codex_hooks.parent.mkdir(parents=True, exist_ok=True)
        codex_hooks.write_text(json.dumps(hooks, indent=2))
        if not pre_already:
            print(f"  {GREEN}Codex PreToolUse hook registered{RESET}")
        if not post_already or cleaned:
            print(f"  {GREEN}Codex PostToolUse hook registered{RESET}")
    else:
        print(f"  {GRAY}Codex hooks already registered{RESET}")


# ── HTTP helpers (no third-party deps — mirrors api.py style) ─────────────────

def _default_agent_token() -> str | None:
    """Read the agent_token minted by `conduct login` from ~/.conduct/config.json.
    This is the CLI's single canonical credential — every call to the central
    API should carry it via Authorization: Bearer."""
    try:
        cfg_path = Path.home() / ".conduct" / "config.json"
        if cfg_path.exists():
            return json.loads(cfg_path.read_text()).get("agent_token") or None
    except Exception:
        pass
    return None


def _req(method: str, url: str, body=None, token: str = None, timeout: int = 20) -> dict:
    # If no explicit token passed, fall back to the login-minted agent_token.
    if not token:
        token = _default_agent_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw).get("detail", raw)
        except Exception:
            detail = raw
        print(f"{RED}HTTP {e.code}: {detail} [{url}]{RESET}")
        sys.exit(1)
    except Exception:
        print(f"{RED}Could not reach ConductAI API. Check your connection.{RESET}")
        sys.exit(1)



def _save_policy(policy: dict, workspace_id: str | None = None):
    GUARD_DIR.mkdir(parents=True, exist_ok=True)
    POLICY_PATH.write_text(json.dumps(policy, indent=2))


def _load_policy(workspace_id: str | None = None) -> dict:
    try:
        return json.loads(POLICY_PATH.read_text())
    except Exception:
        return {"rules": []}


# ── since-string parser ───────────────────────────────────────────────────────

def _parse_since(since_str: str) -> str:
    """Convert '7d', '24h', '1h', '30d' to an ISO-8601 UTC timestamp string."""
    unit  = since_str[-1].lower()
    value = int(since_str[:-1])
    delta_map = {"h": timedelta(hours=value), "d": timedelta(days=value)}
    if unit not in delta_map:
        print(f"{RED}Invalid --since value '{since_str}'. Use: 1h, 24h, 7d, 30d{RESET}")
        sys.exit(1)
    return (datetime.now(tz=timezone.utc) - delta_map[unit]).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Hook helpers ─────────────────────────────────────────────────────────────

def _install_claude_hook(hook_path: Path) -> None:
    """Register PreToolUse and PostToolUse hooks in ~/.claude/settings.json."""
    claude_settings = Path.home() / ".claude" / "settings.json"
    settings: dict = {}
    if claude_settings.exists():
        try:
            settings = json.loads(claude_settings.read_text())
        except json.JSONDecodeError:
            settings = {}

    hooks = settings.setdefault("hooks", {})

    # PreToolUse — existing hook script
    pre = hooks.setdefault("PreToolUse", [])
    pre_cmd = f"{_best_python()} {hook_path}"
    hook_path_str = str(hook_path)
    pre_already = any(
        hook_path_str in e.get("command", "")
        for h in pre
        for e in h.get("hooks", [])
    )
    changed = False
    if not pre_already:
        pre.append({"matcher": ".*", "hooks": [{"type": "command", "command": pre_cmd}]})
        changed = True
    else:
        # Update existing entry to use current sys.executable
        for h in pre:
            for e in h.get("hooks", []):
                if hook_path_str in e.get("command", "") and e["command"] != pre_cmd:
                    e["command"] = pre_cmd
                    changed = True

    # PostToolUse
    post = hooks.setdefault("PostToolUse", [])
    post_cmd = f"{_best_python()} {hook_path} post"
    # Remove stale conductguard-post entries registered by older CLI versions
    stale = "conductguard-post"
    cleaned = False
    for h in post:
        before = len(h.get("hooks", []))
        h["hooks"] = [e for e in h.get("hooks", []) if e.get("command") != stale]
        if len(h["hooks"]) < before:
            cleaned = True
    post[:] = [h for h in post if h.get("hooks")]
    post_already = any(
        hook_path_str in e.get("command", "")
        for h in post
        for e in h.get("hooks", [])
    )
    if not post_already:
        post.append({"matcher": ".*", "hooks": [{"type": "command", "command": post_cmd}]})
        changed = True
    if cleaned:
        changed = True

    # Stop — capture session for team memory only (guard sync removed — exits 1 without TTY)
    stop = hooks.setdefault("Stop", [])

    python = _best_python()
    stop_path = GUARD_DIR / "guard-stop.py"
    mem_cmd = f"{python} {stop_path}"
    mem_already = any(
        "guard-stop" in e.get("command", "")
        for h in stop
        for e in h.get("hooks", [])
    )
    if not mem_already and stop_path.exists():
        stop.append({"hooks": [{"type": "command", "command": mem_cmd}]})
        changed = True

    if changed:
        claude_settings.parent.mkdir(parents=True, exist_ok=True)
        claude_settings.write_text(json.dumps(settings, indent=2))
        if not pre_already:
            print(f"  {GREEN}Claude Code PreToolUse hook registered{RESET}")
        if not post_already or cleaned:
            print(f"  {GREEN}Claude Code PostToolUse hook registered{RESET}")
        if not mem_already:
            print(f"  {GREEN}Claude Code Stop hook registered (team memory capture){RESET}")
    else:
        print(f"  {GRAY}Claude Code hooks already registered{RESET}")


# ── Commands ──────────────────────────────────────────────────────────────────

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

    result = _req(
        "GET",
        f"{server}/guard/config/installed?workspace_id={workspace_id}",
        token=agent_token or None,
    )

    if not result.get("installed"):
        print(f"  {GRAY}Guard not installed for this workspace — skipping{RESET}")
        return

    resp_agent_token = result.get("agent_token") or agent_token
    user_email       = result.get("user_email") or ""
    clerk_user_id    = result.get("clerk_user_id") or ""

    # Persona selection — prompt once, skip if already chosen

    # Persist unified config — single ~/.conduct/config.json
    import time as _time
    _save_guard_config({
        "workspace_id":          workspace_id,
        "agent_token":           resp_agent_token,
        "user_email":            user_email,
        "clerk_user_id":         clerk_user_id,
        "api_url":               server,
        "last_synced_at":        _time.time(),
    })

    # Download policies
    try:
        policy = _req(
            "GET",
            f"{server}/guard/policies/sync?workspace_id={workspace_id}",
            token=agent_token,
        )
        _save_policy(policy)
        # Mirror fail_mode into guard config so the hook can enforce it
        # even when POLICY_PATH is missing or unreadable.
        cfg = _load_guard_config()
        cfg["fail_mode"] = policy.get("fail_mode", "fail_closed")
        cfg["advisory_mode"] = policy.get("advisory_mode", False)
        _save_guard_config(cfg)
        rule_count = len(policy.get("rules", []))
        advisory_label = " · advisory" if cfg["advisory_mode"] else ""
        print(f"  {GREEN}Guard policies:{RESET} {rule_count} rule(s) active · fail mode: {cfg['fail_mode']}{advisory_label}")
    except SystemExit:
        rule_count = 0

    # Write hook script
    hook_path = GUARD_DIR / "hook.py"
    _write_hook(hook_path)

    # Install PreToolUse hooks — Claude Code + Codex (real interception)
    _install_claude_hook(hook_path)
    _install_codex_hook(hook_path)

    # Register MCP in all found AI tools — Cursor/Windsurf (advisory)
    _register_mcp(workspace_id, agent_token or "", server)

    _cd = next((t for t in _detect_ai_tools() if t["name"] == "claude-desktop" and not t.get("proxy_routed")), None)
    if _cd:
        print(f"  {CYAN}Claude Desktop detected — patching apiBaseUrl to route through Guard proxy{RESET}")
        _patch_claude_desktop_proxy(server, agent_token or "")

    # Install session persistence hooks (PreCompact + SessionStart)
    try:
        _install_session_hooks()
    except Exception:
        pass

    # Write signing key if provided by the admin at onboarding time.
    signing_key_hex = getattr(args, "signing_key", None)
    if signing_key_hex:
        _write_signing_key(signing_key_hex)

    # Start watch daemon — auto-discovers agents every 15 min, no user action needed.
    try:
        import subprocess as _sp, sys as _sys
        running, _ = _is_watch_running()
        if not running:
            log_file = open(_WATCH_LOG, "a")
            proc = _sp.Popen(
                [_sys.executable, "-c",
                 "from conduct_cli.guard import _watch_loop; _watch_loop()"],
                start_new_session=True,
                stdout=log_file,
                stderr=log_file,
            )
            _WATCH_PID.write_text(str(proc.pid))
            print(f"  {GREEN}Guard watch:{RESET} background discovery daemon started (pid {proc.pid})")
        else:
            print(f"  {GREEN}Guard watch:{RESET} already running")
    except Exception:
        pass  # non-fatal


def _write_signing_key(hex_key: str) -> None:
    """Write a hex-encoded signing key to ~/.conduct/signing.key.

    Validates that the path resolves within GUARD_DIR (no traversal) and
    that the value is a valid 64-char hex string (32 bytes).
    """
    import re as _re
    signing_key_path = GUARD_DIR / "signing.key"

    # Path traversal guard.
    try:
        resolved = signing_key_path.resolve()
        resolved.relative_to(GUARD_DIR.resolve())
    except (ValueError, RuntimeError):
        print(f"  {RED}Signing key path rejected (traversal check failed).{RESET}")
        return

    # Must be exactly 64 hex characters (32 bytes).
    if not _re.fullmatch(r"[0-9a-fA-F]{64}", hex_key.strip()):
        print(f"  {RED}Invalid signing key: expected 64 hex characters.{RESET}")
        return

    GUARD_DIR.mkdir(parents=True, exist_ok=True)
    signing_key_path.write_text(hex_key.strip())
    print(f"  {GREEN}Signing key written:{RESET} {signing_key_path}")


def cmd_guard_join(args):
    invite_code = args.invite_code

    # Prompt for email if not supplied
    email = getattr(args, "email", None) or input("Email address: ").strip()
    if not email:
        print(f"{RED}Email is required.{RESET}")
        sys.exit(1)

    # Use configured API URL or default
    existing_cfg = _load_guard_config()
    base_url     = existing_cfg.get("api_url", "https://api.conductai.ai").rstrip("/")

    print(f"\nJoining workspace with invite code {CYAN}{invite_code}{RESET}…")

    payload = {"invite_code": invite_code, "email": email}
    result = _req("POST", f"{base_url}/guard/join", body=payload)

    workspace_id = result["workspace_id"]
    agent_token_install = result.get("agent_token", "")
    policy       = result.get("policy", {"workspace_id": workspace_id, "version": "1", "rules": []})

    # Download and persist policy
    _save_policy(policy)
    rule_count = len(policy.get("rules", []))
    print(f"  {GREEN}Policy downloaded:{RESET} {rule_count} rule(s)")

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
    _save_guard_config(cfg)

    # Write hook script
    hook_path = GUARD_DIR / "hook.py"
    _write_hook(hook_path)
    print(f"  {GREEN}Hook script written:{RESET} {hook_path}")

    # Install PreToolUse hook in ~/.claude/settings.json
    _install_claude_hook(hook_path)

    print(
        f"\n{BOLD}{GREEN}Guard connected.{RESET} "
        f"{rule_count} polic{'y' if rule_count == 1 else 'ies'} active.\n"
        f"Your AI tool calls will now be checked against team policies."
    )


def _is_anthropic_proxied() -> bool:
    url = os.environ.get("ANTHROPIC_BASE_URL", "")
    return "conductai.ai" in url or "conduct" in url.lower()


def _is_openai_proxied() -> bool:
    url = os.environ.get("OPENAI_BASE_URL", "")
    return "conductai.ai" in url or "conduct" in url.lower()


def _detect_ai_tools() -> list[dict]:
    """Return list of detected AI coding tools with mcp_registered, hook_registered, proxy_routed."""
    home = Path.home()

    def _check_json_mcp(path: Path) -> bool:
        try:
            d = json.loads(path.read_text()) if path.exists() else {}
            return any("conduct" in k for k in d.get("mcpServers", {}))
        except Exception:
            return False

    def _check_json_hook(path: Path) -> bool:
        try:
            d = json.loads(path.read_text()) if path.exists() else {}
            hooks = d.get("hooks", {})
            pre = hooks.get("PreToolUse", [])
            return any("conductguard" in str(h) or "conduct" in str(h).lower() for h in pre)
        except Exception:
            return False

    def _check_toml_str(path: Path, needle: str) -> bool:
        try:
            return needle in (path.read_text() if path.exists() else "")
        except Exception:
            return False

    def _claude_desktop_proxied() -> bool:
        candidates = [
            home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
        ]
        for p in candidates:
            if p.exists():
                try:
                    url = json.loads(p.read_text()).get("apiBaseUrl", "")
                    return "conductai.ai" in url or "conduct" in url.lower()
                except Exception:
                    pass
        return False

    tools = []

    claude_dir = home / ".claude"
    if claude_dir.exists():
        settings = claude_dir / "settings.json"
        tools.append({
            "name": "claude-code",
            "mcp_registered": _check_json_mcp(settings),
            "hook_registered": _check_json_hook(settings),
            "proxy_routed": _is_anthropic_proxied(),
        })

    codex_dir = home / ".codex"
    if codex_dir.exists():
        config = codex_dir / "config.toml"
        is_desktop = _check_toml_str(config, "[desktop]")
        if is_desktop:
            tools.append({
                "name": "codex-desktop",
                "mcp_registered": _check_toml_str(config, "conduct-mcp"),
                "hook_registered": _check_toml_str(config, "conductguard"),
                "proxy_routed": False,
            })
        else:
            tools.append({
                "name": "codex",
                "mcp_registered": _check_toml_str(config, "conduct-mcp"),
                "hook_registered": _check_toml_str(config, "conductguard"),
                "proxy_routed": _is_openai_proxied(),
            })

    cursor_dir = home / ".cursor"
    if cursor_dir.exists():
        tools.append({
            "name": "cursor",
            "mcp_registered": _check_json_mcp(cursor_dir / "mcp.json"),
            "hook_registered": False,
            "proxy_routed": _is_anthropic_proxied(),
        })

    windsurf_dir = home / ".codeium" / "windsurf"
    if windsurf_dir.exists():
        tools.append({
            "name": "windsurf",
            "mcp_registered": _check_json_mcp(windsurf_dir / "mcp_config.json"),
            "hook_registered": False,
            "proxy_routed": _is_anthropic_proxied(),
        })

    claude_desktop_candidates = [
        home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
    ]
    if any(p.exists() for p in claude_desktop_candidates):
        tools.append({
            "name": "claude-desktop",
            "mcp_registered": False,
            "hook_registered": False,
            "proxy_routed": _claude_desktop_proxied(),
        })

    vscode_ext_dir = home / ".vscode" / "extensions"
    copilot_installed = vscode_ext_dir.exists() and any(
        p.name.startswith("github.copilot") for p in vscode_ext_dir.iterdir() if p.is_dir()
    )
    if copilot_installed:
        vscode_candidates = [
            home / "Library" / "Application Support" / "Code" / "User" / "settings.json",
            home / ".config" / "Code" / "User" / "settings.json",
            home / ".vscode" / "settings.json",
        ]
        vscode_settings = next((p for p in vscode_candidates if p.exists()), None)
        try:
            d = json.loads(vscode_settings.read_text()) if vscode_settings else {}
            mcp_reg = any("conduct" in k for k in d.get("mcp", {}).get("servers", {}))
        except Exception:
            mcp_reg = False
        # Also check ~/.copilot/mcp-config.json (SSE entry written by guard sync)
        if not mcp_reg:
            try:
                copilot_cfg = home / ".copilot" / "mcp-config.json"
                mcp_reg = "conduct-guard" in json.loads(copilot_cfg.read_text()).get("mcpServers", {})
            except Exception:
                pass
        tools.append({
            "name": "copilot",
            "mcp_registered": mcp_reg,
            "hook_registered": False,
            "proxy_routed": False,
        })

    return tools


def _report_tools_to_server() -> None:
    """Detect AI coding tools on this machine and POST coverage to Guard API. Silent on failure."""
    tools = _detect_ai_tools()

    if not tools:
        return

    try:
        cfg = _load_guard_config()
        base_url = _api_url(cfg)
        email = cfg.get("user_email", "")
        token = cfg.get("agent_token", "")
        if not email:
            return
        conduct_cfg_path = Path.home() / ".conduct" / "config.json"
        conduct_agent_token = ""
        if conduct_cfg_path.exists():
            try:
                conduct_agent_token = json.loads(conduct_cfg_path.read_text()).get("agent_token", "")
            except Exception:
                pass

        payload = json.dumps({"email": email, "tools": tools}).encode()
        headers = {"Content-Type": "application/json"}
        if conduct_agent_token and conduct_agent_token.startswith("cond_live_"):
            headers["Authorization"] = f"Bearer {conduct_agent_token}"
        elif token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            f"{base_url}/guard/developer-tools",
            data=payload,
            headers=headers,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass  # Never surface errors — this is background telemetry


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

    print(f"  {YELLOW}Updates available:{RESET} " + ", ".join(f"{p} {c} → {l}" for p, c, l in stale))
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
        print(f"  {GREEN}Updated:{RESET} " + ", ".join(f"{p} → {l}" for p, _, l in stale))
    except Exception as e:
        print(f"  {YELLOW}Auto-update failed:{RESET} {e} — run: pip install --upgrade {' '.join(p for p,_,_ in stale)}")


def _proactive_token_refresh() -> None:
    """Refresh agent_token if it expires within 5 min. No-op if no refresh_token."""
    cfg = _load_guard_config()
    if not cfg.get("refresh_token"):
        return
    import datetime as _dt, json as _json
    exp = cfg.get("token_expires_at", "")
    try:
        if exp and _dt.datetime.fromisoformat(exp) >= _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=5):
            return  # still valid
    except ValueError:
        pass
    api_url = _api_url(cfg)
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
        _save_guard_config(cfg)
    except Exception:
        print(f"  {YELLOW}⚠ Token refresh failed — run `conduct login` if sync fails{RESET}")


def cmd_guard_sync(args):
    _proactive_token_refresh()
    cfg          = _require_guard_config()
    workspace_id = cfg.get("workspace_id") or cfg.get("workspace")
    agent_token  = cfg.get("agent_token", "")
    base_url     = _api_url(cfg)
    _token       = agent_token or None

    # Persona selection — prompt once, skip if already chosen

    dry_run = getattr(args, "dry_run", False)

    if getattr(args, "reset_instructions", False):
        print("Removing ConductGuard blocks from instruction files…")
        _reset_tool_instruction_files()
        return

    print(f"{'[dry-run] ' if dry_run else ''}Syncing policy…")
    _check_and_upgrade_packages()

    try:
        policy = _req(
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
        current_policy = _load_policy()
        current_rules = {r["rule_id"]: r for r in current_policy.get("rules", [])}
        new_rules = {r["rule_id"]: r for r in rules}

        added   = [r for r in new_rules   if r not in current_rules]
        removed = [r for r in current_rules if r not in new_rules]
        changed = [
            r for r in new_rules
            if r in current_rules and new_rules[r].get("action") != current_rules[r].get("action")
        ]

        print(f"\n  {BOLD}Dry run — no files written{RESET}")
        print(f"  Rules in policy: {rule_count}")
        if added:
            print(f"\n  {GREEN}+ Added ({len(added)}){RESET}")
            for rid in added:
                r = new_rules[rid]
                print(f"      {rid}  [{r.get('action','?').upper()}]")
        if removed:
            print(f"\n  {RED}- Removed ({len(removed)}){RESET}")
            for rid in removed:
                print(f"      {rid}")
        if changed:
            print(f"\n  ~ Changed action ({len(changed)})")
            for rid in changed:
                old_a = current_rules[rid].get("action", "?")
                new_a = new_rules[rid].get("action", "?")
                print(f"      {rid}  {old_a} → {new_a}")
        if not added and not removed and not changed:
            print(f"  {GREEN}No changes{RESET}")
        return

    _save_policy(policy)
    print(f"  {GREEN}Policy refreshed:{RESET} {rule_count} rule(s)")

    # Refresh member token from server (workspace API key → fresh guard-mt- token).
    # Never rely on the locally-cached value — it may be stale or missing.
    try:
        installed = _req(
            "GET",
            f"{base_url}/guard/config/installed?workspace_id={workspace_id}",
            token=_token,
        )
        fresh_agent_token = installed.get("agent_token") or ""
        if fresh_agent_token:
            cfg["agent_token"] = fresh_agent_token
        if installed.get("user_email"):
            cfg["user_email"] = installed["user_email"]
        if installed.get("clerk_user_id"):
            cfg["clerk_user_id"] = installed["clerk_user_id"]
        _save_guard_config(cfg)
        if not fresh_agent_token and not cfg.get("agent_token"):
            print(f"  {YELLOW}Warning: server returned no token — proxy env may be stale{RESET}")
    except Exception as e:
        print(f"  {YELLOW}Warning: could not refresh token ({e}) — using cached value{RESET}")

    # Write LLM proxy env vars so any AI tool (Claude Code, Cursor, Codex, …)
    # routes through Conduct Guard. Customer-overridable via --proxy-url or
    # CONDUCT_PROXY_URL env var; otherwise fetched from server (workspace_config).
    proxy_url = getattr(args, "proxy_url", None) or os.environ.get("CONDUCT_PROXY_URL")
    if not proxy_url:
        try:
            import urllib.request as _ur, urllib.error as _ue
            _headers = {"Content-Type": "application/json"}
            _token = cfg.get("agent_token", "")
            if _token:
                _headers["Authorization"] = f"Bearer {_token}"
            _r = _ur.Request(f"{base_url}/guard/proxy-config", headers=_headers)
            with _ur.urlopen(_r, timeout=10) as _resp:
                proxy_url = json.loads(_resp.read()).get("conduct_proxy_url") or DEFAULT_PROXY_URL
        except Exception:
            proxy_url = DEFAULT_PROXY_URL
    agent_token = cfg.get("agent_token", "")
    rc_path, newly_sourced = _write_proxy_env(agent_token, proxy_url)
    if agent_token:
        print(f"  {GREEN}Proxy env written:{RESET} ~/.conduct/env → {proxy_url}")
        if newly_sourced:
            print(f"  {CYAN}Run `source {rc_path}` (or open a new shell) to activate.{RESET}")

    _tools = _detect_ai_tools()
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
        print(f"  {CYAN}Claude Desktop detected — patching apiBaseUrl to route through Guard proxy{RESET}")
        _patch_claude_desktop_proxy(cfg.get("api_url", "https://api.conductai.ai"), agent_token)

    # Local key audit — scan known config files for real provider keys that
    # may have been pasted before the dev onboarded onto Conduct. Findings
    # surface in /guard/audit with a 'LOCAL RISK' badge. --no-local-audit
    # skips the scan (CI runners, dev throw-away setups, etc.)
    if not getattr(args, "no_local_audit", False):
        local = _scan_local_keys()
        if local:
            print(f"  {YELLOW}Local risk: {len(local)} pre-existing key(s) found{RESET}")
            for f in local[:5]:
                print(f"    [{f['provider']}] {f['path']}:{f['line']}  {f['masked']}")
            if len(local) > 5:
                print(f"    …{len(local) - 5} more — see /guard/audit")
            _post_local_findings(cfg, base_url, local)

    if getattr(args, "cursor", False):
        _write_cursorrules(policy)


    # Refresh hook script + re-register in all tools
    hook_path = GUARD_DIR / "hook.py"
    _write_hook(hook_path)
    _install_claude_hook(hook_path)
    _install_codex_hook(hook_path)
    cfg2 = _load_guard_config()
    _register_mcp(workspace_id, cfg2.get("agent_token", ""), base_url, dry_run=dry_run)
    try:
        _install_session_hooks()
    except Exception:
        pass
    print(f"  {GREEN}Hook script updated{RESET}")

    # Auto-init Agent Booster if installed but not yet set up in this project
    _ensure_booster(Path.cwd())

    # Capture savings from RTK and Agent Booster
    _report_savings(cfg, base_url)

    # Report AI tool coverage
    try:
        _report_tools_to_server()
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
        print(f"  {CYAN}Discovery daemon started{RESET} — agent inventory updating in background")
    except Exception:
        pass

    print(f"\n{BOLD}Policy refreshed ({rule_count} rule(s)).{RESET}")

    # Print remote MCP URL for any MCP-compatible client
    agent_token = cfg.get("agent_token", "")
    if workspace_id and agent_token:
        mcp_url = "https://api.conductai.ai/guard/mcp"
        masked = agent_token[:13] + "•" * 20
        print(f"\n{BOLD}MCP server{RESET} (Claude.ai, Copilot, Cursor, Windsurf, any MCP client):")
        print(f"  URL:    {CYAN}{mcp_url}{RESET}")
        print(f"  Auth:   {CYAN}Bearer {masked}{RESET}  {GRAY}(run `conduct token` to reveal){RESET}\n")


CONDUCT_DIR        = Path.home() / ".conduct"
PROXY_ENV_FILE     = CONDUCT_DIR / "env"
PROXY_OVERRIDE     = CONDUCT_DIR / "env-override"
DEFAULT_PROXY_URL  = "https://api.conductai.ai/proxy"
SHELL_RC_MARKER    = "# Conduct Guard Proxy — managed by `conduct guard sync`"
SHELL_SOURCE_LINE  = "[ -f ~/.conduct/env ] && . ~/.conduct/env"


# ── Local key audit ──────────────────────────────────────────────────────────
# Patterns that match real provider keys (NOT our member tokens).
# Tuples of (provider, regex). Compiled once at import.
import re as _re

_KEY_PATTERNS = [
    ("anthropic",  _re.compile(r"sk-ant-(?:api\d+-)?[A-Za-z0-9_-]{20,}")),
    ("openai",     _re.compile(r"sk-(?:proj-)?[A-Za-z0-9]{20,}")),   # sk-… (not sk-ant-)
    ("perplexity", _re.compile(r"pplx-[A-Za-z0-9]{20,}")),
]

# Files to scan on the dev's machine.  Strings are user-home-relative paths.
_SCAN_PATHS = [
    "~/.claude/settings.json",
    "~/.claude.json",
    "~/.cursor/mcp.json",
    "~/Library/Application Support/Cursor/User/settings.json",
    "~/.codex/auth.json",
    "~/.codex/config.toml",
    "~/.zshrc",
    "~/.bashrc",
    "~/.bash_profile",
    "~/.profile",
    "~/.config/aider/.aider.conf.yml",
]


def _scan_local_keys() -> list[dict]:
    """Scan the dev's machine for pre-existing real provider API keys.

    Returns a list of findings. Each finding is dict with:
        provider, path, masked, line (best-effort)

    Skips our own guard-mt-… tokens — those aren't real keys.
    """
    findings: list[dict] = []
    home = Path.home()
    for raw in _SCAN_PATHS:
        path = Path(raw.replace("~", str(home)))
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        # OpenAI's sk- pattern will also catch sk-ant-… — order matters:
        # try anthropic first, then strip its hits from the OpenAI pass.
        seen: set[tuple[str, str]] = set()
        for provider, pat in _KEY_PATTERNS:
            for m in pat.finditer(text):
                key = m.group(0)
                if (provider, key) in seen:
                    continue
                if key.startswith("guard-mt-"):
                    continue
                # Compute line number for usability
                line = text[: m.start()].count("\n") + 1
                findings.append({
                    "provider": provider,
                    "path":     str(path),
                    "masked":   key[:10] + "…" + key[-4:],
                    "line":     line,
                })
                seen.add((provider, key))
    return findings


def _post_local_findings(cfg: dict, base_url: str, findings: list[dict]) -> None:
    """Upload findings to /guard/local-audit-findings. Best-effort, never fatal."""
    try:
        _req(
            "POST",
            f"{base_url}/guard/local-audit-findings",
            body={
                "user_email": cfg.get("user_email", ""),
                "findings":   findings,
            },
            token=cfg.get("agent_token", ""),
        )
    except Exception as e:
        print(f"  {YELLOW}Audit upload skipped: {e}{RESET}")


def _write_proxy_env(agent_token: str, proxy_url: str) -> tuple[Path, bool]:
    """Write ~/.conduct/env with the 3 provider env-var pairs and ensure the
    user's shell rc sources it.

    Idempotent — env file rewritten each sync. Shell rc gets the source line
    appended once (guarded by SHELL_RC_MARKER). Returns (rc_path, newly_sourced).
    User-managed customizations go in ~/.conduct/env-override which is sourced
    after the managed file.
    """
    if not agent_token:
        print(f"  {YELLOW}Proxy env skipped — no agent token in config{RESET}")
        return Path(), False

    CONDUCT_DIR.mkdir(parents=True, exist_ok=True)
    token = agent_token  # cond_agt_* used directly as the API key value
    proxy = proxy_url.rstrip("/")

    PROXY_ENV_FILE.write_text("\n".join([
        SHELL_RC_MARKER,
        "# Edit ~/.conduct/env-override to add your own vars — sourced after this file.",
        "",
        f'export ANTHROPIC_BASE_URL="{proxy}"',
        f'export ANTHROPIC_API_KEY="{token}"',
        "",
        f'export OPENAI_BASE_URL="{proxy}/openai"',
        f'export OPENAI_API_KEY="{token}"',
        "",
        f'export PERPLEXITY_BASE_URL="{proxy}/perplexity"',
        f'export PERPLEXITY_API_KEY="{token}"',
        "",
        "[ -f ~/.conduct/env-override ] && . ~/.conduct/env-override",
        "",
    ]))

    shell = os.environ.get("SHELL", "").lower()
    if "zsh" in shell:
        rc = Path.home() / ".zshrc"
    elif "bash" in shell:
        rc = Path.home() / ".bashrc"
    elif "fish" in shell:
        # fish doesn't source bash-style files; tell the user
        print(f"  {YELLOW}fish detected — add this to ~/.config/fish/config.fish:{RESET}")
        print(f"    bass source ~/.conduct/env")
        return Path(), False
    else:
        print(f"  {YELLOW}Unknown shell. Source manually: . ~/.conduct/env{RESET}")
        return Path(), False

    existing = rc.read_text() if rc.exists() else ""
    CLAUDE_ALIAS = "alias claude='env -u ANTHROPIC_BASE_URL claude'"

    if SHELL_RC_MARKER in existing:
        # Already installed — patch in the alias if missing (upgrade path)
        if CLAUDE_ALIAS not in existing:
            rc.write_text(existing.rstrip() + f"\n{CLAUDE_ALIAS}\n")
            return rc, True
        return rc, False

    rc.parent.mkdir(parents=True, exist_ok=True)
    # ponytail: alias strips ANTHROPIC_BASE_URL so Claude Code auth isn't routed
    # through the Guard proxy (Claude Code governs agents; it isn't one)
    addition = (
        f"\n\n{SHELL_RC_MARKER}\n"
        f"{SHELL_SOURCE_LINE}\n"
        f"{CLAUDE_ALIAS}\n"
    )
    rc.write_text(existing.rstrip() + addition if existing else addition.lstrip())
    return rc, True


def _write_cursorrules(policy: dict) -> None:
    """Write active Guard policies into .cursorrules in the current directory."""
    rules = policy.get("rules", [])
    enabled = [r for r in rules if r.get("enabled", True)]
    lines = [
        "# .cursorrules — generated by Conduct AI Guard",
        "# Run `conduct guard sync --cursor` to refresh.",
        "# Do not edit manually — changes will be overwritten.",
        "",
        "## Conduct Guard Policies",
        f"# {len(enabled)} active rule(s) enforced by ConductGuard.",
        "",
    ]
    for r in enabled:
        action = r.get("action", "warn").upper()
        rule_id = r.get("rule_id", "")
        desc = r.get("description") or r.get("message") or ""
        lines.append(f"# [{action}] {rule_id}" + (f" — {desc}" if desc else ""))
        pattern = r.get("pattern")
        if pattern:
            lines.append(f"#   pattern: {pattern}")
    lines += [
        "",
        "## General",
        "# Never include secrets, API keys, or credentials in prompts.",
        "# PII (emails, SSNs, phone numbers) is redacted by Conduct before reaching any model.",
        "# Conduct AI governance is active — all tool calls are audited.",
        "# Independent of Cursor's ownership — policies enforced by your team, not the IDE vendor.",
    ]
    out = Path(".cursorrules")
    out.write_text("\n".join(lines) + "\n")
    print(f"  {GREEN}.cursorrules written:{RESET} {len(enabled)} rule(s) → {out.resolve()}")


def _ensure_booster(root: Path) -> None:
    """Auto-init and background-index booster if installed but not yet set up."""
    import shutil
    import subprocess
    import sys

    if not shutil.which("booster"):
        if sys.version_info < (3, 10):
            print(
                f"  {GRAY}Agent Booster:{RESET} requires Python 3.10+ "
                f"(you have {sys.version_info.major}.{sys.version_info.minor}). "
                f"Upgrade Python then: pip install 'conduct-cli[booster]'"
            )
            return
        print(f"  {GRAY}Agent Booster:{RESET} installing…")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "conduct-cli[booster]"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            print(f"  {RED}Agent Booster:{RESET} install failed — {r.stderr.strip()[:120]}")
            return
        print(f"  {GREEN}Agent Booster:{RESET} installed")
        if not shutil.which("booster"):
            print(f"  {YELLOW}Agent Booster:{RESET} 'booster' not on PATH yet — restart shell or re-run sync")
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
                print(f"  {GREEN}Agent Booster:{RESET} hooks installed")
            else:
                print(f"  {GRAY}Agent Booster:{RESET} init failed — {r.stderr.strip()[:120]}")
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
            print(f"  {GREEN}Agent Booster:{RESET} indexing in background (Read/Grep intercept active shortly)")
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
        print(f"  {GREEN}Agent Booster:{RESET} {symbols_count} symbols indexed — Read/Grep intercept active")

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
                print(f"  {GREEN}Agent Booster:{RESET} refreshed BOOSTER_SECRET in .mcp.json")
        except Exception:
            pass


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
    baseline_path = GUARD_DIR / "savings_baseline.json"
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
        print(f"  {GREEN}Savings reported{RESET}")
    except Exception:
        pass  # Never fail sync because savings POST failed

    # Push booster symbol index to team workspace (best-effort)
    try:
        r = subprocess.run(["booster", "index-push"], capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            print(f"  {GREEN}Booster index:{RESET} {r.stdout.strip()}")
    except Exception:
        pass


def cmd_guard_status(args):
    cfg          = _require_guard_config()
    workspace_id = cfg.get("workspace_id")
    user_email   = cfg.get("user_email", "")
    agent_token  = cfg.get("agent_token", "")
    base_url     = _api_url(cfg)

    # Auto-refresh user_email + clerk_user_id into config if missing
    if (not user_email or not cfg.get("clerk_user_id")) and agent_token:
        try:
            installed = _req("GET", f"{base_url}/guard/config/installed", token=agent_token or None)
            fetched_email = installed.get("user_email") or ""
            fetched_clerk = installed.get("clerk_user_id") or ""
            if fetched_email:
                cfg["user_email"] = fetched_email
                user_email = fetched_email
            if fetched_clerk:
                cfg["clerk_user_id"] = fetched_clerk
            _save_guard_config(cfg)
            # Rewrite hook script so future events carry the email
            hook_path = GUARD_DIR / "hook.py"
            _write_hook(hook_path)
        except Exception:
            pass

    # Load local policy for rule count
    rule_count = len(_load_policy().get("rules", []))

    # Fetch today's spend
    spend = {}
    try:
        spend = _req(
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
        events = _req(
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
        daemon_line = f"{GREEN}running{RESET} (pid {d_pid})"
    elif d_status == "stale":
        daemon_line = f"{YELLOW}stale{RESET} (pid {d_pid}, not flushing — will restart on next tool call)"
    else:
        daemon_line = f"{RED}not running{RESET} — will start on next tool call, journal events queued"

    # Proxy coverage — check active env vars in this shell
    proxy_url      = cfg.get("api_url", "https://api.conductai.ai").rstrip("/") + "/proxy"
    _env           = os.environ
    anthropic_ok   = proxy_url in _env.get("ANTHROPIC_BASE_URL", "")
    openai_ok      = proxy_url in _env.get("OPENAI_BASE_URL",    "")
    perplexity_ok  = proxy_url in _env.get("PERPLEXITY_BASE_URL","")
    env_file_exists = (Path.home() / ".conduct" / "env").exists()

    def _cov(ok: bool, name: str) -> str:
        return f"{GREEN}{name}{RESET}" if ok else f"{YELLOW}{name}{RESET}"

    covered   = [n for n, ok in [("Anthropic", anthropic_ok), ("OpenAI", openai_ok), ("Perplexity", perplexity_ok)] if ok]
    uncovered = [n for n, ok in [("Anthropic", anthropic_ok), ("OpenAI", openai_ok), ("Perplexity", perplexity_ok)] if not ok]

    if covered and not uncovered:
        proxy_line = f"{GREEN}active{RESET} — {', '.join(covered)} routed through Guard proxy"
    elif covered:
        proxy_line = f"{YELLOW}partial{RESET} — {', '.join(covered)} covered · {', '.join(uncovered)} NOT intercepted"
    elif env_file_exists:
        proxy_line = f"{YELLOW}inactive{RESET} — ~/.conduct/env exists but not sourced in this shell. Run: {BOLD}. ~/.conduct/env{RESET}"
    else:
        proxy_line = f"{RED}not configured{RESET} — run: {BOLD}conduct guard sync{RESET}"

    print(f"\n{BOLD}Guard status{RESET} — {user_email}")
    _active_cfg = _load_guard_config()
    if _active_cfg.get("current_goal_id"):
        print(f"  Active goal: {CYAN}{_active_cfg.get('current_goal_name', 'unnamed')}{RESET}  ({_active_cfg['current_goal_id'][:8]}...)")
    print(f"{rule_count} polic{'y' if rule_count == 1 else 'ies'} active")
    print()
    print(f"Proxy coverage: {proxy_line}")
    print(f"Drain daemon:   {daemon_line}")
    print()
    print(f"Today:")
    print(f"  Sessions: {session_str}")
    print(f"  Tokens used: {tokens_used:,}  (saved {token_saved_pct}% via optimization)")
    print(f"  Cost: ${cost:.2f}  (saved ${cost_saved:.2f})")
    print(f"  Violations: {len(violations)}{viol_summary}")
    print()


def cmd_guard_savings(args):
    cfg          = _require_guard_config()
    workspace_id = cfg.get("workspace_id")
    agent_token  = cfg.get("agent_token", "")
    base_url     = _api_url(cfg)

    try:
        data = _req(
            "GET",
            f"{base_url}/guard/savings/team-summary?workspace_id={workspace_id}",
            token=agent_token or None,
        )
    except Exception:
        print(f"{RED}Failed to fetch team savings.{RESET}")
        return
    if not isinstance(data, dict):
        print(f"{RED}Failed to fetch team savings.{RESET}")
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
    print(f"{BOLD}Team Token Savings{RESET}  ({dev_count} developer{'s' if dev_count != 1 else ''})")
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
        cfg = _load_guard_config()
        cfg["current_goal_id"] = goal_id
        cfg["current_goal_name"] = goal
        _save_guard_config(cfg)
        print(f"  {GREEN}Session started{RESET}")
        if goal:
            print(f"  Goal: {CYAN}{goal}{RESET}")
        print(f"  ID:   {goal_id}")
        print(f"\nAll Guard events in this session will be tagged with this goal.")
        print(f"Run {BOLD}conduct guard session stop{RESET} when done.")
    elif sub == "stop":
        cfg = _load_guard_config()
        name = cfg.pop("current_goal_name", "")
        cfg.pop("current_goal_id", None)
        _save_guard_config(cfg)
        print(f"  {GREEN}Session stopped{RESET}" + (f" — {name}" if name else ""))
    else:
        print("Usage: conduct guard session start [--goal GOAL] | stop")


def cmd_guard_audit(args):
    cfg          = _require_guard_config()
    workspace_id = cfg.get("workspace_id")
    user_email   = cfg.get("user_email", "")
    agent_token  = cfg.get("agent_token", "")
    base_url     = _api_url(cfg)

    since_str = getattr(args, "since", None) or "24h"
    since_iso = _parse_since(since_str)

    events_resp = _req(
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
        print(f"{GRAY}No events in the last {since_str}.{RESET}")
        return

    # Table header
    ts_w     = 22
    tool_w   = 14
    action_w = 28
    dec_w    = 10
    print()
    print(
        f"{BOLD}"
        f"{'Timestamp':<{ts_w}} "
        f"{'Tool':<{tool_w}} "
        f"{'Action':<{action_w}} "
        f"{'Decision':<{dec_w}} "
        f"{'Rule'}"
        f"{RESET}"
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
                f"  {RED}[BLOCK]{RESET} {GRAY}{ts}{RESET} "
                f"policy_signature_invalid "
                f"host={hostname} workspace={ws_slug}"
            )
            continue

        dec_color = RED if decision == "blocked" else GREEN if decision == "allowed" else GRAY
        print(
            f"  {GRAY}{ts:<{ts_w}}{RESET} "
            f"{tool:<{tool_w}} "
            f"{action:<{action_w}} "
            f"{dec_color}{decision:<{dec_w}}{RESET} "
            f"{GRAY}{rule}{RESET}"
        )

    print()


# ── Subparser registration (called from main.py) ──────────────────────────────

def register_guard_parser(sub):
    """Attach the `guard` subparser tree to an existing argparse subparsers object."""
    guard_p = sub.add_parser("guard", help="Guard — team policies and MCP registration")
    guard_sub = guard_p.add_subparsers(dest="guard_command")

    # conduct guard sync
    sync_p = guard_sub.add_parser("sync", help="Refresh policy and re-scan for AI tools")
    sync_p.add_argument("--cursor", action="store_true", help="Write active Guard policies to .cursorrules")
    sync_p.add_argument("--dry-run", action="store_true", help="Preview policy changes without writing anything")
    sync_p.add_argument("--reset-instructions", action="store_true", dest="reset_instructions",
                        help="Remove ConductGuard blocks from all instruction files")
    sync_p.add_argument("--proxy-url", default=None,
                        help="Override the Guard proxy URL (default: https://api.conductai.ai/proxy/anthropic)")
    sync_p.add_argument("--no-local-audit", action="store_true",
                        help="Skip the local pre-existing API key scan")

    # conduct guard status
    guard_sub.add_parser("status", help="Show today's spend and violations")

    # conduct guard savings --team
    guard_sub.add_parser("savings", help="Show org-level token savings across all developers")

    # conduct guard audit [--since 7d]
    audit_p = guard_sub.add_parser("audit", help="Show recent guard events")
    audit_p.add_argument(
        "--since",
        default="24h",
        metavar="PERIOD",
        help="Time window: 1h, 24h, 7d, 30d (default: 24h)",
    )

    # conduct guard install [--signing-key <hex>]
    install_p = guard_sub.add_parser("install", help="Install Guard hook and download policies")
    install_p.add_argument(
        "--signing-key",
        default=None,
        metavar="HEX",
        help="Hex-encoded 32-byte signing key from POST /workspaces/{id}/signing-key. "
             "Written to ~/.conduct/signing.key.",
    )

    # conduct guard booster-status
    guard_sub.add_parser("booster-status", help="Verify Agent Booster intercept is active for this project")

    # conduct guard skip-setup
    guard_sub.add_parser("skip-setup", help="Suppress the Guard setup reminder (does not disable Guard)")

    # conduct guard debug-hook <toolname>
    debug_hook_p = guard_sub.add_parser(
        "debug-hook",
        help="Run any hook standalone with JSON from stdin and print what it would do",
    )
    debug_hook_p.add_argument(
        "toolname",
        choices=["pretooluse", "posttooluse", "stop", "precompact", "session-start"],
        help="Which hook to test",
    )

    # conduct guard discover
    discover_p = guard_sub.add_parser("discover", help="Scan for AI agents and show Guard coverage")
    discover_p.add_argument("--config-only", action="store_true", help="Skip process scan, config files only")
    discover_p.add_argument("--report", default=None, metavar="FILE", help="Write full JSON report to file")

    # conduct guard watch
    watch_p = guard_sub.add_parser("watch", help="Start background daemon — scans every 15 min, auto-pushes to Guard")
    watch_p.add_argument("--stop",   action="store_true", help="Stop the running watch daemon")
    watch_p.add_argument("--status", action="store_true", help="Show whether the watch daemon is running")

    # conduct guard lint [--file PATH]
    lint_p = guard_sub.add_parser("lint", help="Validate local policy — show errors and warnings")
    lint_p.add_argument("--file", default=None, metavar="FILE",
                        help="Path to policy YAML/JSON (default: ~/.conduct/policy.json)")

    # conduct guard session start|stop
    p_session = guard_sub.add_parser("session", help="Start or stop a named goal session")
    session_sub = p_session.add_subparsers(dest="session_cmd")
    p_sess_start = session_sub.add_parser("start", help="Start a goal session — tags all Guard events with a goal ID")
    p_sess_start.add_argument("--goal", default="", help="Human-readable goal label")
    session_sub.add_parser("stop", help="End the current goal session")
    p_session.set_defaults(func=cmd_guard_session)

    return guard_p, guard_sub


def _discover_config_agents() -> list[tuple]:
    """Detect installed AI tools from config dirs + .env files. No cross-module import.
    Returns list of (name, config_path, under_guard) tuples.
    """
    home = Path.home()
    results = []

    def _mcp_registered(path: Path) -> bool:
        try:
            if not path.exists():
                return False
            text = path.read_text()
            if path.suffix == ".toml":
                # conduct-mcp or conductai in mcp_servers section
                return "conduct" in text and "mcp_servers" in text
            import json as _j
            d = _j.loads(text)
            return any("conduct" in k for k in d.get("mcpServers", {}))
        except Exception:
            return False

    def _hook_registered(path: Path) -> bool:
        try:
            if not path.exists():
                # Codex: check hooks.json sibling
                hooks_path = path.parent / "hooks.json"
                if hooks_path.exists():
                    return "conductguard" in hooks_path.read_text()
                return False
            import json as _j
            d = _j.loads(path.read_text())
            hooks = d.get("hooks", {})
            return any("conductguard" in str(h).lower() or "conduct" in str(h).lower()
                       for h in hooks.get("PreToolUse", []))
        except Exception:
            return False

    # Known tool config locations
    TOOLS = [
        ("claude-code", home / ".claude",  home / ".claude"  / "settings.json", "mcp"),
        ("codex",       home / ".codex",   home / ".codex"   / "config.toml",    "mcp"),
        ("cursor",      home / ".cursor",  home / ".cursor"  / "mcp.json",       "mcp"),
        ("windsurf",    home / ".codeium" / "windsurf", home / ".codeium" / "windsurf" / "mcp_config.json", "mcp"),
        ("copilot",     home / ".copilot", home / ".copilot" / "mcp-config.json", "mcp"),
    ]
    for name, check_dir, config_path, _ in TOOLS:
        if check_dir.exists():
            under = _mcp_registered(config_path) or _hook_registered(config_path)
            results.append((name, config_path, under))

    # .env file scan for LLM API keys — shadow agents not using known tools
    LLM_KEYS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COHERE_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY"]
    search_paths = [home, home / "projects", home / "code", home / "dev", Path.cwd()]
    seen_envs: set[str] = set()
    for base in search_paths:
        if not base.exists():
            continue
        try:
            candidates = list(base.glob(".env"))
            # ponytail: shallow glob only — deep ** hits system dirs (WhatsApp containers etc.)
            for sub in base.iterdir() if base.exists() else []:
                try:
                    if sub.is_dir() and not sub.name.startswith("."):
                        env = sub / ".env"
                        if env.exists():
                            candidates.append(env)
                except OSError:
                    pass
        except OSError:
            continue
        for env_file in candidates:
            if str(env_file) in seen_envs or ".git" in str(env_file):
                continue
            seen_envs.add(str(env_file))
            try:
                content = env_file.read_text(errors="ignore")
                found_keys = [k for k in LLM_KEYS if k in content]
                if found_keys:
                    results.append(("env-agent", env_file, False))  # .env with LLM key = unregistered
            except OSError:
                pass

    return results


def _scan_processes() -> list[dict]:
    """Detect AI agent processes using psutil. Returns list of discovered agent dicts."""
    try:
        import psutil
    except ImportError:
        return []

    # Known framework signatures: (framework_name, cmdline_patterns)
    SIGNATURES = [
        ("langchain",      ["langchain"]),
        ("crewai",         ["crewai", "crew_ai"]),
        ("autogen",        ["autogen", "pyautogen"]),
        ("openai-agents",  ["openai-agents", "openai_agents"]),
        ("llama-index",    ["llama_index", "llamaindex"]),
        ("claude-code",    ["claude"]),
        ("codex",          ["codex"]),
        ("cursor",         ["cursor"]),
        ("windsurf",       ["windsurf"]),
        ("copilot",        ["copilot-language-server", "github.copilot"]),
    ]

    found = []
    seen = set()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or []).lower()
            name    = (proc.info["name"] or "").lower()
            combined = f"{name} {cmdline}"
            for framework, patterns in SIGNATURES:
                if any(p in combined for p in patterns):
                    key = (framework, proc.info["name"])
                    if key not in seen:
                        seen.add(key)
                        found.append({
                            "name": proc.info["name"],
                            "framework": framework,
                            "source": "process",
                            "location": f"pid:{proc.info['pid']} {proc.info['name']}",
                            "evidence": {"pid": proc.info["pid"], "cmdline": cmdline[:200]},
                            "risk_score": 60,
                        })
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return found


_WATCH_PID  = Path.home() / ".conduct" / "watch.pid"
_WATCH_LOG  = Path.home() / ".conduct" / "watch.log"
_WATCH_INTERVAL = 15 * 60  # seconds


def _is_watch_running():
    """Returns (is_running: bool, pid: int | None)."""
    if not _WATCH_PID.exists():
        return False, None
    try:
        pid = int(_WATCH_PID.read_text().strip())
        os.kill(pid, 0)
        return True, pid
    except (ValueError, ProcessLookupError):
        _WATCH_PID.unlink(missing_ok=True)
        return False, None


def _watch_loop():
    """Background loop — runs discover+push every 15 min. Invoked as subprocess."""
    import time, json as _json
    # resolve config at each iteration so workspace switches are picked up
    def _cfg():
        return _load_guard_config()

    while True:
        try:
            c       = _cfg()
            api_url = _api_url(c)
            token   = c.get("agent_token", "")
            agent_token = c.get("agent_token", "")
            agents = []
            for name, config_path, mcp_key in _discover_config_agents():
                agents.append({
                    "name": name, "framework": name, "source": "config",
                    "location": str(config_path),
                    "evidence": {"config_path": str(config_path), "under_guard": mcp_key},
                    "risk_score": 20 if mcp_key else 70,
                    "under_guard": mcp_key,
                })
            try:
                process_agents = _scan_processes()
                registered = {a["framework"] for a in agents if a["under_guard"]}
                for a in process_agents:
                    a["under_guard"] = a["framework"] in registered
                agents += process_agents
            except Exception:
                pass
            _req("POST", f"{api_url}/guard/discover/scan",
                 body={"triggered_by": "watch", "agents": agents},
                 token=token or agent_token)
        except Exception:
            pass
        time.sleep(_WATCH_INTERVAL)


def cmd_guard_watch(args):
    """Start/stop/status the background discovery daemon."""
    import signal as _signal

    if getattr(args, "status", False):
        running, pid = _is_watch_running()
        if running:
            print(f"  Guard watch daemon running (pid {pid})")
            log_tail = ""
            if _WATCH_LOG.exists():
                lines = _WATCH_LOG.read_text().splitlines()
                log_tail = "\n".join(lines[-5:])
            if log_tail:
                print(f"  Last log:\n{log_tail}")
        else:
            print("  Guard watch daemon not running. Start with: conduct guard watch")
        return

    if getattr(args, "stop", False):
        running, pid = _is_watch_running()
        if not running:
            print("  Guard watch daemon is not running.")
            return
        os.kill(pid, _signal.SIGTERM)
        _WATCH_PID.unlink(missing_ok=True)
        print(f"  Guard watch daemon stopped (pid {pid}).")
        return

    # Start
    running, pid = _is_watch_running()
    if running:
        print(f"  Guard watch daemon already running (pid {pid}). Stop with: conduct guard watch --stop")
        return

    _WATCH_PID.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(_WATCH_LOG, "a")
    import subprocess, sys as _sys
    proc = subprocess.Popen(
        [_sys.executable, "-c",
         "from conduct_cli.guard import _watch_loop; _watch_loop()"],
        start_new_session=True,
        stdout=log_file,
        stderr=log_file,
    )
    _WATCH_PID.write_text(str(proc.pid))
    print(f"  Guard watch daemon started (pid {proc.pid}).")
    print(f"  Scans every 15 min — results visible at conductai.ai/guard/discovery")
    print(f"  Stop with: conduct guard watch --stop")


def cmd_guard_lint(args):
    """Validate the local policy file and report errors / warnings."""
    import json as _json, re as _re

    policy_path = getattr(args, "file", None)
    if policy_path:
        from pathlib import Path as _Path
        p = _Path(policy_path).expanduser().resolve()
        if not p.exists():
            print(f"  {RED}File not found: {p}{RESET}")
            sys.exit(1)
        raw = p.read_text()
    else:
        policy = _load_policy()
        raw = None

    if raw is not None:
        try:
            policy = _json.loads(raw)
        except Exception:
            try:
                import yaml as _yaml
                policy = _yaml.safe_load(raw)
            except Exception as e:
                print(f"  {RED}Cannot parse file: {e}{RESET}")
                sys.exit(1)

    rules     = policy.get("rules", [])
    fail_mode = policy.get("fail_mode")

    # ── local lint (no API call needed) ──────────────────────────────────────
    VALID_ACTIONS    = {"block", "warn", "audit", "approval", "inject"}
    VALID_FAIL_MODES = {"fail_open", "fail_closed"}
    MATCH_FIELDS     = {"match_tool", "match_pattern", "match_path_pattern",
                        "match_command_word", "match_tokens_before_gt"}

    errors: list[dict] = []
    warnings: list[dict] = []
    seen_ids: set[str] = set()

    if fail_mode and fail_mode not in VALID_FAIL_MODES:
        errors.append({"rule_id": "(policy)", "field": "fail_mode",
                       "message": f"must be one of: {', '.join(sorted(VALID_FAIL_MODES))}"})

    for i, rule in enumerate(rules):
        rid = rule.get("rule_id") or rule.get("id") or f"(rule[{i}])"
        if not rule.get("rule_id") and not rule.get("id"):
            errors.append({"rule_id": rid, "field": "rule_id", "message": "rule_id is required"})
        if rid in seen_ids:
            errors.append({"rule_id": rid, "field": "rule_id", "message": f"Duplicate rule_id '{rid}'"})
        seen_ids.add(rid)

        action = rule.get("action")
        if not action:
            errors.append({"rule_id": rid, "field": "action", "message": "action is required"})
        elif action not in VALID_ACTIONS:
            errors.append({"rule_id": rid, "field": "action",
                           "message": f"'{action}' must be one of: {', '.join(sorted(VALID_ACTIONS))}"})

        for rf in ("match_pattern", "match_path_pattern"):
            val = rule.get(rf)
            if val:
                try:
                    _re.compile(val)
                except _re.error as e:
                    errors.append({"rule_id": rid, "field": rf, "message": f"Invalid regex: {e}"})

        if not any(rule.get(f) for f in MATCH_FIELDS):
            warnings.append({"rule_id": rid, "field": "match_*",
                             "message": "No match condition — rule fires on every tool call"})

        tokens = rule.get("match_tokens_before_gt")
        if tokens is not None and (not isinstance(tokens, int) or tokens <= 0):
            errors.append({"rule_id": rid, "field": "match_tokens_before_gt",
                           "message": "must be a positive integer"})

    # ── output ────────────────────────────────────────────────────────────────
    print(f"\n  {BOLD}Policy lint{RESET} — {len(rules)} rule(s)\n")

    if not errors and not warnings:
        print(f"  {GREEN}No issues found{RESET}\n")
        return

    for e in errors:
        print(f"  {RED}ERROR{RESET}  [{e['rule_id']}] {e['field']}: {e['message']}")
    for w in warnings:
        print(f"  {YELLOW}WARN{RESET}   [{w['rule_id']}] {w['field']}: {w['message']}")

    print()
    if errors:
        sys.exit(1)


def cmd_guard_discover(args):
    """Scan for AI agents across config files and processes, report Guard coverage."""
    import json as _json

    cfg      = _load_guard_config()
    api_url  = _api_url(cfg)
    token    = cfg.get("agent_token", "")
    hdrs     = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Config file scan — detect AI tools from known config dirs
    config_agents = []
    for name, config_path, mcp_key in _discover_config_agents():
        under = mcp_key
        config_agents.append({
            "name": name,
            "framework": name,
            "source": "config",
            "location": str(config_path),
            "evidence": {"config_path": str(config_path), "under_guard": under},
            "risk_score": 20 if under else 70,
            "under_guard": under,
        })

    # Process scan
    process_agents: list[dict] = []
    if not getattr(args, "config_only", False):
        process_agents = _scan_processes()
        # Mark as under Guard if same framework is already registered
        registered_frameworks = {a["framework"] for a in config_agents if a["under_guard"]}
        for a in process_agents:
            a["under_guard"] = a["framework"] in registered_frameworks

    all_agents = config_agents + process_agents
    total      = len(all_agents)
    covered    = sum(1 for a in all_agents if a["under_guard"])
    missing    = total - covered
    pct        = round(covered / total * 100) if total else 0

    # Print coverage meter
    print(f"\n  Discovered {total} AI agents across your environment\n")
    config_count  = len(config_agents)
    process_count = len(process_agents)
    config_cov    = sum(1 for a in config_agents if a["under_guard"])
    process_cov   = sum(1 for a in process_agents if a["under_guard"])
    if config_count:
        print(f"  Config files:  {config_count:3d} agents   ({config_cov} under Guard, {config_count - config_cov} not)")
    if process_count:
        print(f"  Processes:     {process_count:3d} running   ({process_cov} under Guard, {process_count - process_cov} not)")
    print(f"  {'─' * 52}")
    print(f"  Guard coverage: {covered} of {total} agents  ({pct}%)\n")
    if missing:
        print(f"  Run: conduct guard discover --register to close the gap")
    print(f"  GitHub scan available — coming in v2\n")

    # POST to API
    try:
        agents_payload = list(all_agents)
        for t in _detect_ai_tools():
            agents_payload.append({
                "name": t["name"],
                "framework": t["name"],
                "source": "ai-tool",
                "under_guard": t.get("mcp_registered", False),
                "proxy_routed": t.get("proxy_routed", False),
            })
        payload = {"triggered_by": "cli", "agents": agents_payload}
        _req("POST", f"{api_url}/guard/discover/scan", body=payload, token=token)
    except SystemExit:
        pass  # 401/network errors — local output still useful

    # Write report if requested
    report_path = getattr(args, "report", None)
    if report_path:
        report = {"total": total, "under_guard": covered, "missing": missing, "coverage_pct": pct, "agents": all_agents}
        Path(report_path).write_text(_json.dumps(report, indent=2))
        print(f"  Report written to {report_path}")


def cmd_guard_booster_status(args):
    """Show whether booster is intercepting Read/Grep in this project."""
    import shutil, sqlite3, subprocess

    root = Path.cwd()
    db_path    = root / ".booster" / "symbols.db"
    hooks_path = root / ".claude" / "hooks" / "booster-gate.py"
    settings_p = root / ".claude" / "settings.json"

    booster_bin = shutil.which("booster")
    print(f"\n{BOLD}Agent Booster intercept status — {root.name}{RESET}\n")

    # 1. Binary
    if booster_bin:
        print(f"  {GREEN}✓{RESET} booster installed  ({booster_bin})")
    else:
        print(f"  {RED}✗{RESET} booster not found on PATH — run: pip install agent-booster")
        return

    # 2. Hook scripts written
    if hooks_path.exists():
        print(f"  {GREEN}✓{RESET} hook scripts present  (.claude/hooks/booster-gate.py)")
    else:
        print(f"  {RED}✗{RESET} hook scripts missing — run: conduct guard sync")

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
        print(f"  {GREEN}✓{RESET} Read hook wired in .claude/settings.json")
    else:
        print(f"  {RED}✗{RESET} Read hook NOT in .claude/settings.json — run: conduct guard sync")

    # 4. Index
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
            files = conn.execute("SELECT COUNT(DISTINCT file) FROM symbols").fetchone()[0]
            conn.close()
            print(f"  {GREEN}✓{RESET} symbols.db  — {count} symbols across {files} files")
        except Exception:
            print(f"  {YELLOW}?{RESET} symbols.db exists but could not be read")
    else:
        print(f"  {RED}✗{RESET} symbols.db missing — Read calls fall through unintercepted")
        print(f"       run: booster index --embed  (or: conduct guard sync to trigger it)")
        return

    # 5. Live intercept test — try reading a known file and check if smart-read fires
    print(f"\n  {BOLD}Live intercept test:{RESET}")
    if not hooks_path.exists():
        print(f"  {YELLOW}~{RESET} Skipped — hook script not present")
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
                print(f"  {GREEN}✓{RESET} Read intercepted → smart-read fired ({len(lines)} lines returned)")
                print(f"    tested on: {row[0]}")
            elif r.returncode == 0:
                print(f"  {YELLOW}~{RESET} Hook ran but passed through (file may not have symbols)")
            else:
                print(f"  {RED}✗{RESET} Hook errored (exit {r.returncode})")
    except Exception as e:
        print(f"  {YELLOW}?{RESET} Could not run live test: {e}")

    print()


def cmd_guard_debug_hook(args):
    """Run a hook module standalone with JSON piped from stdin and print the outcome.

    Usage:
        echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | \\
            conduct guard debug-hook pretooluse
    """
    import subprocess as _sp
    toolname = args.toolname  # pretooluse | posttooluse | stop | precompact | session-start

    module_map = {
        "pretooluse":   "conduct_cli.hooks.pretooluse",
        "posttooluse":  "conduct_cli.hooks.posttooluse",
        "stop":         "conduct_cli.hooks.stop",
        "precompact":   "conduct_cli.hooks.precompact",
        "session-start":"conduct_cli.hooks.session_start",
    }
    module = module_map[toolname]

    print(f"{BOLD}conduct guard debug-hook {toolname}{RESET}")
    print(f"{GRAY}Reading JSON from stdin (send EOF when done — Ctrl+D)…{RESET}\n")

    stdin_data = sys.stdin.read()
    if not stdin_data.strip():
        # Provide a neutral no-op payload so the hook doesn't crash
        stdin_data = "{}"

    result = _sp.run(
        [sys.executable, "-c", f"from {module} import main; main()"],
        input=stdin_data,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(f"{BOLD}stdout:{RESET}")
        print(result.stdout)
    if result.stderr:
        print(f"{BOLD}stderr:{RESET}")
        print(result.stderr)

    exit_label = {0: f"{GREEN}0 — allowed{RESET}", 2: f"{RED}2 — blocked{RESET}"}.get(
        result.returncode, f"{YELLOW}{result.returncode}{RESET}"
    )
    print(f"\n{BOLD}Exit code:{RESET} {exit_label}")


# ── OWASP Agentic Top 10 mapping ──────────────────────────────────────────────

_PRIV_KEYWORDS = ["privilege", "escalat", "role_abuse", "admin_access", "no-sudo", "nosudo", "runasroot"]

_OWASP_MAP: list[tuple[list[str], str, str]] = [
    (["prompt_inject", "injection", "jailbreak", "override_system", "indirect_prompt"],
     "A01", "Prompt Injection"),
    (["secret", "credential", "token_leak", "api_key_leak", "password", "sensitive_data", "pii", "exfil"],
     "A02", "Sensitive Information Disclosure"),
    (["supply_chain", "dependency", "package", "malicious_package", "unsigned"],
     "A03", "Supply Chain Vulnerabilities"),
    (["excessive_agency", "no-rm-rf", "norms", "rmrf", "scope", "overreach", "unauthorized_action", "out_of_scope", "shell_destruct"],
     "A04", "Excessive Agency"),
    (["model_theft", "model_extract", "weights"],
     "A05", "Model Theft"),
    (["communication", "callback", "exfiltrate_output", "covert_channel"],
     "A06", "Agentic Communication Vulnerabilities"),
    (["unmonitored", "no_audit", "policy_eval_error", "policy_signature_invalid"],
     "A07", "Insufficient Monitoring and Logging"),
    (["hallucin", "unverified", "over_reliance", "fabricat"],
     "A08", "Over-reliance on Model Outputs"),
    (_PRIV_KEYWORDS,
     "A09", "Privilege Escalation"),
    (["budget", "rate_limit", "dos", "denial", "hard_cap", "spend"],
     "A10", "Model Denial of Service"),
]

_OWASP_UNKNOWN = ("A??", "Uncategorised")


def _map_owasp(rule_id: str) -> tuple[str, str]:
    key = (rule_id or "").lower()
    for keywords, code, title in _OWASP_MAP:
        if any(k in key for k in keywords):
            return code, title
    return _OWASP_UNKNOWN


_GRADE_COLORS = {"A": "\033[32m", "B": "\033[32m", "C": "\033[33m", "D": "\033[33m", "F": "\033[31m"}
_GRADE_ORDER  = ["A", "B", "C", "D", "F"]


def _grade_below(actual: str, minimum: str) -> bool:
    return _GRADE_ORDER.index(actual) > _GRADE_ORDER.index(minimum.upper())


_VERDICT_COLOR = {"held": GREEN, "bypassed": RED, "not_tested": YELLOW}


def cmd_verify(args) -> None:
    """conduct verify — governance grade + OWASP Agentic Top 10 coverage."""
    import json as _json

    evidence_out = getattr(args, "evidence", None)
    badge        = getattr(args, "badge", False)
    min_grade    = getattr(args, "min_grade", None)
    strict       = getattr(args, "strict", False)
    fmt          = getattr(args, "format", "text")
    run_battery  = getattr(args, "run", False)

    cfg          = _require_guard_config()
    workspace_id = cfg.get("workspace_id")
    agent_token  = cfg.get("agent_token", "")
    base_url     = _api_url(cfg)

    # ── fetch evidence from API ───────────────────────────────────────────────
    ev = _req(
        "GET",
        f"{base_url}/guard/verify/evidence?workspace_id={workspace_id}",
        token=agent_token or None,
    )

    grade        = ev.get("grade", "F")
    coverage_pct = ev.get("coverage_pct", 0)
    score        = ev.get("score", 0)
    blocked_24h  = ev.get("blocked_24h", 0)
    controls     = ev.get("controls", [])
    generated_at = ev.get("generated_at", "")

    # ── --run (live adversarial battery) ─────────────────────────────────────
    run_result = None
    if run_battery:
        print(f"\n{BOLD}Running adversarial test battery…{RESET}")
        run_result = _req(
            "POST",
            f"{base_url}/guard/verify/run?workspace_id={workspace_id}",
            token=agent_token or None,
        )
        if fmt == "json":
            print(_json.dumps(run_result, indent=2))
            return
        rs      = run_result.get("score", 0)
        rg      = run_result.get("grade", "F")
        passed  = run_result.get("passed_tests", 0)
        total   = run_result.get("total_tests", 0)
        results = run_result.get("results", [])
        rg_col  = _GRADE_COLORS.get(rg, GRAY)
        print()
        print(f"{BOLD}conduct verify --run — Live Adversarial Score{RESET}")
        print("─" * 60)
        print(f"\n  Live Grade: {rg_col}{BOLD}{rg}{RESET}  ({rs}/100) · {passed}/{total} held\n")
        print(f"  {BOLD}{'ASI':<8} {'Verdict':<12} {'Expected':<10} {'Actual':<10} Test{RESET}")
        print("  " + "─" * 56)
        for r in results:
            vc = _VERDICT_COLOR.get(r.get("verdict", ""), GRAY)
            print(
                f"  {r.get('asi',''):<8} "
                f"{vc}{r.get('verdict',''):<12}{RESET} "
                f"{r.get('expected',''):<10} "
                f"{r.get('actual',''):<10} "
                f"{r.get('name','')}"
            )
        print()
        if min_grade and _grade_below(rg, min_grade):
            print(f"  {RED}✗ Live grade {rg} is below minimum {min_grade.upper()}.{RESET}\n")
            sys.exit(1)
        print(f"  {GREEN}✓ PASS{RESET}\n")
        return

    # ── --badge ───────────────────────────────────────────────────────────────
    if badge:
        color = {"A": "brightgreen", "B": "green", "C": "yellow", "D": "orange", "F": "red"}.get(grade, "lightgrey")
        print(f"![Conduct Guard](https://img.shields.io/badge/Guard-Grade_{grade}-{color})")
        return

    # ── --evidence (write artifact) ───────────────────────────────────────────
    if evidence_out:
        artifact = {
            "grade":        grade,
            "coverage_pct": coverage_pct,
            "score":        score,
            "blocked_24h":  blocked_24h,
            "controls":     controls,
            "generated_at": generated_at,
            "workspace_id": workspace_id,
        }
        Path(evidence_out).write_text(_json.dumps(artifact, indent=2))
        print(f"{GREEN}✓ Evidence artifact written to {evidence_out}{RESET}")

    # ── output ────────────────────────────────────────────────────────────────
    if fmt == "json":
        print(_json.dumps(ev, indent=2))
    else:
        grade_color = _GRADE_COLORS.get(grade, GRAY)
        print()
        print(f"{BOLD}conduct verify — Governance Grade{RESET}")
        print("─" * 60)
        print(f"\n  Grade:    {grade_color}{BOLD}{grade}{RESET}  (score {score}/100)")
        print(f"  Coverage: {coverage_pct}% of OWASP ASI controls active")
        print(f"  Blocked (24h): {blocked_24h}")
        print()
        print(f"{BOLD}  {'Control':<8} {'Status':<10} Name{RESET}")
        print("  " + "─" * 56)
        for c in controls:
            status = c.get("status", "missing")
            if status == "active":
                sc = f"{GREEN}active   {RESET}"
            elif status == "partial":
                sc = f"{YELLOW}partial  {RESET}"
            else:
                sc = f"{RED}missing  {RESET}"
            print(f"  {c.get('id',''):<8} {sc} {c.get('name','')}")
        print()

        # CI checks
        failed = False
        if strict and blocked_24h > 0:
            print(f"  {RED}✗ Strict mode: {blocked_24h} blocked event(s) in last 24h.{RESET}")
            failed = True
        if min_grade and _grade_below(grade, min_grade):
            print(f"  {RED}✗ Grade {grade} is below minimum {min_grade.upper()}.{RESET}")
            failed = True
        if not failed:
            print(f"  {GREEN}✓ PASS{RESET}")
        print()

    # ── exit codes ────────────────────────────────────────────────────────────
    if (strict and blocked_24h > 0) or (min_grade and _grade_below(grade, min_grade)):
        sys.exit(1)


def dispatch_guard(args, guard_p):
    """Dispatch to the correct guard handler. Called from main()."""
    guard_command = getattr(args, "guard_command", None)
    if guard_command == "sync":
        cmd_guard_sync(args)
    elif guard_command == "status":
        cmd_guard_status(args)
    elif guard_command == "savings":
        cmd_guard_savings(args)
    elif guard_command == "audit":
        cmd_guard_audit(args)
    elif guard_command == "install":
        cmd_guard_install(args)
    elif guard_command == "discover":
        cmd_guard_discover(args)
    elif guard_command == "watch":
        cmd_guard_watch(args)
    elif guard_command == "lint":
        cmd_guard_lint(args)
    elif guard_command == "booster-status":
        cmd_guard_booster_status(args)
    elif guard_command == "debug-hook":
        cmd_guard_debug_hook(args)
    elif guard_command == "session":
        cmd_guard_session(args)
    else:
        guard_p.print_help()
        sys.exit(1)
