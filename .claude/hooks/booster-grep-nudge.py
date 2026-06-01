#!/usr/bin/env python3
"""Booster grep nudge — blocks semantic Grep and redirects to search_context."""
import json
import sys

data = json.load(sys.stdin)
pattern = data.get("tool_input", {}).get("pattern", "")

if not pattern:
    sys.exit(0)

REGEX_CHARS = set(r"^$*+?[](){}\\|.")
is_regex = any(c in REGEX_CHARS for c in pattern)
word_count = len(pattern.split())

if not is_regex and word_count >= 2:
    print(
        f"[booster] Grep blocked for semantic pattern \'{pattern}\'. "
        "Use mcp__agent-booster__search_context instead — it searches by meaning "
        "across all indexed symbols and returns ranked results with far fewer tokens."
    )
    sys.exit(2)

sys.exit(0)
