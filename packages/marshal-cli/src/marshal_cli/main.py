import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from marshal_cli import api, github

RESET = "\033[0m"
BOLD  = "\033[1m"
GREEN = "\033[32m"
RED   = "\033[31m"
BLUE  = "\033[34m"
GRAY  = "\033[90m"
CYAN  = "\033[36m"

DEV_WORKSPACE = "00000000-0000-0000-0000-000000000001"


def _stream_run(server: str, workflow_id: str, run_id: str, workspace_id: str, token: str | None):
    qs = f"?workspace_id={workspace_id}"
    if token:
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


def cmd_run(args):
    path = Path(args.yaml)
    if not path.exists():
        print(f"ERROR: file not found: {path}")
        sys.exit(1)

    raw_yaml     = path.read_text()
    cfg          = yaml.safe_load(raw_yaml)
    name         = cfg.get("name", path.stem)
    server       = args.server.rstrip("/")
    workspace_id = cfg.get("workspace_id") or DEV_WORKSPACE
    token        = args.token

    # Read trigger config
    on_block     = cfg.get("on") or {}
    trigger_type = next(iter(on_block), None)
    trigger_cfg  = on_block.get(trigger_type, {})

    # GitHub token — from flag or env
    gh_token = args.github_token or os.environ.get("GITHUB_TOKEN")

    json_h = api.headers(workspace_id, token, "application/json")
    yaml_h = api.headers(workspace_id, token, "application/x-yaml")

    print(f"\n{BOLD}▶ marshal run — {name}{RESET}")
    print(f"  server: {server}\n")

    # 1. Find or create workflow, push YAML
    workflow_id = api.find_or_create_workflow(server, name, json_h)
    print(f"  workflow: {workflow_id}")
    print(f"  pushing YAML… ", end="", flush=True)
    api.req_text("PUT", f"{server}/workflows/{workflow_id}/yaml", yaml_h, raw_yaml)
    print(f"{GREEN}ok{RESET}\n")

    # 2. Build runs — one per matching issue
    if trigger_type == "github_issue_labeled":
        repo  = trigger_cfg.get("repo_allowlist", "")
        label = trigger_cfg.get("label", "")

        if not gh_token:
            print(f"{RED}ERROR: GitHub token required. Pass --github-token or set GITHUB_TOKEN env var.{RESET}")
            sys.exit(1)

        print(f"  Fetching issues from {repo} with label '{label}'…")
        issues = github.get_issues_with_label(repo, label, gh_token)

        if not issues:
            print(f"  No open issues found with label '{label}'.")
            return

        print(f"  Found {len(issues)} issue(s)\n")

        passed = failed = 0
        for issue in issues:
            print(f"{CYAN}  ── Issue #{issue['number']}: {issue['title']}{RESET}")
            state = github.build_state(issue, repo)
            run   = api.req("POST", f"{server}/workflows/{workflow_id}/runs", json_h, {
                "triggered_by": f"cli:issue#{issue['number']}",
                "initial_state": state,
            })
            ok = _stream_run(server, workflow_id, run["id"], workspace_id, token)
            if ok:
                passed += 1
            else:
                failed += 1
            print()

        print(f"{BOLD}  Summary: {passed} passed, {failed} failed{RESET}\n")

    else:
        # Non-webhook trigger — just run with empty state
        run = api.req("POST", f"{server}/workflows/{workflow_id}/runs", json_h, {
            "triggered_by": "cli",
            "initial_state": {},
        })
        _stream_run(server, workflow_id, run["id"], workspace_id, token)


def main():
    parser = argparse.ArgumentParser(prog="marshal")
    parser.add_argument("--server",       required=True, help="Marshal API URL")
    parser.add_argument("--token",        help="Bearer token for Clerk auth")
    parser.add_argument("--github-token", help="GitHub token (or set GITHUB_TOKEN env var)")

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
