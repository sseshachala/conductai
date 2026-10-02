import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
const state = vi.hoisted(() => ({ fetch: vi.fn(), list: vi.fn(), snapshot: vi.fn() }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/lib/auth/runtime", () => ({ publicApiUrl: () => "https://api.example" }))
vi.mock("@/lib/api", () => ({ API: "https://api.example", guard: { gatewayProfilesV2: { list: state.list, revisionSnapshot: state.snapshot } } }))
import ToolSetupPanel, { setupCommand } from "./ToolSetupPanel"

beforeEach(() => {
  vi.clearAllMocks()
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

it("keeps configuration and published models in Settings without loading discovery", async () => {
  render(<ToolSetupPanel workspaceId="ws" isAdmin />)
  expect(await screen.findAllByText("cond-abcdefgh-coding")).toHaveLength(2)
  expect(screen.getAllByText("No compatible profiles published")).toHaveLength(1)
  expect(screen.getByText("conduct guard sync")).toBeInTheDocument()
  expect(screen.getByRole("link", { name: "Agent Discovery" })).toHaveAttribute("href", "/theguard/discovery")
  expect(screen.queryByRole("table")).toBeNull()
  expect(screen.queryByText("MCP inventory")).toBeNull()
  expect(state.fetch).not.toHaveBeenCalled()
})

it("does not fetch credential-management profiles for a non-admin", async () => {
  render(<ToolSetupPanel workspaceId="ws" isAdmin={false} />)
  expect(state.list).not.toHaveBeenCalled()
  expect(state.fetch).not.toHaveBeenCalled()
})

it("does not fetch when the tab is hidden", () => {
  render(<ToolSetupPanel workspaceId="ws" isAdmin enabled={false} />)
  expect(state.fetch).not.toHaveBeenCalled()
  expect(state.list).not.toHaveBeenCalled()
})

it("clears previous workspace models when loading the next workspace fails", async () => {
  const view = render(<ToolSetupPanel workspaceId="a" isAdmin />)
  await screen.findAllByText("cond-abcdefgh-coding")
  state.list.mockRejectedValueOnce(new Error("denied"))
  view.rerender(<ToolSetupPanel workspaceId="b" isAdmin />)
  expect(await screen.findByRole("alert")).toHaveTextContent("Published models unavailable")
  await waitFor(() => expect(screen.queryByText("cond-abcdefgh-coding")).toBeNull())
})
