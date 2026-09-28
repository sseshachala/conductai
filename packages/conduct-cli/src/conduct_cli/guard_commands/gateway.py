"""Guard CLI: gateway."""
from __future__ import annotations

from pathlib import Path
import json
import os
import re as _re
import sys

from . import shared as _guard_shared


def _configure_codex_proxy(proxy_url: str) -> bool:
    """Opt in Codex to Conduct's Responses endpoint without storing a secret."""
    config_path = Path.home() / ".codex" / "config.toml"
    if not config_path.parent.exists():
        return False
    content = config_path.read_text() if config_path.exists() else ""
    backup = config_path.with_suffix(".toml.pre-conduct-proxy")
    if config_path.exists() and not backup.exists():
        backup.write_text(content)
        backup.chmod(0o600)

    import re as _re
    sections = _re.split(r"(?m)(?=^\[)", content)
    root = sections[0]
    root = _re.sub(r'(?m)^model_provider\s*=.*\n?', '', root)
    root = root.rstrip() + '\nmodel_provider = "conduct"\n\n'
    remaining = [s for s in sections[1:] if not s.startswith("[model_providers.conduct]")]
    base = proxy_url.rstrip("/") + "/openai/v1"
    snippet = (
        "[model_providers.conduct]\n"
        'name = "Conduct Gateway"\n'
        f"base_url = {json.dumps(base)}\n"
        'env_key = "CONDUCT_GATEWAY_TOKEN"\n'
        'wire_api = "responses"\n'
        'requires_openai_auth = false\n\n'
    )
    config_path.write_text(root + snippet + "".join(remaining).lstrip())
    return True


def _configure_codex_launch_env(agent_token: str) -> bool:
    """Refresh credentials for newly launched macOS apps, not running processes."""
    if sys.platform != "darwin" or not agent_token:
        return False
    import subprocess

    try:
        subprocess.run(
            ["/bin/launchctl", "setenv", "CONDUCT_GATEWAY_TOKEN", agent_token],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        # Subprocess exceptions can include the credential-bearing command.
        print(f"  {_guard_shared.YELLOW}Could not update the macOS app environment. "
              f"Source ~/.conduct/env and launch Codex from that shell.{_guard_shared.RESET}")
        return False
    return True


def _read_conduct_env_var(name: str) -> str:
    # ponytail: fall back to ~/.conduct/env so proxy detection is truthful
    # right after `conduct login`, before the user sources the file.
    try:
        for line in (Path.home() / ".conduct" / "env").read_text().splitlines():
            if line.startswith(f"export {name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _is_anthropic_proxied() -> bool:
    url = os.environ.get("ANTHROPIC_BASE_URL", "") or _read_conduct_env_var("ANTHROPIC_BASE_URL")
    return "conductai.ai" in url or "conduct" in url.lower()


def _is_openai_proxied() -> bool:
    url = os.environ.get("OPENAI_BASE_URL", "") or _read_conduct_env_var("OPENAI_BASE_URL")
    return "conductai.ai" in url or "conduct" in url.lower()


CONDUCT_DIR        = Path.home() / ".conduct"


PROXY_ENV_FILE     = CONDUCT_DIR / "env"


PROXY_OVERRIDE     = CONDUCT_DIR / "env-override"


DEFAULT_PROXY_URL  = "https://gateway.conductai.ai/gateway/v1"


SHELL_RC_MARKER    = "# Conduct Guard Proxy — managed by `conduct guard sync`"


SHELL_SOURCE_LINE  = "[ -f ~/.conduct/env ] && . ~/.conduct/env"


def _gateway_v1_url(proxy_url: str) -> str:
    """Convert a legacy server proxy URL to the parallel gateway surface."""
    base = proxy_url.rstrip("/")
    if base.endswith("/proxy"):
        return base[:-len("/proxy")] + "/gateway/v1"
    return base


_KEY_PATTERNS = [
    ("anthropic",  _re.compile(r"sk-ant-(?:api\d+-)?[A-Za-z0-9_-]{20,}")),
    ("openai",     _re.compile(r"sk-(?:proj-)?[A-Za-z0-9]{20,}")),   # sk-… (not sk-ant-)
    ("perplexity", _re.compile(r"pplx-[A-Za-z0-9]{20,}")),
]


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
        _guard_shared._req(
            "POST",
            f"{base_url}/guard/local-audit-findings",
            body={
                "user_email": cfg.get("user_email", ""),
                "findings":   findings,
            },
            token=cfg.get("agent_token", ""),
        )
    except Exception as e:
        print(f"  {_guard_shared.YELLOW}Audit upload skipped: {e}{_guard_shared.RESET}")


_LEGACY_CLAUDE_BYPASSES = {
    "alias claude='env -u ANTHROPIC_BASE_URL claude'",
    (
        "function claude { "
        "$prev=$env:ANTHROPIC_BASE_URL; $env:ANTHROPIC_BASE_URL=$null; "
        "try { & claude @args } finally { $env:ANTHROPIC_BASE_URL=$prev } }"
    ),
}


def _remove_legacy_claude_bypass(content: str) -> str:
    """Remove only proxy-bypass aliases previously generated by Conduct."""
    return "".join(
        line for line in content.splitlines(keepends=True)
        if line.strip() not in _LEGACY_CLAUDE_BYPASSES
    )


def _write_proxy_env_windows(agent_token: str, proxy_url: str) -> tuple[Path, bool]:
    """Windows equivalent of _write_proxy_env — PowerShell profile + env.ps1."""
    CONDUCT_DIR.mkdir(parents=True, exist_ok=True)
    token = agent_token
    proxy = proxy_url.rstrip("/")

    ps1_file = CONDUCT_DIR / "env.ps1"
    ps1_file.write_text("\n".join([
        SHELL_RC_MARKER,
        "# Edit ~/.conduct/env-override.ps1 to add your own vars — sourced after this file.",
        "",
        f'$env:ANTHROPIC_BASE_URL = "{proxy}/anthropic"',
        f'$env:ANTHROPIC_API_KEY  = "{token}"',
        '$env:CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY = "1"',
        "",
        f'$env:OPENAI_BASE_URL = "{proxy}/openai/v1"',
        f'$env:OPENAI_API_KEY  = "{token}"',
        '$env:CONDUCT_GATEWAY_TOKEN = $env:OPENAI_API_KEY',
        "",
        f'$env:PERPLEXITY_BASE_URL = "{proxy}/perplexity"',
        f'$env:PERPLEXITY_API_KEY  = "{token}"',
        "",
        'if (Test-Path "$HOME/.conduct/env-override.ps1") { . "$HOME/.conduct/env-override.ps1" }',
        "",
    ]))

    # ponytail: prefer PS7 profile; fall back to WPS5 only if its file already exists
    ps7_profile = Path.home() / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
    wps5_profile = Path.home() / "Documents" / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"
    if ps7_profile.parent.exists() or not wps5_profile.exists():
        rc = ps7_profile
    else:
        rc = wps5_profile

    existing = rc.read_text() if rc.exists() else ""
    cleaned = _remove_legacy_claude_bypass(existing)
    bypass_removed = cleaned != existing
    existing = cleaned
    PS_SOURCE_LINE = 'if (Test-Path "$HOME/.conduct/env.ps1") { . "$HOME/.conduct/env.ps1" }'

    if SHELL_RC_MARKER in existing:
        if bypass_removed:
            rc.write_text(existing)
            return rc, True
        return rc, False

    rc.parent.mkdir(parents=True, exist_ok=True)
    addition = (
        f"\n\n{SHELL_RC_MARKER}\n"
        f"{PS_SOURCE_LINE}\n"
    )
    rc.write_text(existing.rstrip() + addition if existing else addition.lstrip())
    return rc, True


_OLD_GATEWAY_HOST = "api.conductai.ai/gateway/v1"


_NEW_GATEWAY_HOST = "gateway.conductai.ai/gateway/v1"


def _migrate_proxy_env_if_stale() -> bool:
    """Rewrite ~/.conduct/env (and env.ps1 on Windows) in place if it
    contains the old default gateway host. Returns True if a rewrite
    happened. No-op when the file is absent, already migrated, or
    contains a non-default (user-customised) URL."""
    targets = []
    if PROXY_ENV_FILE.exists():
        targets.append(PROXY_ENV_FILE)
    ps1 = CONDUCT_DIR / "env.ps1"
    if ps1.exists():
        targets.append(ps1)
    changed = False
    for path in targets:
        try:
            old_text = path.read_text()
        except Exception:
            continue
        if _OLD_GATEWAY_HOST not in old_text:
            continue
        new_text = old_text.replace(_OLD_GATEWAY_HOST, _NEW_GATEWAY_HOST)
        if new_text == old_text:
            continue
        try:
            path.write_text(new_text)
            changed = True
        except Exception:
            # Best-effort — never block the CLI on a write failure.
            pass
    return changed


def _write_proxy_env(agent_token: str, proxy_url: str) -> tuple[Path, bool]:
    """Write ~/.conduct/env with the 3 provider env-var pairs and ensure the
    user's shell rc sources it.

    Idempotent — env file rewritten each sync. Shell rc gets the source line
    appended once (guarded by SHELL_RC_MARKER). Returns (rc_path, newly_sourced).
    User-managed customizations go in ~/.conduct/env-override which is sourced
    after the managed file.
    """
    if not agent_token:
        print(f"  {_guard_shared.YELLOW}Proxy env skipped — no agent token in config{_guard_shared.RESET}")
        return Path(), False

    if sys.platform == "win32":
        return _write_proxy_env_windows(agent_token, proxy_url)

    CONDUCT_DIR.mkdir(parents=True, exist_ok=True)
    token = agent_token  # cond_agt_* used directly as the bearer value
    proxy = proxy_url.rstrip("/")

    PROXY_ENV_FILE.write_text("\n".join([
        SHELL_RC_MARKER,
        "# Edit ~/.conduct/env-override to add your own vars — sourced after this file.",
        "",
        f'export ANTHROPIC_BASE_URL="{proxy}/anthropic"',
        f'export ANTHROPIC_API_KEY="{token}"',
        'export CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY="1"',
        "",
        f'export OPENAI_BASE_URL="{proxy}/openai/v1"',
        f'export OPENAI_API_KEY="{token}"',
        'export CONDUCT_GATEWAY_TOKEN="$OPENAI_API_KEY"',
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
        print(f"  {_guard_shared.YELLOW}fish detected — add this to ~/.config/fish/config.fish:{_guard_shared.RESET}")
        print(f"    bass source ~/.conduct/env")
        return Path(), False
    else:
        print(f"  {_guard_shared.YELLOW}Unknown shell. Source manually: . ~/.conduct/env{_guard_shared.RESET}")
        return Path(), False

    existing = rc.read_text() if rc.exists() else ""
    cleaned = _remove_legacy_claude_bypass(existing)
    bypass_removed = cleaned != existing
    existing = cleaned

    if SHELL_RC_MARKER in existing:
        if bypass_removed:
            rc.write_text(existing)
            return rc, True
        return rc, False

    rc.parent.mkdir(parents=True, exist_ok=True)
    addition = (
        f"\n\n{SHELL_RC_MARKER}\n"
        f"{SHELL_SOURCE_LINE}\n"
    )
    rc.write_text(existing.rstrip() + addition if existing else addition.lstrip())
    return rc, True
