#!/usr/bin/env python3
"""
End-to-end test for the Autopilot agent against conductai-testbed-node.

Modes
-----
E2E (default)
  Creates a real GitHub issue, applies the "autopilot-ready" label, waits for
  Autopilot to open a PR, then cleans up (closes issue, closes PR, deletes branch).
  Slack notifications fire as normal — this is the full real-world path.

Silent (--silent)
  POSTs to /workflows/{id}/trigger with a synthetic event pointing at the testbed
  repo. No real GitHub issue is created. Streams the run and reports pass/fail.
  Useful for smoke-testing without Slack noise.

Usage
-----
  # E2E (real issue + Slack)
  python scripts/test_autopilot_node.py \\
    --gh-token ghp_xxx \\
    --api-key  <conduct-api-key> \\
    --workspace <workspace-id> \\
    --workflow-id <autopilot-workflow-id>

  # Silent (synthetic trigger, no Slack)
  python scripts/test_autopilot_node.py --silent \\
    --gh-token ghp_xxx \\
    --api-key  <conduct-api-key> \\
    --workspace <workspace-id> \\
    --workflow-id <autopilot-workflow-id>

  # Skip cleanup (leave issue/PR open for inspection)
  python scripts/test_autopilot_node.py --no-cleanup ...

Config fallback: if --api-key / --workspace are omitted, reads ~/.conduct/config.json.
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# ── constants ─────────────────────────────────────────────────────────────────

REPO           = "sseshachala/conductai-testbed-node"
TRIGGER_LABEL  = "autopilot-ready"
CONDUCT_SERVER = "https://api.conductai.ai"
GH_API         = "https://api.github.com"

# Simple, self-contained task: add a /health endpoint.
# - Does not touch existing code
# - Can be verified by reading the PR diff
# - Autopilot can implement it in one pass
ISSUE_TITLE = "[TEST] Add GET /health endpoint"
ISSUE_BODY  = """\
Add a `GET /health` route to the Express app that returns:

```json
{"status": "ok", "timestamp": "<ISO-8601 string>"}
```

Requirements:
- HTTP 200
- JSON content-type
- `timestamp` is the current UTC time in ISO format

This is an automated test run by Conduct AI. Please prefix the branch and PR \
title with `[TEST]`.
"""

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
RED    = "\033[31m"
BLUE   = "\033[34m"
GRAY   = "\033[90m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_conduct_config() -> dict:
    p = Path.home() / ".conduct" / "config.json"
    return json.loads(p.read_text()) if p.exists() else {}


def gh(method: str, path: str, token: str, body=None):
    url  = f"{GH_API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req  = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"token {token}",
        "Accept":        "application/vnd.github+json",
        "Content-Type":  "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        try:
            detail = json.loads(body_text).get("message", body_text)
        except Exception:
            detail = body_text
        print(f"{RED}GitHub {e.code} {method} {path}: {detail}{RESET}")
        sys.exit(1)


def conduct(method: str, path: str, workspace_id: str, api_key: str, body=None):
    url  = f"{CONDUCT_SERVER}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req  = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type":  "application/json",
        "X-Workspace-Id": workspace_id,
        "X-Api-Key":     api_key,
    })
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        try:
            detail = json.loads(body_text).get("detail", body_text)
        except Exception:
            detail = body_text
        print(f"{RED}Conduct {e.code} {method} {path}: {detail}{RESET}")
        sys.exit(1)


def conduct_stream(path: str, workspace_id: str, api_key: str):
    """Yield SSE event dicts from a streaming endpoint."""
    req = urllib.request.Request(f"{CONDUCT_SERVER}{path}", headers={
        "X-Workspace-Id": workspace_id,
        "X-Api-Key":      api_key,
    })
    try:
        resp = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        print(f"{RED}Stream {e.code}: {e.read().decode()}{RESET}")
        sys.exit(1)

    buf = b""
    while True:
        chunk = resp.read(1)
        if not chunk:
            break
        buf += chunk
        if buf.endswith(b"\n\n"):
            text = buf.decode().strip()
            buf  = b""
            event = "message"
            for line in text.splitlines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        data = {"raw": line[5:].strip()}
                    data.setdefault("kind", event)
                    yield data


# ── E2E mode ──────────────────────────────────────────────────────────────────

def create_issue(gh_token: str) -> dict:
    print(f"  Creating issue in {REPO}…")
    issue = gh("POST", f"/repos/{REPO}/issues", gh_token, {
        "title": ISSUE_TITLE,
        "body":  ISSUE_BODY,
    })
    print(f"  {GREEN}✓ Issue #{issue['number']}:{RESET} {issue['title']}")
    print(f"    {GRAY}{issue['html_url']}{RESET}")
    return issue


def apply_label(gh_token: str, issue_number: int):
    print(f"  Applying label '{TRIGGER_LABEL}'…")
    gh("POST", f"/repos/{REPO}/issues/{issue_number}/labels", gh_token, {
        "labels": [TRIGGER_LABEL],
    })
    print(f"  {GREEN}✓ Label applied — webhook should fire now{RESET}")


def wait_for_pr(gh_token: str, issue_number: int, timeout: int = 600) -> dict | None:
    branch_prefix = f"autopilot/issue-{issue_number}"
    print(f"\n  Polling for PR from branch '{branch_prefix}'…")
    deadline = time.time() + timeout
    dots = 0
    while time.time() < deadline:
        prs = gh("GET", f"/repos/{REPO}/pulls?state=open&per_page=20", gh_token)
        for pr in prs:
            if pr["head"]["ref"].startswith(branch_prefix) or f"#{issue_number}" in pr["title"]:
                print(f"\n  {GREEN}✓ PR found:{RESET} {pr['title']}")
                print(f"    {GRAY}{pr['html_url']}{RESET}")
                return pr
        print("." if dots % 60 else f"\n  waiting", end="", flush=True)
        dots += 1
        time.sleep(10)
    print()
    return None


def cleanup_e2e(gh_token: str, issue_number: int, pr: dict | None, no_cleanup: bool):
    if no_cleanup:
        print(f"\n{YELLOW}--no-cleanup set — leaving issue/PR open for inspection.{RESET}")
        return

    print(f"\n{BOLD}Cleaning up…{RESET}")

    # Close the issue
    gh("PATCH", f"/repos/{REPO}/issues/{issue_number}", gh_token, {"state": "closed"})
    print(f"  {GREEN}✓ Issue #{issue_number} closed{RESET}")

    if pr:
        pr_number = pr["number"]
        branch    = pr["head"]["ref"]

        # Close the PR
        gh("PATCH", f"/repos/{REPO}/pulls/{pr_number}", gh_token, {"state": "closed"})
        print(f"  {GREEN}✓ PR #{pr_number} closed{RESET}")

        # Delete the branch
        try:
            gh("DELETE", f"/repos/{REPO}/git/refs/heads/{branch}", gh_token)
            print(f"  {GREEN}✓ Branch '{branch}' deleted{RESET}")
        except SystemExit:
            print(f"  {YELLOW}⚠ Could not delete branch '{branch}' (may already be gone){RESET}")


def run_e2e(args, workspace_id: str, api_key: str):
    print(f"\n{BOLD}▶ Autopilot E2E test — {REPO}{RESET}")
    print(f"  Mode: {CYAN}real GitHub issue + webhook{RESET}\n")

    issue = create_issue(args.gh_token)
    apply_label(args.gh_token, issue["number"])

    pr = wait_for_pr(args.gh_token, issue["number"], timeout=args.timeout)

    print()
    if pr:
        print(f"{BOLD}{GREEN}✓ PASSED{RESET} — Autopilot opened PR #{pr['number']}")
        print(f"  {pr['html_url']}")
    else:
        print(f"{BOLD}{RED}✗ FAILED{RESET} — No PR appeared within {args.timeout}s")

    cleanup_e2e(args.gh_token, issue["number"], pr, args.no_cleanup)
    return bool(pr)


# ── Silent mode ───────────────────────────────────────────────────────────────

def run_silent(args, workspace_id: str, api_key: str):
    print(f"\n{BOLD}▶ Autopilot silent test — {REPO}{RESET}")
    print(f"  Mode: {CYAN}synthetic trigger (no Slack, no real issue){RESET}\n")

    owner, repo_name = REPO.split("/", 1)
    clone_url = f"https://github.com/{REPO}.git"

    payload = {
        "action": "labeled",
        "label":  {"name": TRIGGER_LABEL},
        "issue": {
            "number":   9001,
            "title":    "[TEST] Add GET /health endpoint",
            "body":     ISSUE_BODY,
            "html_url": f"https://github.com/{REPO}/issues/9001",
            "user":     {"login": "conductai-test-bot"},
            "labels":   [{"name": TRIGGER_LABEL}],
        },
        "repository": {
            "full_name":     REPO,
            "name":          repo_name,
            "owner":         {"login": owner},
            "default_branch": "main",
            "clone_url":     clone_url,
        },
        "sender": {"login": "conductai-test-bot"},
    }

    resp = conduct(
        "POST", f"/workflows/{args.workflow_id}/trigger",
        workspace_id, api_key, payload,
    )
    run_id = resp.get("run_id")
    print(f"  {GRAY}run: {run_id}{RESET}\n")

    passed = False
    for event in conduct_stream(
        f"/workflows/{args.workflow_id}/runs/{run_id}/stream",
        workspace_id, api_key,
    ):
        kind    = event.get("kind", "")
        bid     = event.get("block_id") or ""
        payload_ev = event.get("payload", event)
        prefix  = f"[{bid}] " if bid else ""

        if kind == "block_started":
            label = payload_ev.get("label") or payload_ev.get("type", "")
            print(f"{BLUE}  ▶ {prefix}{label}{RESET}")
        elif kind == "block_completed":
            summary = payload_ev.get("summary") or json.dumps(payload_ev, default=str)[:120]
            print(f"{GREEN}  ✓ {prefix}{summary}{RESET}")
        elif kind == "block_failed":
            err = payload_ev.get("error", json.dumps(payload_ev, default=str)[:200])
            print(f"{RED}  ✗ {prefix}{err}{RESET}")
        elif kind == "brain_tool_call":
            summary = payload_ev.get("summary", payload_ev.get("tool", ""))
            print(f"{GRAY}    · {summary}{RESET}")
        elif kind == "run_completed":
            print(f"\n{BOLD}{GREEN}✓ PASSED{RESET}")
            passed = True
            break
        elif kind == "run_failed":
            err = payload_ev.get("error", "")
            print(f"\n{BOLD}{RED}✗ FAILED: {err}{RESET}")
            break

    return passed


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="E2E test for Autopilot against conductai-testbed-node",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--gh-token",     required=True,  help="GitHub PAT with repo + issues scope")
    p.add_argument("--workflow-id",  required=True,  help="Autopilot workflow ID in Conduct")
    p.add_argument("--api-key",      help="Conduct API key (or set in ~/.conduct/config.json)")
    p.add_argument("--workspace",    help="Workspace ID (or set in ~/.conduct/config.json)")
    p.add_argument("--silent",       action="store_true",
                   help="Use synthetic trigger — no real GitHub issue, no Slack")
    p.add_argument("--no-cleanup",   action="store_true",
                   help="Skip cleanup — leave issue/PR open for inspection")
    p.add_argument("--timeout",      type=int, default=600,
                   help="E2E mode: seconds to wait for PR (default: 600)")
    args = p.parse_args()

    # Resolve auth from config file if not passed
    cfg        = _load_conduct_config()
    api_key    = args.api_key    or cfg.get("api_key")
    workspace  = args.workspace  or cfg.get("workspace")

    if not api_key:
        print(f"{RED}No API key. Pass --api-key or run: conduct login --api-key <key>{RESET}")
        sys.exit(1)
    if not workspace:
        print(f"{RED}No workspace. Pass --workspace or run: conduct login --workspace <id>{RESET}")
        sys.exit(1)

    ok = run_silent(args, workspace, api_key) if args.silent \
        else run_e2e(args, workspace, api_key)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
