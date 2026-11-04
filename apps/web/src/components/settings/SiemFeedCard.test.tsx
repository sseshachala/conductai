import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import SiemFeedCard, { ago } from "./SiemFeedCard"

const authFetch = vi.hoisted(() => vi.fn())
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch }) }))
vi.mock("@/lib/WorkspaceContext", () => ({ useWorkspace: () => ({ activeWorkspace: { id: "ws1" } }) }))

const now = () => new Date().toISOString()
const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString()

function respond(body: unknown, ok = true, status = 200) {
  authFetch.mockResolvedValue({ ok, status, json: async () => body })
}

beforeEach(() => authFetch.mockReset())
afterEach(cleanup)

describe("SIEM feed card", () => {
  it("shows setup when no collector has pulled", async () => {
    respond({ available: true, collectors: [], stale_after_seconds: 900 })
    render(<SiemFeedCard />)
    await waitFor(() => expect(screen.getByTestId("siem-feed-badge").textContent).toBe("Not connected"))
    expect(screen.getByText(/conduct audit feed --follow/)).toBeTruthy()
    expect(authFetch.mock.calls[0][0]).toContain("/workspaces/ws1/audit-log/feed-status")
  })

  it("lists live collectors without the setup hint", async () => {
    respond({ available: true, stale_after_seconds: 900, collectors: [
      { actor_id: "u1", actor_email: "siem@acme.io", last_pull_at: now(), cursor_ts: now(), lag_seconds: 75, last_page_events: 12, stale: false },
    ] })
    render(<SiemFeedCard />)
    await waitFor(() => expect(screen.getByTestId("siem-feed-badge").textContent).toBe("Receiving"))
    expect(screen.getByText("siem@acme.io")).toBeTruthy()
    expect(screen.getByText("12 events")).toBeTruthy()
    expect(screen.queryByText(/conduct audit feed --follow/)).toBeNull()
  })

  it("flags a stale collector", async () => {
    respond({ available: true, stale_after_seconds: 900, collectors: [
      { actor_id: "u1", actor_email: null, last_pull_at: minutesAgo(40), cursor_ts: minutesAgo(41), lag_seconds: 2460, last_page_events: 0, stale: true },
    ] })
    render(<SiemFeedCard />)
    await waitFor(() => expect(screen.getByTestId("siem-feed-badge").textContent).toBe("Stale"))
    expect(screen.getByText(/No pull in the last 15 minutes/)).toBeTruthy()
  })

  it("hides itself without permission", async () => {
    respond({ detail: "forbidden" }, false, 403)
    const { container } = render(<SiemFeedCard />)
    await waitFor(() => expect(authFetch).toHaveBeenCalled())
    await waitFor(() => expect(container.innerHTML).toBe(""))
  })

  it("formats durations", () => {
    expect(ago(30)).toBe("30s")
    expect(ago(600)).toBe("10m")
    expect(ago(7200)).toBe("2h")
    expect(ago(3 * 86400)).toBe("3d")
  })
})
