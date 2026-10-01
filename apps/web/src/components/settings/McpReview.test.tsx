import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { McpReview } from "./McpReview"

const authFetch = vi.hoisted(() => vi.fn())
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch }) }))

beforeEach(() => authFetch.mockReset())
afterEach(cleanup)

describe("MCP review", () => {
  it("saves response mode with the current revision", async () => {
    const changed = vi.fn()
    const governance = { state: "approved" as const, revision: 3, response_mode: "block" as const }
    authFetch.mockResolvedValue({ ok: true, json: async () => ({ governance }) })
    render(<McpReview id="server" governance={{ state: "approved", revision: 2 }} onChange={changed} />)
    expect((screen.getByLabelText("Save response inspection") as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText("JSON response inspection"), { target: { value: "block" } })
    fireEvent.click(screen.getByLabelText("Save response inspection"))
    await waitFor(() => expect(changed).toHaveBeenCalledWith(governance))
    expect(JSON.parse(authFetch.mock.calls[0][1].body)).toEqual({ action: "response_policy", mode: "block", revision: 2, digest: null })
  })

  it("does not show inspection settings before enrollment", () => {
    render(<McpReview id="server" onChange={vi.fn()} />)
    expect(screen.queryByLabelText("JSON response inspection")).toBeNull()
  })

  it("does not approve without inspecting", () => {
    render(<McpReview id="server" governance={{ state: "needs_review", revision: 1 }} onChange={vi.fn()} />)
    expect((screen.getByText("Approve inspected tools") as HTMLButtonElement).disabled).toBe(true)
    expect(authFetch).not.toHaveBeenCalled()
  })

  it("sends inspected digest and current revision", async () => {
    const changed = vi.fn()
    authFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ tools: [{ name: "read", description: "Reads", inputSchema: {} }], digest: "a".repeat(64) }) })
    authFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ governance: { state: "approved", revision: 2 } }) })
    render(<McpReview id="server" governance={{ state: "needs_review", revision: 1 }} onChange={changed} />)
    fireEvent.click(screen.getByText("Inspect tools"))
    await screen.findByText("read")
    fireEvent.click(screen.getByText("Approve inspected tools"))
    await waitFor(() => expect(changed).toHaveBeenCalledWith({ state: "approved", revision: 2 }))
    expect(JSON.parse(authFetch.mock.calls[1][1].body)).toEqual({ action: "approve", revision: 1, digest: "a".repeat(64) })
  })

  it("restores quarantined servers for review, not direct approval", () => {
    render(<McpReview id="server" governance={{ state: "quarantined", revision: 4 }} onChange={vi.fn()} />)
    expect(screen.queryByText("Approve inspected tools")).toBeNull()
    expect(screen.getByText("Restore for review")).toBeTruthy()
  })

  it("surfaces denied mutations without changing state", async () => {
    const changed = vi.fn()
    authFetch.mockResolvedValue({ ok: false, json: async () => ({ detail: "Permission denied" }) })
    render(<McpReview id="server" onChange={changed} />)
    fireEvent.click(screen.getByText("Require review"))
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Permission denied")
    expect(changed).not.toHaveBeenCalled()
  })
})
