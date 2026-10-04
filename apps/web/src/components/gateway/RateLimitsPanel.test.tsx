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
const editButton = () => screen.getByRole("button", { name: "Edit limits" })
async function editLimits() {
  await waitFor(() => expect(editButton()).toBeEnabled())
  fireEvent.click(editButton())
}
beforeEach(() => { vi.clearAllMocks(); state.get.mockResolvedValue(caps); state.set.mockResolvedValue(caps) })
afterEach(cleanup)

it("loads the selected profile separately from its additional agent caps", async () => {
  render(<RateLimitsPanel {...props} />)
  await waitFor(() => expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(60))
  expect(state.get).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a")
  expect(screen.getByRole("spinbutton", { name: "Worker A Requests / min (RPM)" })).toHaveValue(2)
  expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveAttribute("readonly")
  expect(screen.queryByRole("button", { name: "Save limits" })).toBeNull()
  expect(screen.queryByRole("button", { name: "Remove Worker A limit" })).toBeNull()
})

it("saves a profile preset without losing migrated agent caps", async () => {
  render(<RateLimitsPanel {...props} />)
  await editLimits()
  fireEvent.click(screen.getByRole("button", { name: "Smoke test" })); fireEvent.click(saveButton())
  await waitFor(() => expect(state.set).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a",
    { rpm: 2, tpm: 500, agent_limits: caps.agent_limits }))
  expect(await screen.findByText("Saved")).toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "Save limits" })).toBeNull()
  expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveAttribute("readonly")
})

it("preserves blank fields as uncapped values", async () => {
  render(<RateLimitsPanel {...props} />)
  await editLimits()
  for (const name of ["Requests / min (RPM)", "Tokens / min (TPM)"]) {
    fireEvent.change(screen.getByRole("spinbutton", { name }), { target: { value: "" } })
  }
  fireEvent.click(saveButton())
  await waitFor(() => expect(state.set).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a",
    { rpm: null, tpm: null, agent_limits: caps.agent_limits }))
})

it.each(["0", "-1", "1.5", "2147483648"])("rejects invalid cap %s before saving", async value => {
  render(<RateLimitsPanel {...props} />)
  await editLimits()
  fireEvent.change(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" }), { target: { value } })
  expect(saveButton()).toBeDisabled(); expect(screen.getByRole("alert")).toHaveTextContent("positive whole number")
  expect(state.set).not.toHaveBeenCalled()
})

it("adds and removes named agent caps", async () => {
  render(<RateLimitsPanel {...props} />)
  await editLimits()
  fireEvent.click(screen.getByRole("button", { name: "Remove Worker A limit" }))
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "agent-b" } })
  fireEvent.click(screen.getByRole("button", { name: "Add agent limit" }))
  fireEvent.change(screen.getByRole("spinbutton", { name: "Worker B Tokens / min (TPM)" }), { target: { value: "50" } })
  fireEvent.click(saveButton())
  await waitFor(() => expect(state.set).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a",
    { rpm: 60, tpm: 100000, agent_limits: [{ agent_identity_id: "agent-b", rpm: null, tpm: 50 }] }))
})

it("distinguishes repeated names without merging identities and saves the selected identity", async () => {
  const first = { id: "abc12345-1111", name: "alice@example.test (auto)" }
  const second = { id: "abc12345-2222", name: first.name }
  state.get.mockResolvedValue({ ...caps, agent_limits: [], available_agents: [first, second, first] })
  render(<RateLimitsPanel {...props} />)
  await editLimits()
  const picker = await screen.findByRole("combobox", { name: "Agent identity" })
  expect(screen.getAllByRole("option")).toHaveLength(3)
  expect(screen.getByRole("option", { name: "alice@example.test (auto) (abc12345-1)" })).toHaveValue(first.id)
  expect(screen.getByRole("option", { name: "alice@example.test (auto) (abc12345-2)" })).toHaveValue(second.id)
  fireEvent.change(picker, { target: { value: second.id } })
  fireEvent.click(screen.getByRole("button", { name: "Add agent limit" }))
  expect(screen.getByRole("spinbutton", { name: "alice@example.test (auto) (abc12345-2) Requests / min (RPM)" })).toBeInTheDocument()
  fireEvent.click(saveButton())
  await waitFor(() => expect(state.set).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a", {
    rpm: 60, tpm: 100000, agent_limits: [{ agent_identity_id: second.id, rpm: null, tpm: null }],
  }))
})

it.each(["user_member (auto)", "oidc_member (auto)", "Auto-provisioned agent"])(
  "gives legacy or unresolved auto names a readable, distinct label: %s", async name => {
    state.get.mockResolvedValue({ ...caps, agent_limits: [], available_agents: [
      { id: "11111111-one", name }, { id: "22222222-two", name },
    ] })
    render(<RateLimitsPanel {...props} />)
    await editLimits()
    expect(await screen.findByRole("option", { name: "Auto-provisioned agent (11111111)" })).toHaveValue("11111111-one")
    expect(screen.getByRole("option", { name: "Auto-provisioned agent (22222222)" })).toHaveValue("22222222-two")
    expect(screen.queryByText(name === "Auto-provisioned agent" ? "unresolved" : name)).toBeNull()
  },
)

it("does not load or expose controls for non-admins", () => {
  render(<RateLimitsPanel {...props} isAdmin={false} />)
  expect(state.get).not.toHaveBeenCalled(); expect(screen.queryByRole("region")).toBeNull()
})

it("does not overwrite stored caps after a failed load and supports retry", async () => {
  state.get.mockRejectedValueOnce(new Error("Could not load limits"))
  render(<RateLimitsPanel {...props} />)
  expect(await screen.findByText("Could not load limits")).toBeInTheDocument()
  expect(editButton()).toBeDisabled(); expect(state.set).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Retry loading limits" }))
  await waitFor(() => expect(editButton()).toBeEnabled())
})

it("reports save failures without claiming success", async () => {
  state.set.mockRejectedValue(new Error("Rate limit update denied"))
  render(<RateLimitsPanel {...props} />)
  await editLimits(); fireEvent.click(saveButton())
  expect(await screen.findByText("Rate limit update denied")).toBeInTheDocument()
  expect(screen.queryByText("Saved")).toBeNull()
})

it("cancel restores stored profile and agent caps without a request", async () => {
  render(<RateLimitsPanel {...props} />)
  await editLimits()
  fireEvent.click(screen.getByRole("button", { name: "Smoke test" }))
  fireEvent.click(screen.getByRole("button", { name: "Remove Worker A limit" }))
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
  expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(60)
  expect(screen.getByRole("spinbutton", { name: "Worker A Requests / min (RPM)" })).toHaveValue(2)
  expect(screen.queryByRole("button", { name: "Save limits" })).toBeNull()
  expect(state.set).not.toHaveBeenCalled()
})

it("cancel uses the latest saved caps rather than the initial load", async () => {
  render(<RateLimitsPanel {...props} />)
  await editLimits()
  fireEvent.click(screen.getByRole("button", { name: "Smoke test" })); fireEvent.click(saveButton())
  await screen.findByText("Saved")
  await editLimits()
  fireEvent.click(screen.getByRole("button", { name: "Larger team" }))
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
  expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(2)
  expect(state.set).toHaveBeenCalledTimes(1)
})

it("agent-only editing preserves the shared cap and sends only agent limits", async () => {
  state.set.mockResolvedValue({ ...caps, rpm: 120, tpm: 250000 })
  render(<RateLimitsPanel {...props} agentOnly />)
  await editLimits()
  expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveAttribute("readonly")
  expect(screen.getByRole("spinbutton", { name: "Worker A Requests / min (RPM)" })).not.toHaveAttribute("readonly")
  expect(screen.queryByRole("button", { name: "Smoke test" })).toBeNull()
  fireEvent.change(screen.getByRole("spinbutton", { name: "Worker A Requests / min (RPM)" }), { target: { value: "10" } })
  fireEvent.click(saveButton())
  await waitFor(() => expect(state.set).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-a", {
    agent_limits: [{ agent_identity_id: "agent-a", rpm: 10, tpm: 500 }],
  }))
  await screen.findByText("Saved")
  expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(120)
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
