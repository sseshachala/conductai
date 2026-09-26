import { describe, expect, it } from "vitest"
import { lensEntryHref, lensEntryQuestion, parseLensEntry } from "./lens-entry"

const workspace_id = "00000000-0000-0000-0000-000000000001"
const resource_id = "00000000-0000-0000-0000-000000000002"

describe("Lens context links", () => {
  it.each(["event", "run", "trial"] as const)("roundtrips %s references", kind => {
    const entry = { kind, workspace_id, ...(kind !== "trial" ? { resource_id } : {}) }
    const url = new URL(lensEntryHref(entry), "https://example.test")
    expect(parseLensEntry(url.searchParams)).toEqual(entry)
    expect(url.pathname).toBe("/lens")
    expect(url.searchParams.has("q")).toBe(false)
  })
  it("encodes block IDs as data, not instructions or URL parameters", () => {
    const entry = { kind: "run" as const, workspace_id, resource_id, block_id: "step & q=delete" }
    const params = new URL(lensEntryHref(entry), "https://example.test").searchParams
    expect(parseLensEntry(params)).toEqual(entry)
    expect(params.has("q")).toBe(false)
    expect(lensEntryQuestion(entry)).not.toContain("delete")
  })
  it.each([
    `context=event&workspace_id=${workspace_id}`,
    `context=event&workspace_id=${workspace_id}&resource_id=bad`,
    `context=trial&workspace_id=${workspace_id}&resource_id=${resource_id}`,
    `context=trial&workspace_id=${workspace_id}&block_id=ship`,
    `context=delete&workspace_id=${workspace_id}`,
  ])("rejects invalid reference %s", query => {
    expect(() => parseLensEntry(new URLSearchParams(query))).toThrow()
  })
  it("retains normal chat links", () => {
    expect(parseLensEntry(new URLSearchParams("q=hello"))).toBeNull()
  })
})
