import { fireEvent, render, screen, cleanup, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
const state = vi.hoisted(() => ({ fetch: vi.fn(), workspace: "workspace-a" }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch, workspaceId: state.workspace }) }))
import { LensSettings } from "./LensSettings"

beforeEach(() => {
  vi.clearAllMocks()
  state.workspace = "workspace-a"
  state.fetch.mockResolvedValue(new Response(JSON.stringify({ environment_id: null, can_edit: true, vaults: [{ id: "prod", name: "Production" }] })))
})
afterEach(cleanup)

it("loads names only and saves the chosen Vault ID", async () => {
  render(<LensSettings />)
  fireEvent.click(screen.getByRole("button", { name: "Lens settings" }))
  const select = await screen.findByLabelText("Workspace Vault")
  fireEvent.change(select, { target: { value: "prod" } })
  state.fetch.mockResolvedValue(new Response("{}"))
  fireEvent.click(screen.getByRole("button", { name: "Save" }))
  await waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(2))
  expect(JSON.parse(state.fetch.mock.calls[1][1].body)).toEqual({ environment_id: "prod" })
})

it("does not offer writes to a read-only member", async () => {
  state.fetch.mockResolvedValue(new Response(JSON.stringify({ environment_id: "prod", can_edit: false, vaults: [{ id: "prod", name: "Production" }] })))
  render(<LensSettings />)
  fireEvent.click(screen.getByRole("button", { name: "Lens settings" }))
  expect(await screen.findByLabelText("Workspace Vault")).toBeDisabled()
  expect(screen.queryByRole("button", { name: "Save" })).toBeNull()
})

it("closes old workspace settings when workspace changes", async () => {
  const view = render(<LensSettings />)
  fireEvent.click(screen.getByRole("button", { name: "Lens settings" }))
  await screen.findByLabelText("Workspace Vault")
  state.workspace = "workspace-b"
  view.rerender(<LensSettings />)
  expect(screen.queryByLabelText("Workspace Vault")).toBeNull()
})
