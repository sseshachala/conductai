import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
const state = vi.hoisted(() => ({ fetch: vi.fn(), list: vi.fn(), snapshot: vi.fn() }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/lib/auth/runtime", () => ({ publicApiUrl: () => "https://api.example" }))
vi.mock("@/lib/api", () => ({ API: "https://api.example", guard: { gatewayProfilesV2: { list: state.list, revisionSnapshot: state.snapshot } } }))
import ToolSetupPanel, { setupCommand } from "./ToolSetupPanel"

beforeEach(() => {
  vi.clearAllMocks()
  state.fetch.mockResolvedValue(new Response(JSON.stringify([{
    id: "one", framework: "copilot-cli", device_id: "device-a", installation_id: "install-a",
    freshness: "fresh", hooks_status: "observed", gateway_status: "configured", mcp_configured: true,
    last_seen_at: "2026-10-01T00:00:00Z",
  }])))
  state.list.mockResolvedValue([{ id: "p", cond_code: "abcdefgh", active_revision_id: "rev" }])
  state.snapshot.mockResolvedValue({ model_alias: "coding", accepts: ["openai_responses"] })
})
afterEach(cleanup)

it("uses deployment-specific login commands and refuses unsafe URLs", () => {
  expect(setupCommand("https://api.conductai.ai", "https://app.conductai.ai")).toBe("conduct login")
  expect(setupCommand("https://localhost:3444", "https://localhost:3443")).toContain('--server "https://localhost:3444"')
  expect(setupCommand("/api/backend", "https://console.example")).toBeNull()
  expect(setupCommand('https://api.example/$(oops)', "https://console.example")).toBeNull()
})

it("shows independent surfaces and compatible published model IDs", async () => {
  render(<ToolSetupPanel workspaceId="ws" isAdmin />)
  expect(await screen.findByText("device-a / install-" )).toBeInTheDocument()
  expect(screen.getByText("Activity observed")).toBeInTheDocument()
  expect(screen.getAllByText("cond-abcdefgh-coding")).toHaveLength(2)
  expect(screen.getAllByText("No compatible profiles published")).toHaveLength(1)
})

it("does not fetch credential-management profiles for a non-admin", async () => {
  render(<ToolSetupPanel workspaceId="ws" isAdmin={false} />)
  await waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(1))
  expect(state.list).not.toHaveBeenCalled()
})

it("does not fetch when the tab is hidden", () => {
  render(<ToolSetupPanel workspaceId="ws" isAdmin enabled={false} />)
  expect(state.fetch).not.toHaveBeenCalled()
})

it("clears previous workspace evidence and handles denied inventory", async () => {
  const view = render(<ToolSetupPanel workspaceId="a" isAdmin={false} />)
  await screen.findByText("Activity observed")
  state.fetch.mockResolvedValue(new Response("{}", { status: 403 }))
  view.rerender(<ToolSetupPanel workspaceId="b" isAdmin={false} />)
  expect(await screen.findByRole("alert")).toHaveTextContent("access denied")
  expect(screen.queryByText("Activity observed")).toBeNull()
})
