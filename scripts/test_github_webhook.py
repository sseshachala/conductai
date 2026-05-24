#!/usr/bin/env python3
"""
CLI test: verify GitHub PAT can list and create webhooks on a repo.

Usage:
  python scripts/test_github_webhook.py --token ghp_xxx --repo owner/repo

Steps:
  1. Verify token identity (GET /user)
  2. Check repo access (GET /repos/{owner}/{repo})
  3. List existing hooks (GET /repos/{owner}/{repo}/hooks) — needs admin:repo_hook
  4. Dry-run: print what webhook URL would be registered
  5. Optional live create+delete with --create flag
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

API = "https://api.github.com"
WEBHOOK_URL_TEMPLATE = "https://api.conductai.ai/webhooks/inbound/{workflow_id}"
TEST_WORKFLOW_ID = "00000000-0000-0000-0000-000000000001"


def gh(method: str, path: str, token: str, body=None):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_bytes = e.read()
        try:
            err_body = json.loads(body_bytes)
        except Exception:
            err_body = body_bytes.decode()
        return e.code, err_body


def check(label: str, ok: bool, detail: str = ""):
    mark = "✅" if ok else "❌"
    print(f"  {mark}  {label}", f"— {detail}" if detail else "")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Test GitHub PAT for webhook registration")
    parser.add_argument("--token", required=True, help="GitHub PAT (fine-grained or classic)")
    parser.add_argument("--repo", required=True, help="owner/repo (e.g. sseshachala/conductai)")
    parser.add_argument("--create", action="store_true", help="Actually create+delete a test webhook")
    args = parser.parse_args()

    token = args.token
    repo = args.repo
    passed = 0
    failed = 0

    print("\n── Step 1: Token identity ──")
    status, data = gh("GET", "/user", token)
    if check("GET /user", status == 200, f"status={status}"):
        print(f"       Authenticated as: {data.get('login')} ({data.get('name')})")
        passed += 1
    else:
        print(f"       Response: {data}")
        failed += 1

    print("\n── Step 2: Repo access ──")
    status, data = gh("GET", f"/repos/{repo}", token)
    if check("GET /repos/{repo}", status == 200, f"status={status}"):
        perms = data.get("permissions", {})
        print(f"       Permissions: admin={perms.get('admin')} push={perms.get('push')} pull={perms.get('pull')}")
        if not perms.get("admin"):
            print("       ⚠️  No admin permission — webhook creation will fail")
        passed += 1
    else:
        print(f"       Response: {data}")
        failed += 1

    print("\n── Step 3: List existing webhooks ──")
    status, data = gh("GET", f"/repos/{repo}/hooks", token)
    if check("GET /repos/{repo}/hooks", status == 200, f"status={status}"):
        print(f"       Existing hooks: {len(data)}")
        for h in data:
            print(f"         id={h['id']}  url={h['config'].get('url','?')}  active={h['active']}")
        passed += 1
    elif status == 403:
        print(f"       Response: {data}")
        print("       ⚠️  403 = PAT missing 'Administration: Read & Write' (fine-grained)")
        print("          or 'admin:repo_hook' scope (classic)")
        print("          OR the GitHub org has restricted fine-grained PATs")
        print("          → Check: GitHub org → Settings → Personal access tokens → Policies")
        failed += 1
    else:
        print(f"       Response: {data}")
        failed += 1

    webhook_url = WEBHOOK_URL_TEMPLATE.format(workflow_id=TEST_WORKFLOW_ID)
    print(f"\n── Step 4: Dry-run webhook payload ──")
    payload = {
        "name": "web",
        "active": True,
        "events": ["issues"],
        "config": {"url": webhook_url, "content_type": "json"},
    }
    print(f"       Would POST to: /repos/{repo}/hooks")
    print(f"       Webhook URL:   {webhook_url}")
    print(f"       Events:        {payload['events']}")

    if args.create:
        print("\n── Step 5: Live create+delete test ──")
        status, data = gh("POST", f"/repos/{repo}/hooks", token, payload)
        if check("POST /repos/{repo}/hooks", status == 201, f"status={status}"):
            hook_id = data["id"]
            print(f"       Created hook id={hook_id}")
            passed += 1
            # Clean up
            del_status, _ = gh("DELETE", f"/repos/{repo}/hooks/{hook_id}", token)
            check("DELETE (cleanup)", del_status == 204, f"status={del_status}")
        else:
            print(f"       Response: {json.dumps(data, indent=8)}")
            failed += 1
    else:
        print("       (skip — pass --create to actually create+delete a test hook)")

    print("\n── Step 6: Recent webhook deliveries ──")
    status, data = gh("GET", f"/repos/{repo}/hooks/630200814/deliveries?per_page=10", token)
    # Try to find hook ID from step 3 dynamically if available
    status6, data6 = gh("GET", f"/repos/{repo}/hooks", token)
    if status6 == 200 and data6:
        hook_id = data6[0]["id"]
        status, data = gh("GET", f"/repos/{repo}/hooks/{hook_id}/deliveries?per_page=10", token)
    if check("GET hook deliveries", status == 200, f"status={status}"):
        if not data:
            print("       No deliveries yet — webhook hasn't been called")
        for d in data:
            icon = "✅" if d.get("status_code", 0) < 300 else "❌"
            print(f"         {icon}  id={d['id']}  event={d['event']}  action={d.get('action','?')}  status={d.get('status_code','?')}  at={d['delivered_at']}")
        passed += 1
    else:
        print(f"       Response: {data}")
        failed += 1

    print(f"\n── Result: {passed} passed, {failed} failed ──\n")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
