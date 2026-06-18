#!/usr/bin/env python3
"""Inject booster instructions into every subagent prompt so they use
mcp__agent-booster__search_context instead of Grep/Bash for searches."""
import json
import sys

data = json.load(sys.stdin)
prompt = data.get("tool_input", {}).get("prompt", "")

if not prompt:
    sys.exit(0)

BOOSTER_INSTRUCTION = (
    "\n\n[booster] IMPORTANT: This session has Agent Booster installed. "
    "For ANY search or code exploration task, use mcp__agent-booster__search_context "
    "instead of Grep or Bash grep/find. Use mcp__agent-booster__smart_read instead of "
    "Read for targeted file reads. Use mcp__agent-booster__get_symbols to survey a "
    "file's structure. These tools are faster, token-efficient, and already available."
)

if "mcp__agent-booster" not in prompt:
    new_prompt = prompt + BOOSTER_INSTRUCTION
    output = dict(data)
    output["tool_input"] = dict(data.get("tool_input", {}))
    output["tool_input"]["prompt"] = new_prompt
    print(json.dumps(output))

sys.exit(0)
