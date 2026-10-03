import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import RateLimitsPanel from "./RateLimitsPanel"

const state = vi.hoisted(() => ({ fetch: vi.fn(), get: vi.fn(), set: vi.fn() }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/lib/api", () => ({ guard: { gatewayProfilesV2: { rateLimits: { get: state.get, set: state.set } } } }))
const props = { isAdmin: true, workspaceId: "workspace-a", profileId: "profile-a" }
const caps = { rpm: 60, tpm: 100000, agent_limits: [{ agent_identity_id: "agent-a", rpm: 2, tpm: 500 }],
  available_agents: [{ id: "agent-a", name: "Worker A" }, { id: "agent-b", name: "Worker B" }] }
const saveButton = () => screen.getByRole("button", { name: "Save limits" })
beforeEach(() => { vi.clearAllMocks(); state.get.mockResolvedValue(caps); state.set.mockResolvedValue(caps) })
afterEach(cleanup)

it("loads the selected profile separately from its additional agent caps", async () => {
  render(<RateLimitsPanel {...props} />)
  await waitFor(() => expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(60))
  expect(state.get).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a")
  expect(screen.getByRole("spinbutton", { name: "Worker A Requests / min (RPM)" })).toHaveValue(2)
})

it("saves a profile preset without losing migrated agent caps", async () => {
  render(<RateLimitsPanel {...props} />)
  await waitFor(() => expect(saveButton()).toBeEnabled())
  fireEvent.click(screen.getByRole("button", { name: "Smoke test" })); fireEvent.click(saveButton())
  await waitFor(() => expect(state.set).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a",
    { rpm: 2, tpm: 500, agent_limits: caps.agent_limits }))
  expect(await screen.findByText("Saved")).toBeInTheDocument()
})

it("preserves blank fields as uncapped values", async () => {
  render(<RateLimitsPanel {...props} />)
  await waitFor(() => expect(saveButton()).toBeEnabled())
  for (const name of ["Requests / min (RPM)", "Tokens / min (TPM)"]) {
    fireEvent.change(screen.getByRole("spinbutton", { name }), { target: { value: "" } })
  }
  fireEvent.click(saveButton())
  await waitFor(() => expect(state.set).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a",
    { rpm: null, tpm: null, agent_limits: caps.agent_limits }))
})

it.each(["0", "-1", "1.5", "2147483648"])("rejects invalid cap %s before saving", async value => {
  render(<RateLimitsPanel {...props} />)
  await waitFor(() => expect(saveButton()).toBeEnabled())
  fireEvent.change(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" }), { target: { value } })
  expect(saveButton()).toBeDisabled(); expect(screen.getByRole("alert")).toHaveTextContent("positive whole number")
  expect(state.set).not.toHaveBeenCalled()
})

it("adds and removes named agent caps", async () => {
  render(<RateLimitsPanel {...props} />)
  await waitFor(() => expect(saveButton()).toBeEnabled())
  fireEvent.click(screen.getByRole("button", { name: "Remove Worker A limit" }))
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "agent-b" } })
  fireEvent.click(screen.getByRole("button", { name: "Add agent limit" }))
  fireEvent.change(screen.getByRole("spinbutton", { name: "Worker B Tokens / min (TPM)" }), { target: { value: "50" } })
  fireEvent.click(saveButton())
  await waitFor(() => expect(state.set).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a",
    { rpm: 60, tpm: 100000, agent_limits: [{ agent_identity_id: "agent-b", rpm: null, tpm: 50 }] }))
})

it("does not load or expose controls for non-admins", () => {
  render(<RateLimitsPanel {...props} isAdmin={false} />)
  expect(state.get).not.toHaveBeenCalled(); expect(screen.queryByRole("region")).toBeNull()
})

it("does not overwrite stored caps after a failed load and supports retry", async () => {
  state.get.mockRejectedValueOnce(new Error("Could not load limits"))
  render(<RateLimitsPanel {...props} />)
  expect(await screen.findByText("Could not load limits")).toBeInTheDocument()
  expect(saveButton()).toBeDisabled(); expect(state.set).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Retry loading limits" }))
  await waitFor(() => expect(saveButton()).toBeEnabled())
})

it("reports save failures without claiming success", async () => {
  state.set.mockRejectedValue(new Error("Rate limit update denied"))
  render(<RateLimitsPanel {...props} />)
  await waitFor(() => expect(saveButton()).toBeEnabled()); fireEvent.click(saveButton())
  expect(await screen.findByText("Rate limit update denied")).toBeInTheDocument()
  expect(screen.queryByText("Saved")).toBeNull()
})

it("clears prior caps on profile changes and ignores a late response", async () => {
  let finish: (value: typeof caps) => void = () => {}
  state.get.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  const view = render(<RateLimitsPanel {...props} />)
  state.get.mockResolvedValueOnce({ ...caps, rpm: 10 })
  view.rerender(<RateLimitsPanel {...props} profileId="profile-b" />)
  await waitFor(() => expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(10))
  await act(async () => { finish(caps) })
  expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(10)
})
