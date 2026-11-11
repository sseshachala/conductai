import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import SiemFeedTokens from "./SiemFeedTokens"

const authFetch = vi.hoisted(() => vi.fn())
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch }) }))

const res = (body: unknown, ok = true, status = 200) => ({ ok, status, json: async () => body, text: async () => JSON.stringify(body) })

beforeEach(() => authFetch.mockReset())
afterEach(cleanup)

describe("SiemFeedTokens", () => {
  it("lazy-loads, creates a token and shows it once", async () => {
    authFetch
      .mockResolvedValueOnce(res([]))
      .mockResolvedValueOnce(res({ id: "t1", name: "splunk", token: "cond_feed_SECRET", token_prefix: "cond_feed_ab12", scope: "audit_feed", status: "active" }, true, 201))
      .mockResolvedValueOnce(res([{ id: "t1", name: "splunk", token_prefix: "cond_feed_ab12", scope: "audit_feed", status: "active" }]))
    render(<SiemFeedTokens workspaceId="ws1" />)
    expect(authFetch).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText("Feed tokens"))
    await waitFor(() => expect(screen.getByLabelText("Feed token name")).toBeTruthy())
    fireEvent.change(screen.getByLabelText("Feed token name"), { target: { value: "splunk" } })
    fireEvent.click(screen.getByText("Create token"))
    await waitFor(() => expect(screen.getByTestId("feed-token-once").textContent).toContain("cond_feed_SECRET"))
    expect(authFetch.mock.calls[1][0]).toContain("/workspaces/ws1/audit-feed-tokens")
    fireEvent.click(screen.getByText("Done"))
    expect(screen.queryByText(/cond_feed_SECRET/)).toBeNull()
    await waitFor(() => expect(screen.getByLabelText("Revoke splunk")).toBeTruthy())
  })

  it("explains non-admins cannot manage tokens", async () => {
    authFetch.mockResolvedValue(res({ detail: "forbidden" }, false, 403))
    render(<SiemFeedTokens workspaceId="ws1" />)
    fireEvent.click(screen.getByText("Feed tokens"))
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/admins/))
  })
})
