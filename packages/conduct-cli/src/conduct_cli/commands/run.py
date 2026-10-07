"""`conduct run` and `conduct test`: trigger workflow runs and stream results."""
from __future__ import annotations

import json
import sys

from conduct_cli import api
from conduct_cli.commands.shared import (
    BOLD,
    CYAN,
    GRAY,
    GREEN,
    RED,
    RESET,
    YELLOW,
    _poll_run,
    _require_auth,
    _stream_run,
)
from conduct_cli.commands.workspace import _resolve_project


def cmd_test(args):
    server, workspace_id, token = _require_auth(args)
    hdrs = api.headers(workspace_id, token, "application/json")

    agent_names    = args.agents
    run_all        = getattr(args, "all", False)
    project_filter = getattr(args, "project", None)
    repo_override  = getattr(args, "repo", None)
    parallel       = getattr(args, "parallel", False)

    workflows = api.req("GET", f"{server}/workflows", hdrs)

    if project_filter:
        proj = _resolve_project(server, workspace_id, hdrs, project_filter)
        proj_id = str(proj["id"])
        workflows = [wf for wf in workflows if str(wf.get("project_id") or "") == proj_id]

    if run_all:
        targets = [wf for wf in workflows if wf.get("playbook_slug")]
        if not targets:
            print("No playbook-based agents found.")
            return
    else:
        targets = []
        for name in agent_names:
            match = next((wf for wf in workflows if wf["name"].lower() == name.lower()), None)
            if not match:
                print(f"{RED}Agent '{name}' not found. Run 'conduct agents' to see available agents.{RESET}")
                sys.exit(1)
            if not match.get("playbook_slug"):
                print(f"{YELLOW}⚠ '{name}' has no playbook_slug — no built-in test payload. Skipping.{RESET}")
                continue
            targets.append(match)

    if not targets:
        print("Nothing to test.")
        return

    proj_label = f" [{project_filter}]" if project_filter else ""
    mode_label = f"{GRAY} --parallel{RESET}" if parallel else ""
    print(f"\n{BOLD}▶ conduct test{proj_label} — {len(targets)} agent(s){RESET}{mode_label}\n")

    pr_override = getattr(args, "pr", None)

    def _build_payload(slug):
        payload: dict = {}
        if repo_override:
            owner, repo = (repo_override.split("/", 1) + [""])[:2]
            clone_url = f"https://github.com/{repo_override}.git"
            payload.update({
                "repo": repo_override,
                "clone_url": clone_url,
                "repo_owner": owner,
                "repo_name": repo,
                "repo_full_name": repo_override,
                "repository": {
                    "full_name": repo_override,
                    "name": repo,
                    "owner": {"login": owner},
                    "clone_url": clone_url,
                    "default_branch": "main",
                },
            })
        if pr_override:
            pr = int(pr_override)
            repo_path = repo_override or ""
            payload.update({
                "number": pr,
                "pull_request": {
                    "number": pr,
                    "html_url": f"https://github.com/{repo_path}/pull/{pr}" if repo_path else "",
                    "diff_url": f"https://github.com/{repo_path}/pull/{pr}.diff" if repo_path else "",
                    "title": f"PR #{pr}",
                    "user": {"login": ""},
                    "base": {"ref": "main"},
                    "head": {"ref": ""},
                },
            })
        return payload

    _run_tests(server, workspace_id, token, hdrs, targets, _build_payload, parallel=parallel)


def _run_tests(server, workspace_id, token, hdrs, targets, build_payload, *, parallel: bool = False):
    import threading

    if not parallel:
        results = []
        for wf in targets:
            name  = wf["name"]
            wf_id = str(wf["id"])
            slug  = wf.get("playbook_slug", "")
            print(f"{CYAN}── {name}{RESET} {GRAY}({slug}){RESET}")
            try:
                run = api.req("POST", f"{server}/workflows/{wf_id}/trigger", hdrs, build_payload(slug))
            except SystemExit:
                results.append((name, False, None))
                print()
                continue
            run_id = run.get("run_id")
            print(f"  {GRAY}run: {run_id}{RESET}")
            try:
                ok = _stream_run(server, wf_id, run_id, workspace_id, token)
            except Exception:
                ok = _poll_run(server, wf_id, run_id, hdrs)
            results.append((name, ok, run_id))
            print()
        _print_results(results)
        return

    # parallel: fire all triggers, then poll concurrently
    pending = []
    for wf in targets:
        name  = wf["name"]
        wf_id = str(wf["id"])
        slug  = wf.get("playbook_slug", "")
        print(f"  {GRAY}→ triggering {name}{RESET}")
        try:
            run    = api.req("POST", f"{server}/workflows/{wf_id}/trigger", hdrs, build_payload(slug))
            run_id = run.get("run_id")
            print(f"    {GRAY}run: {run_id}{RESET}")
            pending.append((name, wf_id, run_id))
        except SystemExit:
            pending.append((name, wf_id, None))

    print(f"\n  Polling {len(pending)} runs concurrently…\n")
    results_lock = threading.Lock()
    results: list = [None] * len(pending)

    def _poll(idx, name, wf_id, run_id):
        if run_id is None:
            with results_lock:
                results[idx] = (name, False, None)
            return
        ok = _poll_run(server, wf_id, run_id, hdrs)
        with results_lock:
            results[idx] = (name, ok, run_id)
        icon = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        print(f"  {icon}  {name}")

    threads = [
        threading.Thread(target=_poll, args=(i, name, wf_id, run_id), daemon=True)
        for i, (name, wf_id, run_id) in enumerate(pending)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    _print_results(results)


def _print_results(results):
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed

    print(f"\n{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}Results:{RESET}")
    for name, ok, run_id in results:
        icon = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        rid  = f"{GRAY}{run_id[:8]}…{RESET}" if run_id else ""
        print(f"  {icon}  {name:<40} {rid}")

    print()
    color = GREEN if failed == 0 else RED
    print(f"{BOLD}{color}{passed}/{len(results)} passed{RESET}\n")

    sys.exit(0 if failed == 0 else 1)


def _gh_api_get(url: str, token: str):
    import urllib.request, urllib.error
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _fetch_github_issue(repo: str, issue_number: int, token: str) -> dict:
    return _gh_api_get(f"https://api.github.com/repos/{repo}/issues/{issue_number}", token)


def _fetch_issues_by_label(repo: str, label: str, token: str) -> list:
    return _gh_api_get(
        f"https://api.github.com/repos/{repo}/issues?labels={label}&state=open&per_page=20",
        token,
    )


def _build_issue_trigger_payload(issue: dict, repo: str) -> dict:
    owner, repo_name = (repo.split("/", 1) + [""])[:2]
    return {
        "action": "labeled",
        "issue": {
            "number": issue["number"],
            "title": issue["title"],
            "body": issue.get("body") or "",
            "html_url": issue.get("html_url", ""),
            "user": issue.get("user") or {},
            "labels": issue.get("labels") or [],
        },
        "repository": {
            "full_name": repo,
            "name": repo_name,
            "owner": {"login": owner},
            "clone_url": f"https://github.com/{repo}.git",
            "default_branch": "main",
        },
    }


def _prompt_issue_choice(issues: list) -> dict:
    print(f"\n{BOLD}Multiple open issues found — choose one:{RESET}\n")
    for i, iss in enumerate(issues):
        print(f"  {BOLD}{i + 1}.{RESET} #{iss['number']} — {iss['title']}")
    print()
    while True:
        raw = input(f"Enter number [1–{len(issues)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(issues):
            return issues[int(raw) - 1]
        print(f"{RED}Invalid choice.{RESET}")


def cmd_run(args):
    server, workspace_id, token = _require_auth(args)
    json_h = api.headers(workspace_id, token, "application/json")

    # Fix 1: --input values go into state["inputs"], not top-level state.
    # {{inputs.key}} refs in YAML only resolve when the executor finds state["inputs"].
    run_inputs: dict = {}
    for kv in (args.input or []):
        if "=" not in kv:
            print(f"{RED}Bad --input format '{kv}' — expected key=value{RESET}")
            sys.exit(1)
        k, v = kv.split("=", 1)
        run_inputs[k] = v

    # Resolve agent by name
    target = args.agent
    workflows = api.req("GET", f"{server}/workflows", json_h)

    # Filter by project if given
    if args.project:
        projects = api.req("GET", f"{server}/workspaces/{workspace_id}/projects", json_h)
        proj = next((p for p in projects if p["name"].lower() == args.project.lower()), None)
        if not proj:
            print(f"{RED}Project '{args.project}' not found.{RESET}")
            sys.exit(1)
        workflows = [w for w in workflows if w.get("project_id") == proj["id"]]

    wf = next((w for w in workflows if w["name"].lower() == target.lower()), None)
    if not wf:
        print(f"{RED}Agent '{target}' not found. Run 'conduct agents' to list agents.{RESET}")
        sys.exit(1)

    workflow_id = wf["id"]

    # Fix 4: determine trigger type from workflow metadata.
    is_github_webhook = bool(wf.get("github_webhook"))
    slug = wf.get("playbook_slug") or ""
    is_issue_trigger = is_github_webhook and "issue" in slug

    print(f"\n{BOLD}▶ conduct run — {wf['name']}{RESET}")
    if run_inputs:
        for k, v in run_inputs.items():
            print(f"  {GRAY}{k}={v}{RESET}")
    print()

    # Fix 2: preflight receives run_inputs so turn estimates use real input context.
    try:
        pf = api.req("POST", f"{server}/workflows/{workflow_id}/preflight", json_h, {
            "run_inputs": run_inputs,
        })
        suggested = pf.get("suggested_max_turns", 20)
        files = pf.get("total_files", [])
        print(f"  {BOLD}Estimated turns:{RESET} {suggested}")
        if files:
            print(f"  {BOLD}Files likely to be modified:{RESET} {', '.join(files)}")
        print()
    except Exception:
        suggested = 20

    # Fix 4: extract github_token before building body so it never lands in state["inputs"].
    import os as _os
    gh_token = run_inputs.pop("github_token", None) or _os.environ.get("GITHUB_TOKEN")

    # Build the trigger body.
    # Fix 1: send inputs under "inputs" key so server puts them in state["inputs"].
    body: dict = {}
    if run_inputs:
        body["inputs"] = run_inputs

    # Fix 4: non-webhook triggers (manual/schedule) — flag so server skips trigger validation.
    if not is_github_webhook:
        body["__manual"] = True

    # Fix 4: github_issue_labeled — fire against a real issue when possible.
    if is_issue_trigger:
        repo = wf.get("github_hook_repo") or run_inputs.get("repo")
        label = wf.get("github_hook_label") or ""
        issue_number_raw = run_inputs.get("issue_number")
        if gh_token and repo:
            try:
                if issue_number_raw:
                    issue = _fetch_github_issue(repo, int(issue_number_raw), gh_token)
                    body.update(_build_issue_trigger_payload(issue, repo))
                    print(f"  {GRAY}issue: #{issue['number']} — {issue['title']}{RESET}\n")
                elif label:
                    issues = _fetch_issues_by_label(repo, label, gh_token)
                    if not issues:
                        print(f"{YELLOW}⚠ No open issues with label '{label}' in {repo}. Using test payload.{RESET}\n")
                    elif len(issues) == 1:
                        body.update(_build_issue_trigger_payload(issues[0], repo))
                        print(f"  {GRAY}issue: #{issues[0]['number']} — {issues[0]['title']}{RESET}\n")
                    else:
                        chosen = _prompt_issue_choice(issues)
                        body.update(_build_issue_trigger_payload(chosen, repo))
                        print(f"  {GRAY}issue: #{chosen['number']} — {chosen['title']}{RESET}\n")
            except Exception as _gh_err:
                print(f"{YELLOW}⚠ GitHub fetch failed ({_gh_err}). Using test payload.{RESET}\n")
        else:
            hint = "export GITHUB_TOKEN=<token>" if not gh_token else "workflow has no github_hook_repo"
            print(f"  {GRAY}No GitHub token — using test payload. ({hint}){RESET}\n")

    # #734: validate required inputs locally before POST — fail fast with clear error.
    try:
        vres = api.req("POST", f"{server}/workflows/{workflow_id}/validate-inputs", json_h,
                       {"inputs": body.get("inputs") or {}, "phase": "run"})
        missing = (vres or {}).get("missing") or []
        if missing:
            print(f"{RED}✗ Missing required inputs:{RESET}")
            for m in missing:
                print(f"  - {m['label']} ({m['key']})")
            print(f"\n{GRAY}Provide with --input {missing[0]['key']}=<value>{RESET}")
            sys.exit(2)
    except SystemExit:
        raise
    except Exception:
        pass  # validate endpoint is best-effort; backend will re-check on /trigger

    # Full preflight validation — credentials, auth chain, proxy, block config.
    # Blocks on errors so bad runs never start.
    try:
        vr = api.req("POST", f"{server}/workflows/{workflow_id}/validate", json_h, {})
        v_errors = (vr or {}).get("errors") or []
        if v_errors:
            print(f"{RED}✗ Cannot start run — preflight validation failed:{RESET}\n")
            for e in v_errors:
                lbl = e.get("label") or e.get("block_id") or "?"
                print(f"  {YELLOW}⚠  [{lbl}]{RESET} {e.get('message', '')}")
            print()
            sys.exit(2)
    except SystemExit:
        raise
    except Exception:
        pass  # best-effort — don't block run if validate endpoint itself errors

    # Fix 3: /trigger returns run_id, not id.
    if getattr(args, "max_turns", None):
        body["__max_turns"] = args.max_turns
    elif suggested > 20:
        body["__max_turns"] = suggested
    # #1515 P2 — opt-in Lens attach. Backend auto-mints a session; response
    # returns session_id. CLI stays terminal-native by default.
    if getattr(args, "lens", False):
        body["lens_attach"] = True
    run = api.req("POST", f"{server}/workflows/{workflow_id}/trigger", json_h, body)
    run_id = run.get("run_id") or run.get("id")
    lens_sid = run.get("session_id")
    if lens_sid:
        ui_url = server.replace("api.", "app.").rstrip("/") if "api." in server else server.rstrip("/")
        print(f"  {GRAY}lens: {ui_url}/lens/{lens_sid}{RESET}\n")
    _stream_run(server, workflow_id, run_id, workspace_id, token)
