#!/usr/bin/env python3
"""
Trigger the Security Patch Updater workflow with a test Dependabot-style payload.

Uses the authenticated /workflows/{id}/trigger endpoint — no HMAC secret needed.

Usage:
    python scripts/trigger_security_patch.py \
        --workflow-id <uuid> \
        --token <clerk_session_token> \
        [--api-url https://api.conductai.ai] \
        [--repo owner/repo] \
        [--package lodash] \
        [--cve CVE-2021-23337] \
        [--severity high]

Get your token: open conductai.ai, open DevTools → Application → Cookies → __session
"""
import argparse
import json
import sys
import urllib.request


DEFAULT_API = "https://api.conductai.ai"

DEFAULT_PAYLOAD = {
    "repo": "sseshachala/conductai",
    "clone_url": "https://github.com/sseshachala/conductai.git",
    "default_branch": "main",
    "advisory": {
        "package": "lodash",
        "severity": "high",
        "cve": "CVE-2021-23337",
        "patched_versions": ">=4.17.21",
        "description": "Prototype pollution in lodash before 4.17.21 via the set, setWith, pull, update, and updateWith methods.",
    },
}


def main():
    p = argparse.ArgumentParser(description="Trigger Security Patch Updater")
    p.add_argument("--workflow-id", required=True, help="Workflow UUID")
    p.add_argument("--token", required=True, help="Clerk session token (from __session cookie)")
    p.add_argument("--api-url", default=DEFAULT_API, help="API base URL")
    p.add_argument("--repo", help="owner/repo to patch (default: sseshachala/conductai)")
    p.add_argument("--package", help="Package name (default: lodash)")
    p.add_argument("--cve", help="CVE identifier (default: CVE-2021-23337)")
    p.add_argument("--severity", choices=["low", "medium", "high", "critical"], default="high")
    args = p.parse_args()

    payload = json.loads(json.dumps(DEFAULT_PAYLOAD))  # deep copy
    if args.repo:
        payload["repo"] = args.repo
        payload["clone_url"] = f"https://github.com/{args.repo}.git"
    if args.package:
        payload["advisory"]["package"] = args.package
    if args.cve:
        payload["advisory"]["cve"] = args.cve
    payload["advisory"]["severity"] = args.severity

    body = json.dumps(payload).encode()
    url = f"{args.api_url.rstrip('/')}/workflows/{args.workflow_id}/trigger"

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {args.token}",
        },
        method="POST",
    )

    print(f"POST {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print()

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"Response {resp.status}: {json.dumps(result, indent=2)}")
            if result.get("run_id"):
                print(f"\nWatch run: https://conductai.ai/runs/{result['run_id']}")
    except urllib.error.HTTPError as e:
        body_err = e.read().decode()
        print(f"Error {e.code}: {body_err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
