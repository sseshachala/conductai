import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AgentActivitySessions } from "./AgentActivitySessions"

const authFetch = vi.fn()
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch }) }))
vi.mock("@/lib/api", () => ({ API: "/api" }))
const row = { session_id: "thread-12345678", tools: ["codex-desktop"], first_seen: "2026-09-14T12:00:00Z", last_seen: "2026-09-14T13:00:00Z", event_count: 8, warned_count: 3, blocked_count: 1 }
const reply = (data: unknown, status = 200) => ({ ok: status === 200, status, json: async () => data })

describe("AgentActivitySessions", () => {
  beforeEach(() => { authFetch.mockReset(); authFetch.mockResolvedValue(reply({ sessions: [row], has_more: false })) })
  it("links recorded activity to the exact agent and thread without login controls", async () => {
    render(<AgentActivitySessions workspaceId="workspace" identityId="agent" />)
    expect(await screen.findByRole("link", { name: "thread-1" })).toHaveAttribute("href", "/logs/guard?view=events&hook_session_id=thread-12345678&agent_identity_id=agent")
    expect(screen.getByText("codex-desktop")).toBeInTheDocument()
    expect(screen.getByText("8")).toBeInTheDocument()
    expect(screen.queryByText("Revoke")).not.toBeInTheDocument()
    expect(authFetch.mock.calls[0][0]).toBe("/api/workspaces/workspace/agent-identities/agent/activity-sessions?limit=50&offset=0")
  })
  it("does not claim an unattributed agent has no activity", async () => {
    authFetch.mockResolvedValue(reply({ sessions: [], has_more: false }))
    render(<AgentActivitySessions workspaceId="workspace" identityId="agent" />)
    expect(await screen.findByText("No activity sessions attributed to this agent yet.")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Next activity page" })).not.toBeInTheDocument()
  })
  it("supports pagination and refresh", async () => {
    authFetch.mockResolvedValue(reply({ sessions: [row], has_more: true }))
    render(<AgentActivitySessions workspaceId="workspace" identityId="agent" />)
    fireEvent.click(await screen.findByRole("button", { name: "Next activity page" }))
    await waitFor(() => expect(authFetch.mock.calls[1][0]).toContain("offset=50"))
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh activity sessions" })).not.toBeDisabled())
    fireEvent.click(screen.getByRole("button", { name: "Refresh activity sessions" }))
    await waitFor(() => expect(authFetch).toHaveBeenCalledTimes(3))
  })
  it("shows permission failures instead of empty results", async () => {
    authFetch.mockResolvedValue(reply({}, 403))
    render(<AgentActivitySessions workspaceId="workspace" identityId="agent" />)
    expect(await screen.findByRole("alert")).toHaveTextContent("permission")
    expect(screen.queryByText("No activity sessions attributed to this agent yet.")).not.toBeInTheDocument()
  })
})
