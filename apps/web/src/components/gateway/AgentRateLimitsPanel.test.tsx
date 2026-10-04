import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import AgentRateLimitsPanel from "./AgentRateLimitsPanel"

const state = vi.hoisted(() => ({ fetch: vi.fn(), agents: vi.fn(), list: vi.fn(), upsert: vi.fn() }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/lib/api", () => ({ guard: { rateLimits: { agents: state.agents, list: state.list, upsert: state.upsert } } }))
const props = { workspaceId: "workspace-a", isAdmin: true }
const agents = [{ id: "identity-1111", name: "Alice (auto)" }, { id: "identity-2222", name: "Alice (auto)" }]
beforeEach(() => {
  vi.clearAllMocks(); state.agents.mockResolvedValue(agents)
  state.list.mockResolvedValue([{ agent_identity_id: agents[0].id, rpm: 5, tpm: 500 }])
  state.upsert.mockImplementation((_f, body) => Promise.resolve(body))
})
afterEach(cleanup)

it("requires explicit agent selection and has no Gateway profile picker", async () => {
  render(<AgentRateLimitsPanel {...props} />)
  const picker = await screen.findByRole("combobox", { name: "Agent identity" })
  expect(picker).toHaveValue("")
  expect(screen.queryByRole("combobox", { name: "Gateway profile" })).toBeNull()
  expect(state.list).not.toHaveBeenCalled()
  for (const row of agents) expect(screen.getByRole("option", { name: row.name + " (" + row.id + ")" })).toHaveValue(row.id)
  fireEvent.change(picker, { target: { value: agents[0].id } })
  await waitFor(() => expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(5))
  expect(screen.getByText(agents[0].id, { selector: "code" })).toBeInTheDocument()
  expect(screen.queryByText("Profile limit")).toBeNull()
})

it("switching agents discards unsaved edits and saves only the selected ID", async () => {
  render(<AgentRateLimitsPanel {...props} />)
  const picker = await screen.findByRole("combobox", { name: "Agent identity" })
  fireEvent.change(picker, { target: { value: agents[0].id } })
  await waitFor(() => expect(screen.getByRole("button", { name: "Edit limits" })).toBeEnabled())
  fireEvent.click(screen.getByRole("button", { name: "Edit limits" }))
  fireEvent.change(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" }), { target: { value: "10" } })
  fireEvent.change(picker, { target: { value: agents[1].id } })
  await waitFor(() => expect(screen.getByRole("button", { name: "Edit limits" })).toBeEnabled())
  expect(screen.queryByRole("button", { name: "Save limits" })).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Edit limits" }))
  fireEvent.click(screen.getByRole("button", { name: "Save limits" }))
  await waitFor(() => expect(state.upsert).toHaveBeenCalledWith(state.fetch, {
    agent_identity_id: agents[1].id, rpm: null, tpm: null,
  }, "workspace-a"))
})

it("uses compact UUID labels while retaining the full selected identity", async () => {
  const rows = [
    { id: "3f27cc94-eb7a-462f-bc51-cbdbb775354a", name: "Claude.ai (admin@example.test)" },
    { id: "3f27cc94-eb7a-462f-bc51-cbdbb775abcd", name: "Claude.ai (admin@example.test)" },
  ]
  state.agents.mockResolvedValue(rows)
  render(<AgentRateLimitsPanel {...props} />)
  const picker = await screen.findByRole("combobox", { name: "Agent identity" })
  expect(screen.getByRole("option", { name: "Claude.ai (admin@example.test) (3f27cc94...354a)" })).toHaveValue(rows[0].id)
  expect(screen.getByRole("option", { name: "Claude.ai (admin@example.test) (3f27cc94...abcd)" })).toHaveValue(rows[1].id)
  fireEvent.change(picker, { target: { value: rows[0].id } })
  expect(picker).toHaveAttribute("title", `${rows[0].name} (${rows[0].id})`)
  expect(screen.getByText(rows[0].id, { selector: "code" })).toBeInTheDocument()
  await waitFor(() => expect(state.list).toHaveBeenCalledWith(state.fetch, "workspace-a"))
})

it("does not fetch protected data for a non-admin", () => {
  render(<AgentRateLimitsPanel {...props} isAdmin={false} />)
  expect(state.agents).not.toHaveBeenCalled()
  expect(screen.getByText("Rate limits are managed by workspace admins.")).toBeInTheDocument()
})

it("links an empty state to Agent identities", async () => {
  state.agents.mockResolvedValue([])
  render(<AgentRateLimitsPanel {...props} />)
  expect(await screen.findByText("No agent identities.")).toBeInTheDocument()
  expect(screen.getByRole("link", { name: "Agent identities" })).toHaveAttribute("href", "/agent-identity?tab=identities")
  expect(state.list).not.toHaveBeenCalled()
})

it("supports retry after an agent list failure", async () => {
  state.agents.mockRejectedValueOnce(new Error("Could not load agents"))
  render(<AgentRateLimitsPanel {...props} />)
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load agents")
  fireEvent.click(screen.getByRole("button", { name: "Retry loading agents" }))
  expect(await screen.findByRole("combobox", { name: "Agent identity" })).toHaveValue("")
})

it("ignores old agents after a workspace switch", async () => {
  let finish!: (value: typeof agents) => void
  state.agents.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  const view = render(<AgentRateLimitsPanel {...props} />)
  state.agents.mockResolvedValueOnce([{ id: "new-identity", name: "Bob" }])
  view.rerender(<AgentRateLimitsPanel {...props} workspaceId="workspace-b" />)
  await screen.findByRole("option", { name: "Bob (new-identity)" })
  await act(async () => { finish(agents) })
  expect(screen.queryByRole("option", { name: /Alice/ })).toBeNull()
  expect(state.agents).toHaveBeenLastCalledWith(state.fetch, "workspace-b")
})
