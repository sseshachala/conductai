#!/usr/bin/env python3
"""Booster route hook — recommends model tier at the start of every user turn."""
import json
import subprocess
import sys

data = json.load(sys.stdin)
message = data.get("message", "")

if not message or len(message.strip()) < 10:
    sys.exit(0)

try:
    result = subprocess.run(
        ["booster", "route", message[:300]],
        capture_output=True,
        text=True,
        timeout=5,
        cwd=data.get("cwd", "."),
    )
    recommendation = result.stdout.strip()
    if recommendation:
        print(f"[booster/route] {recommendation}")
except Exception:
    pass

sys.exit(0)
