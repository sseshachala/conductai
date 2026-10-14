import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import Page from "./page"

const state = vi.hoisted(() => ({
  role: "admin", fetch: vi.fn(), get: vi.fn(), publish: vi.fn(), unpublish: vi.fn(),
  remove: vi.fn(), rollback: vi.fn(), push: vi.fn(),
}))
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "p" }),
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: state.push, replace: vi.fn() }),
}))
vi.mock("@/components/AppShell", () => ({ default: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/hooks/useGuardRole", () => ({ useGuardRole: () => ({ role: state.role }) }))
vi.mock("@/lib/WorkspaceContext", () => ({ useWorkspace: () => ({ activeWorkspace: { id: "ws" } }) }))
vi.mock("@/lib/api/client", () => ({ API: "https://api.example" }))
vi.mock("@/lib/api", () => ({
  environments: { list: vi.fn().mockResolvedValue([]) },
  guard: { gatewayProfilesV2: {
    get: state.get, publish: state.publish, unpublish: state.unpublish,
    remove: state.remove, rollback: state.rollback, rateLimits: { get: vi.fn() },
  } },
}))
vi.mock("@/components/settings/GatewayProfileV2Editor", () => ({ default: () => <div>editor</div> }))

const rev1 = { id: "r1", version: 1, published_by: "me", published_at: "2026-10-03T00:00:00Z" }
const rev2 = { id: "r2", version: 2, published_by: "me", published_at: "2026-10-04T00:00:00Z" }
const valid = { name: "Prod", model_alias: "coding", timeout_seconds: 60, max_attempts: 1,
  targets: [{ id: "primary", transport: "native_http", provider: "anthropic", model: "m",
    credential_ref: "vault://bbbbbbbb-0000-4000-8000-000000000001/anthropic" }] }
function make(over: Record<string, unknown>) {
  return { id: "p", workspace_id: "ws", name: "Prod", model_alias: "coding", cond_code: "abc12345",
    active_revision_id: null, status: "draft", has_unpublished_changes: false, revisions: [],
    created_at: "2026-10-02", updated_at: "2026-10-02", working_copy: valid, ...over }
}
const published = (over = {}) => make({ status: "published", active_revision_id: "r2", revisions: [rev1, rev2], ...over })
const unpublished = make({ status: "unpublished", revisions: [rev1] })

beforeEach(() => {
  vi.clearAllMocks()
  state.role = "admin"
  state.get.mockResolvedValue(make({}))
})
afterEach(cleanup)

const publishBtn = () => screen.getByRole("button", { name: "Publish…" })

it("draft: publish enabled, no unpublish, delete enabled", async () => {
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  expect(screen.getAllByText("cond-abc12345-coding").length).toBeGreaterThan(0)
  expect(screen.getByRole("button", { name: "Copy model ID" })).toBeInTheDocument()
  expect(publishBtn()).toBeEnabled()
  expect(screen.queryByRole("button", { name: "Unpublish…" })).toBeNull()
  expect(screen.getByRole("button", { name: "Delete…" })).toBeEnabled()
})

it("published without changes: publish disabled, unpublish available, delete blocked with tooltip", async () => {
  state.get.mockResolvedValue(published())
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  expect(publishBtn()).toBeDisabled()
  expect(publishBtn()).toHaveAttribute("title", "No changes since v2")
  expect(screen.getByRole("button", { name: "Unpublish…" })).toBeEnabled()
  const del = screen.getByRole("button", { name: "Delete…" })
  expect(del).toBeDisabled()
  expect(del).toHaveAttribute("title", "Unpublish before deleting")
})

it("published with changes: publish enabled and targets the next version", async () => {
  state.get.mockResolvedValue(published({ has_unpublished_changes: true }))
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  expect(screen.getByText("Unpublished changes")).toBeInTheDocument()
  expect(publishBtn()).toBeEnabled()
  fireEvent.click(publishBtn())
  expect(await screen.findByRole("heading", { name: "Publish v3" })).toBeInTheDocument()
})

it("unpublished: publish and delete enabled, no unpublish", async () => {
  state.get.mockResolvedValue(unpublished)
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  expect(publishBtn()).toBeEnabled()
  expect(screen.queryByRole("button", { name: "Unpublish…" })).toBeNull()
  expect(screen.getByRole("button", { name: "Delete…" })).toBeEnabled()
})

it("hides lifecycle actions from non-admins", async () => {
  state.role = "viewer"
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  expect(screen.queryByRole("button", { name: "Publish…" })).toBeNull()
  expect(screen.queryByRole("button", { name: "Delete…" })).toBeNull()
})

it("delete dialog says permanently deleted for a draft", async () => {
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  fireEvent.click(screen.getByRole("button", { name: "Delete…" }))
  expect(screen.getByText(/permanently deleted/)).toBeInTheDocument()
  expect(screen.queryByText(/archived/)).toBeNull()
})

it("delete dialog says archived with audit history for an unpublished profile, then returns to the list", async () => {
  state.get.mockResolvedValue(unpublished)
  state.remove.mockResolvedValue(undefined)
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  fireEvent.click(screen.getByRole("button", { name: "Delete…" }))
  expect(screen.getByText(/archived and hidden from the list/)).toBeInTheDocument()
  expect(screen.getByText(/revision history is kept for audit/)).toBeInTheDocument()
  expect(screen.queryByText(/permanently deleted/)).toBeNull()
  fireEvent.change(screen.getByPlaceholderText("Prod"), { target: { value: "Prod" } })
  fireEvent.click(screen.getByRole("button", { name: "Archive profile" }))
  await waitFor(() => expect(state.remove).toHaveBeenCalledWith(state.fetch, "ws", "p"))
  await waitFor(() => expect(state.push).toHaveBeenCalledWith("/proxy/gateway-profiles"))
})

it("unpublish warns, then calls POST /unpublish and reloads", async () => {
  state.get.mockResolvedValue(published())
  state.unpublish.mockResolvedValue(unpublished)
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  fireEvent.click(screen.getByRole("button", { name: "Unpublish…" }))
  expect(screen.getByText(/will\s+start failing immediately/)).toBeInTheDocument()
  expect(state.unpublish).not.toHaveBeenCalled()
  state.get.mockResolvedValue(unpublished)
  fireEvent.click(screen.getByRole("button", { name: "Unpublish" }))
  await waitFor(() => expect(state.unpublish).toHaveBeenCalledWith(state.fetch, "ws", "p"))
  await waitFor(() => expect(screen.getByText("Unpublished", { selector: ".sbadge" })).toBeInTheDocument())
})

it("shows the server's 409 message verbatim on publish", async () => {
  state.publish.mockRejectedValue(new Error('Alias "coding" is already used by published profile "Other"'))
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  fireEvent.click(publishBtn())
  fireEvent.click(screen.getByRole("button", { name: "Publish" }))
  expect(await screen.findByRole("alert")).toHaveTextContent('Alias "coding" is already used by published profile "Other"')
})

it("shows the server's 409 message on unpublish and delete", async () => {
  state.get.mockResolvedValue(published())
  state.unpublish.mockRejectedValue(new Error("Unpublish failed upstream"))
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  fireEvent.click(screen.getByRole("button", { name: "Unpublish…" }))
  fireEvent.click(screen.getByRole("button", { name: "Unpublish" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("Unpublish failed upstream")
})

it("revisions tab lists versions and rolls back after confirmation, surfacing 409s", async () => {
  state.get.mockResolvedValue(published())
  state.rollback.mockRejectedValue(new Error("Alias held by Other"))
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  fireEvent.click(screen.getByRole("tab", { name: "Revisions (2)" }))
  expect(screen.getByText("Active")).toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "Roll back to v2" })).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Roll back to v1" }))
  fireEvent.click(screen.getByRole("button", { name: "Confirm rollback to v1" }))
  await waitFor(() => expect(state.rollback).toHaveBeenCalledWith(state.fetch, "ws", "p", "r1"))
  expect(await screen.findByRole("alert")).toHaveTextContent("Alias held by Other")
})

it("rollback confirm warns that unpublished edits are replaced", async () => {
  state.get.mockResolvedValue(published({ has_unpublished_changes: true }))
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  fireEvent.click(screen.getByRole("tab", { name: "Revisions (2)" }))
  expect(screen.queryByText(/unpublished edits will be replaced/)).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Roll back to v1" }))
  expect(screen.getByRole("status")).toHaveTextContent("Your unpublished edits will be replaced by v1.")
})

it("rollback confirm on an unpublished profile warns that routing resumes", async () => {
  state.get.mockResolvedValue(make({ status: "unpublished", revisions: [rev1, rev2] }))
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  fireEvent.click(screen.getByRole("tab", { name: "Revisions (2)" }))
  fireEvent.click(screen.getByRole("button", { name: "Roll back to v1" }))
  expect(screen.getByRole("status")).toHaveTextContent("Rolling back publishes v1")
})

it("has no duplicate-to-edit or locked messaging, and the editor is reachable on published profiles", async () => {
  state.get.mockResolvedValue(published())
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  expect(screen.queryByText(/duplicate/i)).toBeNull()
  expect(screen.queryByText(/locked/i)).toBeNull()
  fireEvent.click(screen.getByRole("tab", { name: "Edit" }))
  expect(screen.getByText("editor")).toBeInTheDocument()
})

it("shows the server error when the profile is gone", async () => {
  state.get.mockRejectedValue(new Error("Profile not found"))
  render(<Page />)
  expect(await screen.findByRole("alert")).toHaveTextContent("Profile not found")
  expect(screen.getByRole("link", { name: /Back to gateway profiles/ })).toHaveAttribute("href", "/proxy/gateway-profiles")
})

it("shows the rate-limits tab to admins only", async () => {
  const view = render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  expect(screen.getByRole("tab", { name: "Rate limits" })).toBeInTheDocument()
  view.unmount()
  state.role = "viewer"
  render(<Page />)
  await screen.findByRole("heading", { name: "Prod" })
  expect(screen.queryByRole("tab", { name: "Rate limits" })).toBeNull()
})
