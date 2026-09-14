import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AgentSessions } from "./AgentSessions"

const authFetch = vi.fn()
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch }) }))
vi.mock("@/lib/api", () => ({ API: "/api" }))
const row = {
  id: "aaaaaaaa-1111-4111-8111-111111111111",
  created_at: "2026-09-14T12:00:00Z", expires_at: "2026-09-14T20:00:00Z",
  refresh_token_expires_at: "2026-10-14T12:00:00Z", revoked_at: null,
  status: "active", is_current: true,
}
const reply = (data: unknown, status = 200) => ({ ok: status === 200, status, json: async () => data })

describe("AgentSessions", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    authFetch.mockReset()
    authFetch.mockResolvedValue(reply({ sessions: [row], has_more: false }))
  })
  it("shows session metadata and expands refresh expiry without any credentials", async () => {
    render(<AgentSessions workspaceId="workspace" identityId="agent" />)
    fireEvent.click(await screen.findByRole("button", { name: "aaaaaaaa" }))
    expect(screen.getByText(row.id)).toBeInTheDocument()
    expect(screen.getByText("Refresh expires")).toBeInTheDocument()
    expect(screen.getByText("This session")).toBeInTheDocument()
    expect(authFetch.mock.calls[0][0]).toBe("/api/workspaces/workspace/agent-identities/agent/sessions?limit=50&offset=0")
  })
  it("confirms revocation and updates only the selected session", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true)
    authFetch.mockResolvedValueOnce(reply({ sessions: [row, { ...row, id: "bbbbbbbb", is_current: false }], has_more: false }))
    authFetch.mockResolvedValueOnce(reply({ ...row, status: "revoked", revoked_at: row.created_at }))
    render(<AgentSessions workspaceId="workspace" identityId="agent" />)
    fireEvent.click(await screen.findByRole("button", { name: "Revoke session aaaaaaaa" }))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("current authenticated connection"))
    await screen.findByText("Revoked")
    expect(screen.getByText("Active")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Revoke session aaaaaaaa" })).toBeDisabled()
  })
  it("does not revoke after cancellation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false)
    render(<AgentSessions workspaceId="workspace" identityId="agent" />)
    fireEvent.click(await screen.findByRole("button", { name: "Revoke session aaaaaaaa" }))
    expect(authFetch).toHaveBeenCalledTimes(1)
  })
  it("shows an error without marking a failed revocation successful", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true)
    authFetch.mockResolvedValueOnce(reply({ sessions: [row], has_more: false }))
    authFetch.mockResolvedValueOnce(reply({}, 403))
    render(<AgentSessions workspaceId="workspace" identityId="agent" />)
    fireEvent.click(await screen.findByRole("button", { name: "Revoke session aaaaaaaa" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to revoke")
    expect(screen.getByText("Active")).toBeInTheDocument()
  })
  it("shows empty and denied states explicitly", async () => {
    authFetch.mockResolvedValueOnce(reply({ sessions: [], has_more: false }))
    authFetch.mockResolvedValueOnce(reply({}, 403))
    render(<AgentSessions workspaceId="workspace" identityId="agent" />)
    await screen.findByText("No authentication sessions for this agent.")
    fireEvent.click(screen.getByRole("button", { name: "Refresh sessions" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("permission")
  })
  it("loads the next page", async () => {
    authFetch.mockResolvedValueOnce(reply({ sessions: [row], has_more: true }))
    render(<AgentSessions workspaceId="workspace" identityId="agent" />)
    await screen.findByText("Active")
    fireEvent.click(screen.getByRole("button", { name: "Next sessions" }))
    await waitFor(() => expect(authFetch.mock.calls[1][0]).toContain("offset=50"))
  })
})
