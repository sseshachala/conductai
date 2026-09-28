"""Guard CLI: instructions."""
from __future__ import annotations

from pathlib import Path
import json

from . import shared as _guard_shared


_GUARD_RULES_TEXT = (Path(__file__).resolve().parents[1] / "guard_policy.md").read_text().rstrip()


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
            print(f"  {_guard_shared.GRAY}Cursor global rules already contain ConductGuard policy{_guard_shared.RESET}")
            continue
        cfg["cursor.rules.user"] = (existing + "\n\n" + GUARD_RULES).strip()
        settings_path.write_text(json.dumps(cfg, indent=2))
        print(f"  {_guard_shared.GREEN}Cursor global rules updated with ConductGuard policy{_guard_shared.RESET}")


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
                    print(f"  {_guard_shared.GRAY}{label} already up to date{_guard_shared.RESET}")
                else:
                    path.write_text(updated)
                    print(f"  {_guard_shared.GREEN}{label} updated{_guard_shared.RESET}")
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
                print(f"  {_guard_shared.GREEN}{label} — ConductGuard block added{_guard_shared.RESET}")


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
            print(f"  {_guard_shared.GREEN}Removed ConductGuard block: {p}{_guard_shared.RESET}")
            removed += 1
        else:
            print(f"  {_guard_shared.YELLOW}No ConductGuard block found: {p}{_guard_shared.RESET}")
    if removed == 0:
        print("  No ConductGuard blocks found in any instruction files.")


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
    print(f"  {_guard_shared.GREEN}.cursorrules written:{_guard_shared.RESET} {len(enabled)} rule(s) → {out.resolve()}")
