import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import RateLimitsPanel from "./RateLimitsPanel"

const state = vi.hoisted(() => ({ fetch: vi.fn(), list: vi.fn(), upsert: vi.fn() }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/lib/api", () => ({ guard: { rateLimits: { list: state.list, upsert: state.upsert } } }))
beforeEach(() => {
  vi.clearAllMocks()
  state.list.mockResolvedValue([
    { id: "default", agent_identity_id: null, rpm: 60, tpm: 100000 },
    { id: "override", agent_identity_id: "agent", rpm: 2, tpm: 500 },
  ])
  state.upsert.mockResolvedValue({})
})
afterEach(cleanup)

it("loads workspace defaults without substituting an agent override", async () => {
  render(<RateLimitsPanel isAdmin />)
  await waitFor(() => expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(60))
  expect(screen.getByRole("spinbutton", { name: "Tokens / min (TPM)" })).toHaveValue(100000)
  expect(screen.getByText(/1 agent override active/)).toBeInTheDocument()
})

it("saves a preset as a workspace default, not a profile or agent override", async () => {
  render(<RateLimitsPanel isAdmin />)
  await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeEnabled())
  fireEvent.click(screen.getByRole("button", { name: /Solo dev \/ smoke test/ }))
  fireEvent.click(screen.getByRole("button", { name: "Save" }))
  await waitFor(() => expect(state.upsert).toHaveBeenCalledWith(state.fetch, { agent_identity_id: null, rpm: 2, tpm: 500 }))
})

it("preserves blank fields as uncapped values", async () => {
  render(<RateLimitsPanel isAdmin />)
  await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeEnabled())
  fireEvent.change(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" }), { target: { value: "" } })
  fireEvent.change(screen.getByRole("spinbutton", { name: "Tokens / min (TPM)" }), { target: { value: "" } })
  fireEvent.click(screen.getByRole("button", { name: "Save" }))
  await waitFor(() => expect(state.upsert).toHaveBeenCalledWith(state.fetch, { agent_identity_id: null, rpm: null, tpm: null }))
})

it("does not load or expose rate-limit controls for non-admins", () => {
  render(<RateLimitsPanel isAdmin={false} />)
  expect(state.list).not.toHaveBeenCalled()
  expect(screen.queryByRole("region", { name: "Gateway workspace rate limits" })).toBeNull()
})

it("reports save failures without claiming success", async () => {
  state.upsert.mockRejectedValue(new Error("Rate limit update denied"))
  render(<RateLimitsPanel isAdmin />)
  await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeEnabled())
  fireEvent.click(screen.getByRole("button", { name: "Save" }))
  expect(await screen.findByText("Rate limit update denied")).toBeInTheDocument()
  expect(screen.queryByText("Saved")).toBeNull()
})
