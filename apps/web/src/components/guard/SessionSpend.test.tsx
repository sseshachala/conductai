import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { SessionSpend, SessionSpendSummary, type SessionSpendEvidence } from "./SessionSpend"

const state = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch, workspaceId: "workspace" }) }))

const evidence: SessionSpendEvidence = {
  link_status: "session_id_linked",
  reported: { snapshot_count: 2, truncated: false, estimated_microdollars: 500, cost_status: "estimated", unpriced_snapshot_count: 0 },
  gateway: { request_count: 1, receipt_count: 2, truncated: false, calculated_cost_microdollars: { value: 400, status: "complete" } },
}

describe("session spend", () => {
  it("keeps overlapping sources separate and counts attempts", () => {
    render(<SessionSpendSummary data={evidence} />)
    expect(screen.getByText(/Reported estimate: \$0.000500/)).toBeTruthy()
    expect(screen.getByText(/Gateway recorded cost: \$0.000400/)).toBeTruthy()
    expect(screen.getByText(/1 Gateway requests · 2 attempts/)).toBeTruthy()
    expect(screen.getByText(/Token overlap unverified/)).toBeTruthy()
    expect(screen.queryByText(/0.000900/)).toBeNull()
  })
  it("does not present unknown or truncated costs as complete", () => {
    render(<SessionSpendSummary data={{ ...evidence, link_status: "unlinked", gateway: {
      ...evidence.gateway, truncated: true, calculated_cost_microdollars: { value: null, status: "unavailable" },
    } }} />)
    expect(screen.getByText(/Gateway recorded cost: Unavailable/)).toBeTruthy()
    expect(screen.getByText("No linked Gateway receipts")).toBeTruthy()
    expect(screen.getByRole("status").textContent).toContain("Partial session")
  })
  it("loads from the selected workspace and refreshes", async () => {
    state.fetch.mockReset().mockResolvedValue({ ok: true, json: async () => evidence })
    render(<SessionSpend eventId="event" />)
    await screen.findByText(/Gateway recorded cost/)
    expect(state.fetch.mock.calls[0][0]).toContain("/session-usage/event/reconciliation?workspace_id=workspace")
    fireEvent.click(screen.getByRole("button", { name: "Refresh session spend" }))
    await waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(2))
  })
  it("shows API denial without substituting a zero cost", async () => {
    state.fetch.mockReset().mockResolvedValue({ ok: false })
    render(<SessionSpend eventId="event" />)
    expect((await screen.findByRole("alert")).textContent).toBe("Session spend unavailable")
    expect(screen.queryByText(/Gateway recorded cost/)).toBeNull()
  })
})
