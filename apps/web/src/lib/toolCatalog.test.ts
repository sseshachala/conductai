import { describe, expect, it } from "vitest"
import { setupTools, toolCatalog } from "./toolCatalog"
import { discoveryLabel } from "./discovery"

describe("shared tool catalog", () => {
  it("preserves the existing setup surfaces and compatible operations", () => {
    expect(setupTools.map(tool => [tool.id, tool.gateway?.operation])).toEqual([
      ["claude-code", "anthropic_messages"],
      ["codex", "openai_responses"],
      ["cursor", undefined],
      ["windsurf", undefined],
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

  it("shares declarative adapters without treating capability as live verification", () => {
    for (const tool of toolCatalog) {
      expect(tool.adapter.version).toBe(1)
      expect(tool.adapter.mcp.length).toBeGreaterThan(0)
      expect(tool.adapter).not.toHaveProperty("command")
    }
    for (const id of ["cursor", "windsurf"]) {
      const tool = toolCatalog.find(tool => tool.id === id)!
      expect(tool.adapter.usage).toBeNull()
      expect(tool.live_acceptance).toBe("pending")
    }
  })
})
