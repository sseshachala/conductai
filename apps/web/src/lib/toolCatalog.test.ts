import { describe, expect, it } from "vitest"
import { setupTools, toolCatalog } from "./toolCatalog"
import { discoveryLabel } from "./discovery"

describe("shared tool catalog", () => {
  it("preserves the existing setup surfaces and compatible operations", () => {
    expect(setupTools.map(tool => [tool.id, tool.gateway?.operation])).toEqual([
      ["claude-code", "anthropic_messages"],
      ["codex", "openai_responses"],
      ["copilot-cli", "openai_responses"],
    ])
  })

  it("uses catalog labels without inventing installation evidence", () => {
    for (const tool of toolCatalog) {
      expect(discoveryLabel(tool.id)).toBe(tool.label)
      expect(tool).not.toHaveProperty("verified")
      expect(tool).not.toHaveProperty("protected")
    }
    expect(discoveryLabel("connection_verified")).toBe("Connection verified")
    expect(discoveryLabel("new-tool")).toBe("new-tool")
  })
})
