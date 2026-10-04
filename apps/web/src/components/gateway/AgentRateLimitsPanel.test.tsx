import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import AgentRateLimitsPanel from "./AgentRateLimitsPanel"

const state = vi.hoisted(() => ({ fetch: vi.fn(), list: vi.fn(), get: vi.fn(), set: vi.fn() }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/lib/api", () => ({ guard: { gatewayProfilesV2: {
  list: state.list, rateLimits: { get: state.get, set: state.set },
} } }))

const props = { workspaceId: "workspace-a", isAdmin: true }
const profiles = [
  { id: "profile-a", name: "Production", cond_code: "abcdefgh", model_alias: "coding" },
  { id: "profile-b", name: "Production", cond_code: "ijklmnop", model_alias: "coding" },
]
const caps = { rpm: 60, tpm: 100000, agent_limits: [], available_agents: [{ id: "agent-a", name: "Worker" }] }
beforeEach(() => {
  vi.clearAllMocks(); state.list.mockResolvedValue(profiles); state.get.mockResolvedValue(caps)
  state.set.mockResolvedValue(caps)
})
afterEach(cleanup)

it("selects a profile and reuses the read-only rate-limit editor", async () => {
  render(<AgentRateLimitsPanel {...props} />)
  expect(await screen.findByRole("combobox", { name: "Gateway profile" })).toHaveValue("profile-a")
  await waitFor(() => expect(state.get).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a"))
  expect(screen.getByRole("option", { name: "Production - cond-abcdefgh-coding" })).toHaveValue("profile-a")
  expect(screen.getByRole("option", { name: "Production - cond-ijklmnop-coding" })).toHaveValue("profile-b")
  expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveAttribute("readonly")
})

it("switches profiles and discards unsaved agent edits", async () => {
  render(<AgentRateLimitsPanel {...props} />)
  await waitFor(() => expect(screen.getByRole("button", { name: "Edit limits" })).toBeEnabled())
  fireEvent.click(screen.getByRole("button", { name: "Edit limits" }))
  fireEvent.change(screen.getByRole("combobox", { name: "Agent identity" }), { target: { value: "agent-a" } })
  fireEvent.click(screen.getByRole("button", { name: "Add agent limit" }))
  fireEvent.change(screen.getByRole("combobox", { name: "Gateway profile" }), { target: { value: "profile-b" } })
  await waitFor(() => expect(state.get).toHaveBeenLastCalledWith(state.fetch, "workspace-a", "profile-b"))
  expect(screen.queryByRole("button", { name: "Save limits" })).toBeNull()
  expect(screen.queryByRole("spinbutton", { name: "Worker Requests / min (RPM)" })).toBeNull()
  expect(state.set).not.toHaveBeenCalled()
})

it("does not fetch protected data for a non-admin", () => {
  render(<AgentRateLimitsPanel {...props} isAdmin={false} />)
  expect(state.list).not.toHaveBeenCalled(); expect(state.get).not.toHaveBeenCalled()
  expect(screen.getByText("Rate limits are managed by workspace admins.")).toBeInTheDocument()
})

it("shows an empty state linking to Gateway profiles", async () => {
  state.list.mockResolvedValue([])
  render(<AgentRateLimitsPanel {...props} />)
  expect(await screen.findByText("No Gateway profiles.")).toBeInTheDocument()
  expect(screen.getByRole("link", { name: "Gateway profiles" })).toHaveAttribute("href", "/proxy/gateway-profiles")
  expect(state.get).not.toHaveBeenCalled()
})

it("reports a profile load failure and supports retry", async () => {
  state.list.mockRejectedValueOnce(new Error("Could not load profiles"))
  render(<AgentRateLimitsPanel {...props} />)
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load profiles")
  fireEvent.click(screen.getByRole("button", { name: "Retry loading profiles" }))
  expect(await screen.findByRole("combobox", { name: "Gateway profile" })).toHaveValue("profile-a")
})

it("does not expose old profile caps after a workspace switch or late response", async () => {
  let finish: (value: typeof profiles) => void = () => {}
  state.list.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  const view = render(<AgentRateLimitsPanel {...props} />)
  state.list.mockResolvedValueOnce([{ ...profiles[1], id: "workspace-b-profile" }])
  view.rerender(<AgentRateLimitsPanel {...props} workspaceId="workspace-b" />)
  await waitFor(() => expect(state.get).toHaveBeenCalledWith(state.fetch, "workspace-b", "workspace-b-profile"))
  await act(async () => { finish(profiles) })
  expect(screen.getByRole("combobox", { name: "Gateway profile" })).toHaveValue("workspace-b-profile")
  expect(state.get).not.toHaveBeenCalledWith(state.fetch, "workspace-b", "profile-a")
})
