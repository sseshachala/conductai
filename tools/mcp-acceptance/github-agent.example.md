---
name: conduct-acceptance
description: Dedicated Conduct MCP acceptance canary
target: github-copilot
disable-model-invocation: true
tools: ['edit', 'conduct/guard_activity', 'conduct/conduct_current_workspace']
mcp-servers:
  conduct:
    type: http
    url: $COPILOT_MCP_CONDUCT_URL
    headers:
      Authorization: Bearer $COPILOT_MCP_CONDUCT_TOKEN
    tools: ['guard_activity', 'conduct_current_workspace']
---

Run only the MCP canary requested by the issue. Use the Conduct tools directly,
not shell, HTTP, or a substitute MCP client. Do not print credentials.
Write only the nonsecret marker and workspace UUID to acceptance-result.txt.
Include the marker and the issue number in the pull request description.
Do not change application code or merge the pull request.
