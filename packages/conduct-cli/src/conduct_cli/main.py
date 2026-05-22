import argparse
import json
import sys
import urllib.parse
from pathlib import Path

import yaml

from conduct_cli import api

RESET = "\033[0m"
BOLD  = "\033[1m"
GREEN = "\033[32m"
RED   = "\033[31m"
BLUE  = "\033[34m"
GRAY  = "\033[90m"
CYAN  = "\033[36m"

DEV_WORKSPACE = "00000000-0000-0000-0000-000000000001"


def _stream_run(server: str, workflow_id: str, run_id: str, workspace_id: str, token=None, api_key=None) -> bool:
    qs = f"?workspace_id={workspace_id}"
    if api_key:
        qs += f"&api_key={api_key}"
    elif token:
        qs += f"&token={token}"
    url = f"{server}/workflows/{workflow_id}/runs/{run_id}/stream{qs}"

    for data in api.stream(url):
        kind    = data.get("kind", "")
        bid     = data.get("block_id") or ""
        payload = data.get("payload", data)
        prefix  = f"[{bid}] " if bid else ""

        if kind == "block_started":
            label = payload.get("label") or payload.get("type", "")
            print(f"{BLUE}    ▶ {prefix}{label}{RESET}")
        elif kind == "block_completed":
            summary = payload.get("summary") or json.dumps(payload, default=str)[:120]
            print(f"{GREEN}    ✓ {prefix}{summary}{RESET}")
        elif kind == "block_failed":
            err = payload.get("error", json.dumps(payload, default=str)[:200])
            print(f"{RED}    ✗ {prefix}{err}{RESET}")
        elif kind == "brain_tool_call":
            summary = payload.get("summary", payload.get("tool", ""))
            print(f"{GRAY}      · {summary}{RESET}")
        elif kind == "run_completed":
            print(f"{BOLD}{GREEN}    ✓ done{RESET}")
        elif kind == "run_failed":
            err = payload.get("error", "")
            print(f"{BOLD}{RED}    ✗ failed: {err}{RESET}")
        else:
            print(f"{GRAY}    {kind}: {json.dumps(payload, default=str)[:120]}{RESET}")

        if kind in ("run_completed", "run_failed"):
            return kind == "run_completed"

    return False


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
    return {
        "github_issue": trigger,
        "_trigger":     trigger,
    }


def cmd_run(args):
    path = Path(args.yaml)
    if not path.exists():
        print(f"ERROR: file not found: {path}")
        sys.exit(1)

    raw_yaml     = path.read_text()
    cfg          = yaml.safe_load(raw_yaml)
    name         = cfg.get("name", path.stem)
    workflow_id  = cfg.get("id")
    server       = args.server.rstrip("/")
    workspace_id = args.workspace or cfg.get("workspace_id") or DEV_WORKSPACE
    token        = args.token
    api_key      = args.api_key
    on_block     = cfg.get("on") or {}
    trigger_type = next(iter(on_block), None)
    trigger_cfg  = on_block.get(trigger_type, {})

    json_h = api.headers(workspace_id, token, "application/json", api_key)
    yaml_h = api.headers(workspace_id, token, "application/x-yaml", api_key)

    print(f"\n{BOLD}▶ conduct run — {name}{RESET}")
    print(f"  server: {server}\n")

    # Use id from YAML; fall back to name lookup
    if not workflow_id:
        workflow_id = api.find_or_create_workflow(server, name, json_h)
    print(f"  workflow: {workflow_id}")
    print(f"  pushing YAML… ", end="", flush=True)
    api.req_text("PUT", f"{server}/workflows/{workflow_id}/yaml", yaml_h, raw_yaml)
    print(f"{GREEN}ok{RESET}\n")

    if trigger_type == "github_issue_labeled":
        repo  = trigger_cfg.get("repo_allowlist", "")
        label = trigger_cfg.get("label", "")

        print(f"  Fetching issues from {repo} with label '{label}'…")
        qs = urllib.parse.urlencode({"repo": repo, "label": label})
        issues = api.req("GET", f"{server}/credentials/github/issues?{qs}", json_h)

        if not issues:
            print(f"  No open issues found with label '{label}'.")
            return

        print(f"  Found {len(issues)} issue(s)\n")

        passed = failed = 0
        for issue in issues:
            print(f"{CYAN}  ── Issue #{issue['number']}: {issue['title']}{RESET}")
            state = _build_state(issue, repo)

            # Preflight: estimate turn budget before starting the run
            max_turns = None
            try:
                pf = api.req("POST", f"{server}/workflows/{workflow_id}/preflight", json_h, {
                    "issue_title": issue["title"],
                    "issue_body":  issue.get("body") or "",
                })
                suggested = pf.get("suggested_max_turns", 20)
                if suggested > 20:
                    print(f"{GRAY}  ⚠ estimated {suggested} turns — bumping max_turns{RESET}")
                    max_turns = suggested
            except Exception:
                pass  # preflight is best-effort

            payload = {"triggered_by": f"cli:issue#{issue['number']}", "initial_state": state}
            if max_turns:
                payload["max_turns"] = max_turns
            run   = api.req("POST", f"{server}/workflows/{workflow_id}/runs", json_h, payload)
            ok = _stream_run(server, workflow_id, run["id"], workspace_id, token, api_key)
            passed += ok
            failed += not ok
            print()

        print(f"{BOLD}  Summary: {passed} passed, {failed} failed{RESET}\n")

    else:
        run = api.req("POST", f"{server}/workflows/{workflow_id}/runs", json_h, {
            "triggered_by": "cli",
            "initial_state": {},
        })
        _stream_run(server, workflow_id, run["id"], workspace_id, token)


def main():
    parser = argparse.ArgumentParser(prog="conduct")
    parser.add_argument("--server",    required=True, help="Marshal API URL")
    parser.add_argument("--api-key",  help="CLI API key (set CLI_API_KEY on the server)")
    parser.add_argument("--token",    help="Bearer token for Clerk auth")
    parser.add_argument("--workspace", help="Workspace ID (overrides YAML workspace_id)")

    sub   = parser.add_subparsers(dest="command")
    run_p = sub.add_parser("run", help="Run a workflow from a YAML file")
    run_p.add_argument("yaml", help="Path to workflow YAML")

    args = parser.parse_args()
    if args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
