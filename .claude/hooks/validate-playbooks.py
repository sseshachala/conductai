#!/usr/bin/env python3
"""
Pre-commit hook: validate any changed playbook YAML files through the DSL loader.
Fires on git commit commands that touch apps/api/playbooks/*.yaml
"""
import json
import os
import subprocess
import sys

def main():
    hook_input = json.load(sys.stdin)
    tool_input = hook_input.get("tool_input", {})
    command = tool_input.get("command", "")

    # Only fire on git commit touching playbooks
    if "git commit" not in command and "git add" not in command:
        sys.exit(0)

    repo_root = "/Users/sudhiseshachala/projects/marshal"

    # Find changed playbook files
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo_root, capture_output=True, text=True
    )
    changed = [f for f in result.stdout.splitlines()
               if f.startswith("apps/api/playbooks/") and f.endswith(".yaml")
               and not f.endswith("base-autopilot.yaml")]  # base is not standalone

    if not changed:
        sys.exit(0)

    errors = []
    for rel_path in changed:
        path = os.path.join(repo_root, rel_path)
        validation = subprocess.run(
            ["python3", "-c", f"""
import sys
sys.path.insert(0, 'apps/api')
from app.dsl.loader import load_workflow
try:
    load_workflow(open('{path}').read())
    print("OK: {rel_path}")
except Exception as e:
    print(f"FAIL: {rel_path} — {{e}}", file=sys.stderr)
    sys.exit(1)
"""],
            cwd=repo_root, capture_output=True, text=True
        )
        if validation.returncode != 0:
            errors.append(f"{rel_path}: {validation.stderr.strip()}")

    if errors:
        print(json.dumps({
            "decision": "block",
            "reason": "Playbook DSL validation failed — fix before committing:\n" + "\n".join(errors)
        }))
        sys.exit(0)

    sys.exit(0)

if __name__ == "__main__":
    main()
