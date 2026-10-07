"""Cedar / gateway-config import and export, and `conduct skill`."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from conduct_cli.commands.shared import (
    BLUE,
    BOLD,
    GRAY,
    GREEN,
    RED,
    RESET,
    YELLOW,
    _require_auth,
)


def cmd_import_cedar(args):
    """conduct import-cedar <file> --pack-slug X --pack-name Y [--install] [--yes]"""
    server, workspace, token = _require_auth(args)
    if not token:
        print(f"{RED}Not authenticated. Run `conduct login` first.{RESET}")
        return

    path = Path(args.file)
    if not path.exists():
        print(f"{RED}File not found: {path}{RESET}")
        return

    try:
        content = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"{RED}Invalid JSON in {path}: {e}{RESET}")
        return

    # Accept either a single policy or a list
    if isinstance(content, dict):
        policies = [content]
    elif isinstance(content, list):
        policies = content
    else:
        print(f"{RED}Expected a Cedar policy object or a list of them; got {type(content).__name__}.{RESET}")
        return

    body = json.dumps({
        "format": "cedar_json",
        "policies": policies,
        "pack_slug": args.pack_slug,
        "pack_name": args.pack_name,
        "pack_version": args.pack_version,
        "pack_description": args.pack_description,
        "preview_only": not args.install,
    }).encode()

    req = urllib.request.Request(
        f"{server}/guard/registry/import-cedar",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Workspace-Id": workspace or "",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        try:
            detail = json.loads(body_text).get("detail", body_text)
        except Exception:
            detail = body_text[:400]
        print(f"{RED}Import failed ({e.code}): {detail}{RESET}")
        return
    except Exception as e:
        print(f"{RED}Request failed: {e}{RESET}")
        return

    imported = result.get("rules_imported", 0)
    rejected = result.get("rules_rejected", 0)

    print(f"{BOLD}Cedar policy import{RESET}")
    print(f"  {GREEN}Rules imported:{RESET} {imported}")
    if rejected:
        print(f"  {YELLOW}Rules rejected:{RESET} {rejected}")
        for rej in result.get("rejections") or []:
            err = rej.get("error", {}) or {}
            print(f"    [{rej.get('index')}] {err.get('error', 'Error')}: {err.get('message', '')}")
            if err.get("hint"):
                print(f"        hint: {err['hint']}")

    if args.install:
        if result.get("installed"):
            print(f"\n{GREEN}Installed:{RESET} {args.pack_slug}@{args.pack_version} ({imported} rule(s))")
        else:
            print(f"\n{YELLOW}Not installed{RESET} (no rules survived conversion)")
    else:
        print(f"\nThis was a preview. Re-run with --install to create the pack in your workspace.")


def cmd_import_gateway_config(args):
    """conduct import --gateway-config <file.json> [--name NEW_NAME]

    Import a Gateway Profile v2 from a portable JSON file. Server strips
    every ``credential_ref`` on import — the admin then picks vault +
    credential handle per target in the UI (Save gate blocks until
    filled).

    The JSON shape is the ``working_copy`` dict — same shape
    ``conduct export --gateway-config`` emits and the same shape the
    editor's Save call posts. Round-trip is safe: export → import
    produces a draft the admin can complete in one editor session.

    Exit codes: 0 on success, 1 on any failure (auth, missing file,
    invalid JSON, backend rejection). Error output goes to stderr so
    callers can pipe stdout without noise.
    """
    server, workspace, token = _require_auth(args)
    if not token:
        print(f"{RED}Not authenticated. Run `conduct login` first.{RESET}", file=sys.stderr)
        sys.exit(1)

    path = Path(args.file)
    if not path.exists():
        print(f"{RED}File not found: {path}{RESET}", file=sys.stderr)
        sys.exit(1)

    try:
        working_copy = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"{RED}Invalid JSON in {path}: {e}{RESET}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(working_copy, dict):
        print(
            f"{RED}Expected a JSON object at the top level (the "
            f"working_copy dict); got {type(working_copy).__name__}.{RESET}",
            file=sys.stderr,
        )
        sys.exit(1)

    body_dict = {"working_copy": working_copy}
    if getattr(args, "name", None):
        body_dict["name_override"] = args.name

    req = urllib.request.Request(
        f"{server}/workspaces/{workspace}/gateway-profiles-v2/import",
        data=json.dumps(body_dict).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Workspace-Id": workspace or "",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        # Backend returns structured errors (PR #2033) — parse them
        # into a readable per-line summary when possible.
        try:
            payload = json.loads(body_text)
            detail = payload.get("detail")
            if isinstance(detail, dict) and isinstance(detail.get("errors"), list):
                lines = [detail.get("summary", "import failed")]
                for err in detail["errors"][:5]:
                    where = err.get("path") or "(profile)"
                    lines.append(f"  {where}: {err.get('message', 'invalid')}")
                if len(detail["errors"]) > 5:
                    lines.append(f"  +{len(detail['errors']) - 5} more")
                detail_text = "\n".join(lines)
            else:
                detail_text = str(detail or body_text)[:600]
        except Exception:
            detail_text = body_text[:600]
        print(f"{RED}Import failed ({e.code}):{RESET}\n{detail_text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"{RED}Request failed: {e}{RESET}", file=sys.stderr)
        sys.exit(1)

    profile = result.get("profile") or {}
    gaps = result.get("credential_gaps") or []
    next_url = result.get("next_url") or ""

    print(f"{BOLD}Gateway profile imported{RESET}")
    print(f"  {GREEN}Name:{RESET}       {profile.get('name', '?')}")
    print(f"  {GREEN}Profile ID:{RESET} {profile.get('id', '?')}")
    print(f"  {GREEN}Cond code:{RESET}  {profile.get('cond_code', '?')}")

    if gaps:
        print(f"\n{YELLOW}{len(gaps)} target(s) need credentials before publish:{RESET}")
        for g in gaps:
            print(
                f"  #{g.get('target_index', '?') + 1 if isinstance(g.get('target_index'), int) else '?'} "
                f"{g.get('target_id', '?')} ({g.get('transport', '?')}): "
                f"{g.get('reason', 'pick a vault')}"
            )

    if next_url:
        print(f"\n{BLUE}Finish setup:{RESET} {next_url}")


def cmd_export_gateway_config(args):
    """conduct export --gateway-config <profile-id-or-cond-code> [--out FILE]

    Pull a Gateway Profile v2 as portable JSON. Server strips every
    ``credential_ref`` on export (safe to commit / share). Writes to
    stdout by default; ``--out FILE`` writes to a file instead.

    ``target`` is one of:
      * a profile UUID (e.g. ``123e4567-e89b-12d3-a456-426614174000``),
      * a bare cond_code (e.g. ``abc12345``), OR
      * the full ``cond-<code>-<alias>`` string admins see in the
        "How to use" panel (e.g. ``cond-abc12345-my-profile``).

    Bare model aliases (e.g. ``claude-sonnet-4-6``) are NOT resolved —
    they map to targets inside a profile, not to profiles themselves.

    Exit codes: 0 on success, 1 on any failure (auth, unresolved
    target, backend error). Errors go to stderr so ``--out`` piping
    stays clean.
    """
    server, workspace, token = _require_auth(args)
    if not token:
        print(f"{RED}Not authenticated. Run `conduct login` first.{RESET}", file=sys.stderr)
        sys.exit(1)

    profile_id = _resolve_gateway_profile_id(server, workspace, token, args.target)
    if not profile_id:
        # _resolve_gateway_profile_id already printed the specific
        # error to stderr — just exit nonzero here.
        sys.exit(1)

    req = urllib.request.Request(
        f"{server}/workspaces/{workspace}/gateway-profiles-v2/{profile_id}/export",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Workspace-Id": workspace or "",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            snapshot = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        print(f"{RED}Export failed ({e.code}): {body_text[:400]}{RESET}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"{RED}Request failed: {e}{RESET}", file=sys.stderr)
        sys.exit(1)

    out_json = json.dumps(snapshot, indent=2)
    out_path = getattr(args, "out", None)
    if out_path:
        Path(out_path).write_text(out_json + "\n")
        print(f"{GREEN}Wrote:{RESET} {out_path}", file=sys.stderr)
    else:
        print(out_json)


def _resolve_gateway_profile_id(server: str, workspace: str, token: str, target: str) -> str | None:
    """Accept either a UUID or a cond_code. Returns the UUID or prints
    an error + returns None."""
    # UUID shape: 8-4-4-4-12 hex.
    import re as _re
    if _re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", target, _re.IGNORECASE):
        return target

    # cond_code lookup — fetch the list, match by cond_code.
    req = urllib.request.Request(
        f"{server}/workspaces/{workspace}/gateway-profiles-v2",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Workspace-Id": workspace or "",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            profiles = json.loads(r.read())
    except Exception as e:
        print(
            f"{RED}Could not list profiles to resolve {target!r}: {e}{RESET}",
            file=sys.stderr,
        )
        return None

    for p in profiles or []:
        if p.get("cond_code") == target:
            return p.get("id")
        # Also accept "cond-<code>-<alias>" for convenience.
        alias = p.get("model_alias") or ""
        full = f"cond-{p.get('cond_code', '')}-{alias}"
        if target == full:
            return p.get("id")

    print(
        f"{RED}No profile matched {target!r}. Pass a profile UUID, "
        f"a cond_code, or the full cond-<code>-<alias> identifier.{RESET}",
        file=sys.stderr,
    )
    return None


def cmd_skill(args):
    """conduct skill list | install <slug> | uninstall <slug>"""
    skill_command = getattr(args, "skill_command", None)
    server, workspace, token = _require_auth(args)

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def _req(method, path, expect=None):
        url = f"{server}{path}"
        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            return data
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                msg = json.loads(body).get("detail", body)
            except Exception:
                msg = body
            from conduct_cli.api import _friendly
            print(f"{RED}{_friendly(e.code, msg)}{RESET}")
            sys.exit(1)

    if skill_command == "list":
        data = _req("GET", f"/compliance/packs/available?workspace_id={workspace}")
        installed_data = _req("GET", f"/compliance/packs/installed?workspace_id={workspace}")
        installed = set(installed_data.get("installed", []))

        packs = data.get("packs", [])
        if not packs:
            print("No skill packs available.")
            return

        print(f"\n{'Slug':<20} {'Name':<22} {'Tier':<8} {'Rules':<7} Status")
        print("─" * 70)
        for p in packs:
            slug   = p.get("slug", "")
            name   = p.get("name", "")
            tier   = p.get("tier", "")
            rules  = len(p.get("rules", []))
            status = f"{GREEN}installed{RESET}" if slug in installed else f"{GRAY}available{RESET}"
            print(f"{slug:<20} {name:<22} {tier:<8} {rules:<7} {status}")
        print()

    elif skill_command == "install":
        slug = getattr(args, "slug", None)
        if not slug:
            print(f"{RED}Usage: conduct skill install <slug>{RESET}")
            sys.exit(1)
        _req("POST", f"/compliance/packs/{slug}/install?workspace_id={workspace}")
        print(f"{GREEN}✓{RESET} Installed {BOLD}{slug}{RESET}")
        print(f"  Run {BOLD}conduct guard sync{RESET} to push the updated policy to your hook.")

    elif skill_command == "uninstall":
        slug = getattr(args, "slug", None)
        if not slug:
            print(f"{RED}Usage: conduct skill uninstall <slug>{RESET}")
            sys.exit(1)
        _req("DELETE", f"/compliance/packs/{slug}/uninstall?workspace_id={workspace}")
        print(f"{GREEN}✓{RESET} Uninstalled {BOLD}{slug}{RESET}")
        print(f"  Run {BOLD}conduct guard sync{RESET} to push the updated policy to your hook.")

    else:
        print("Usage: conduct skill <list|install|uninstall> [slug]")
