#!/usr/bin/env python3
"""Booster grep nudge — suggests search_context for semantic-looking Grep patterns."""
import json
import re
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
        f"[booster] '{pattern}' looks like a semantic search. "
        "Consider mcp__agent-booster__search_context instead of Grep — "
        "it searches by meaning across all indexed symbols, not just text match."
    )

sys.exit(0)
