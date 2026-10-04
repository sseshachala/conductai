import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import RateLimitsPanel from "./RateLimitsPanel"

const state = vi.hoisted(() => ({ fetch: vi.fn(), get: vi.fn(), set: vi.fn(), list: vi.fn(), upsert: vi.fn() }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/lib/api", () => ({ guard: {
  gatewayProfilesV2: { rateLimits: { get: state.get, set: state.set } },
  rateLimits: { list: state.list, upsert: state.upsert },
} }))
const props = { isAdmin: true, workspaceId: "workspace-a", profileId: "profile-a" }
const agentProps = { isAdmin: true, workspaceId: "workspace-a", agentId: "agent-a" }
const caps = { rpm: 60, tpm: 100000 }
const rpm = () => screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })
const save = () => screen.getByRole("button", { name: "Save limits" })
async function edit() {
  await waitFor(() => expect(screen.getByRole("button", { name: "Edit limits" })).toBeEnabled())
  fireEvent.click(screen.getByRole("button", { name: "Edit limits" }))
}
beforeEach(() => {
  vi.clearAllMocks()
  state.get.mockResolvedValue({ ...caps, agent_limits: [{ agent_identity_id: "old-agent", rpm: 1 }], available_agents: [] })
  state.list.mockResolvedValue([{ agent_identity_id: null, rpm: 999, tpm: 999 }, { agent_identity_id: "agent-a", rpm: 5, tpm: 500 }])
  state.set.mockImplementation((_f, _w, _p, body) => Promise.resolve(body))
  state.upsert.mockImplementation((_f, body) => Promise.resolve(body))
})
afterEach(cleanup)

it("loads only the shared profile cap, read-only, without agent controls", async () => {
  render(<RateLimitsPanel {...props} />)
  await waitFor(() => expect(rpm()).toHaveValue(60))
  expect(state.get).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a")
  expect(rpm()).toHaveAttribute("readonly")
  expect(screen.queryByRole("combobox")).toBeNull()
  expect(screen.getAllByRole("spinbutton")).toHaveLength(2)
  expect(state.list).not.toHaveBeenCalled()
})

it("saves a profile preset without sending agent caps", async () => {
  render(<RateLimitsPanel {...props} />)
  await edit()
  fireEvent.click(screen.getByRole("button", { name: "Smoke test" })); fireEvent.click(save())
  await screen.findByText("Saved")
  expect(state.set).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a", { rpm: 2, tpm: 500 })
  expect(state.upsert).not.toHaveBeenCalled()
  expect(rpm()).toHaveAttribute("readonly")
})

it("saves blank profile fields as uncapped", async () => {
  render(<RateLimitsPanel {...props} />); await edit()
  for (const name of ["Requests / min (RPM)", "Tokens / min (TPM)"]) {
    fireEvent.change(screen.getByRole("spinbutton", { name }), { target: { value: "" } })
  }
  fireEvent.click(save())
  await waitFor(() => expect(state.set).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a", { rpm: null, tpm: null }))
})

it.each(["0", "-1", "1.5", "2147483648"])("rejects invalid cap %s", async value => {
  render(<RateLimitsPanel {...props} />); await edit()
  fireEvent.change(rpm(), { target: { value } })
  expect(save()).toBeDisabled()
  expect(screen.getByRole("alert")).toHaveTextContent("positive whole number")
  expect(state.set).not.toHaveBeenCalled()
})

it("loads and saves the selected agent-wide cap without a profile request", async () => {
  render(<RateLimitsPanel {...agentProps} />); await edit()
  expect(rpm()).toHaveValue(5)
  expect(screen.getByRole("button", { name: "Smoke test" })).toBeEnabled()
  fireEvent.change(rpm(), { target: { value: "10" } }); fireEvent.click(save())
  await screen.findByText("Saved")
  expect(state.upsert).toHaveBeenCalledWith(state.fetch, { agent_identity_id: "agent-a", rpm: 10, tpm: 500 }, "workspace-a")
  expect(state.get).not.toHaveBeenCalled(); expect(state.set).not.toHaveBeenCalled()
})

it.each([
  { label: "Smoke test", rpm: 2, tpm: 500 },
  { label: "Small team", rpm: 60, tpm: 100000 },
  { label: "Larger team", rpm: 300, tpm: 500000 },
])("saves the $label preset only for the selected agent", async preset => {
  render(<RateLimitsPanel {...agentProps} />); await edit()
  fireEvent.click(screen.getByRole("button", { name: preset.label }))
  expect(rpm()).toHaveValue(preset.rpm)
  expect(screen.getByRole("spinbutton", { name: "Tokens / min (TPM)" })).toHaveValue(preset.tpm)
  expect(state.upsert).not.toHaveBeenCalled()
  fireEvent.click(save())
  await screen.findByText("Saved")
  expect(state.upsert).toHaveBeenCalledTimes(1)
  expect(state.upsert).toHaveBeenCalledWith(state.fetch, {
    agent_identity_id: "agent-a", rpm: preset.rpm, tpm: preset.tpm,
  }, "workspace-a")
  expect(state.get).not.toHaveBeenCalled(); expect(state.set).not.toHaveBeenCalled()
  expect(screen.queryByRole("button", { name: preset.label })).toBeNull()
})

it("cancel discards an agent preset and restores the saved cap", async () => {
  render(<RateLimitsPanel {...agentProps} />)
  await waitFor(() => expect(rpm()).toHaveValue(5))
  expect(screen.queryByRole("button", { name: "Smoke test" })).toBeNull()
  await edit()
  fireEvent.click(screen.getByRole("button", { name: "Larger team" }))
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
  expect(rpm()).toHaveValue(5)
  expect(screen.getByRole("spinbutton", { name: "Tokens / min (TPM)" })).toHaveValue(500)
  expect(rpm()).toHaveAttribute("readonly")
  expect(state.upsert).not.toHaveBeenCalled(); expect(state.set).not.toHaveBeenCalled()
})

it("does not apply a legacy workspace default to an uncapped agent", async () => {
  state.list.mockResolvedValue([{ agent_identity_id: null, rpm: 999, tpm: 999 }])
  render(<RateLimitsPanel {...agentProps} />); await edit()
  expect(rpm()).toHaveValue(null)
  fireEvent.click(save())
  await waitFor(() => expect(state.upsert).toHaveBeenCalledWith(state.fetch, { agent_identity_id: "agent-a", rpm: null, tpm: null }, "workspace-a"))
})

it("does not load or expose controls for non-admins", () => {
  render(<RateLimitsPanel {...props} isAdmin={false} />)
  expect(state.get).not.toHaveBeenCalled(); expect(screen.queryByRole("region")).toBeNull()
})

it("does not save after a failed load and supports retry", async () => {
  state.get.mockRejectedValueOnce(new Error("Could not load limits"))
  render(<RateLimitsPanel {...props} />)
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load limits")
  expect(screen.getByRole("button", { name: "Edit limits" })).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Retry loading limits" }))
  await waitFor(() => expect(rpm()).toHaveValue(60))
})

it("reports save failure without claiming success", async () => {
  state.set.mockRejectedValueOnce(new Error("Update denied"))
  render(<RateLimitsPanel {...props} />); await edit(); fireEvent.click(save())
  expect(await screen.findByRole("alert")).toHaveTextContent("Update denied")
  expect(screen.queryByText("Saved")).toBeNull()
})

it("cancel restores the latest saved values", async () => {
  render(<RateLimitsPanel {...props} />); await edit()
  fireEvent.click(screen.getByRole("button", { name: "Smoke test" })); fireEvent.click(save())
  await screen.findByText("Saved"); await edit()
  fireEvent.click(screen.getByRole("button", { name: "Larger team" }))
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
  expect(rpm()).toHaveValue(2); expect(state.set).toHaveBeenCalledTimes(1)
})

it("ignores a late profile load after selection changes", async () => {
  let finish!: (value: typeof caps) => void
  state.get.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  const view = render(<RateLimitsPanel {...props} />)
  state.get.mockResolvedValueOnce({ rpm: 10, tpm: 100 })
  view.rerender(<RateLimitsPanel {...props} profileId="profile-b" />)
  await waitFor(() => expect(rpm()).toHaveValue(10))
  await act(async () => { finish(caps) })
  expect(rpm()).toHaveValue(10)
})

it("ignores a late agent save after the workspace changes", async () => {
  let finish!: (value: typeof caps) => void
  state.upsert.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  const view = render(<RateLimitsPanel {...agentProps} />); await edit(); fireEvent.click(save())
  state.list.mockResolvedValueOnce([{ agent_identity_id: "agent-b", rpm: 20, tpm: 200 }])
  view.rerender(<RateLimitsPanel {...agentProps} workspaceId="workspace-b" agentId="agent-b" />)
  await waitFor(() => expect(rpm()).toHaveValue(20))
  await act(async () => { finish(caps) })
  expect(rpm()).toHaveValue(20); expect(screen.queryByText("Saved")).toBeNull()
})
