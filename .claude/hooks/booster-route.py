#!/usr/bin/env python3
"""Booster route hook — recommends model tier at the start of every user turn."""
import json
import re
import subprocess
import sys
from pathlib import Path

data = json.load(sys.stdin)
message = data.get("message", "")

if not message or len(message.strip()) < 10:
    sys.exit(0)

# Strip control characters and null bytes before passing to subprocess
safe_message = re.sub(r'[\x00-\x1f\x7f]', ' ', message).strip()[:300]

# Derive project root from this hook's known location — never trust external cwd
safe_cwd = Path(__file__).resolve().parent.parent.parent

try:
    result = subprocess.run(
        ["booster", "route", safe_message],
        capture_output=True,
        text=True,
        timeout=5,
        cwd=str(safe_cwd),
    )
    recommendation = result.stdout.strip()
    if recommendation:
        print(f"[booster/route] {recommendation}")
except Exception:
    pass

sys.exit(0)
