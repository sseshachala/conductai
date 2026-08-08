#!/usr/bin/env python3
"""Pre-commit hook — block commits that add a broken skill_pack JSON.

Mirrors .claude/hooks/validate-playbooks.py. Fires when a `git commit` or
`git add` touches an `apps/api/app/modules/guard/skill_packs/*.json` file.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


def main() -> None:
    hook_input = json.load(sys.stdin)
    command = hook_input.get("tool_input", {}).get("command", "")

    if "git commit" not in command and "git add" not in command:
        sys.exit(0)

    repo_root = "/Users/sudhiseshachala/projects/marshal"
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo_root, capture_output=True, text=True,
    )
    changed = [
        f for f in result.stdout.splitlines()
        if f.startswith("apps/api/app/modules/guard/skill_packs/")
        and f.endswith(".json")
    ]
    if not changed:
        sys.exit(0)

    venv_python = os.path.join(repo_root, "apps/api/.venv/bin/python3")
    if not os.path.exists(venv_python):
        sys.exit(0)

    validation = subprocess.run(
        [venv_python, "scripts/validate_all_skill_packs.py"],
        cwd=os.path.join(repo_root, "apps/api"),
        capture_output=True, text=True,
    )
    if validation.returncode != 0:
        print(json.dumps({
            "decision": "block",
            "reason": (
                "Skill-pack validation failed — fix before committing:\n"
                + (validation.stderr or validation.stdout).strip()
            ),
        }))
        sys.exit(0)


if __name__ == "__main__":
    main()
