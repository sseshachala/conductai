import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import Page from "./page"

const state = vi.hoisted(() => ({
  role: "admin", workspace: "workspace-a", query: "", fetch: vi.fn(), profiles: vi.fn(),
  push: vi.fn(), replace: vi.fn(),
}))
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(state.query),
  useRouter: () => ({ push: state.push, replace: state.replace }),
}))
vi.mock("@/components/AppShell", () => ({ default: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/hooks/useGuardRole", () => ({ useGuardRole: () => ({ role: state.role }) }))
vi.mock("@/lib/WorkspaceContext", () => ({ useWorkspace: () => ({ activeWorkspace: { id: state.workspace } }) }))
vi.mock("@/lib/api", () => ({ guard: { gatewayProfilesV2: { list: state.profiles } } }))
vi.mock("@/components/settings/GatewayProfileV2ImportDialog", () => ({ default: () => null }))

function make(over: Record<string, unknown>) {
  return { id: "p", workspace_id: "workspace-a", name: "P", model_alias: "alias", cond_code: "abc12345",
    active_revision_id: null, status: "draft", has_unpublished_changes: false, revisions: [],
    created_at: "2026-10-02", updated_at: "2026-10-02", working_copy: {}, ...over }
}
const rev = { id: "r1", version: 1, published_by: "me", published_at: "2026-10-03T00:00:00Z" }
const rows = [
  make({ id: "d", name: "Drafty", model_alias: "drafty" }),
  make({ id: "pub", name: "Live", model_alias: "live", status: "published", active_revision_id: "r1",
    has_unpublished_changes: true, revisions: [rev] }),
  make({ id: "unp", name: "Parked", model_alias: "parked", status: "unpublished", revisions: [rev] }),
]

beforeEach(() => {
  vi.clearAllMocks()
  state.role = "admin"; state.workspace = "workspace-a"; state.query = ""
  state.profiles.mockResolvedValue(rows)
})
afterEach(cleanup)

it("lists profiles with status, model ID and unpublished-changes indicator", async () => {
  render(<Page />)
  const live = (await screen.findByRole("link", { name: "Live" })).closest("tr") as HTMLElement
  expect(within(live).getByText("Published")).toBeInTheDocument()
  expect(within(live).getByText("Unpublished changes")).toBeInTheDocument()
  expect(within(live).getByText("cond-abc12345-live")).toBeInTheDocument()
  expect(within(screen.getByRole("link", { name: "Drafty" }).closest("tr") as HTMLElement).getByText("Draft")).toBeInTheDocument()
  expect(within(screen.getByRole("link", { name: "Parked" }).closest("tr") as HTMLElement).getByText("Unpublished")).toBeInTheDocument()
  expect(screen.getByRole("link", { name: "New profile" })).toHaveAttribute("href", "/proxy/gateway-profiles/new")
})

it("filters by status", async () => {
  render(<Page />)
  await screen.findByRole("link", { name: "Live" })
  fireEvent.click(screen.getByRole("button", { name: "Unpublished" }))
  expect(screen.getByRole("link", { name: "Parked" })).toBeInTheDocument()
  expect(screen.queryByRole("link", { name: "Live" })).toBeNull()
  expect(screen.queryByRole("link", { name: "Drafty" })).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Draft" }))
  expect(screen.getByRole("link", { name: "Drafty" })).toBeInTheDocument()
  expect(screen.queryByRole("link", { name: "Parked" })).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "All" }))
  expect(screen.getAllByRole("link", { name: /Live|Parked|Drafty/ })).toHaveLength(3)
})

it("navigates to the detail page on row click", async () => {
  render(<Page />)
  const row = (await screen.findByRole("link", { name: "Parked" })).closest("tr") as HTMLElement
  fireEvent.click(within(row).getByText("cond-abc12345-parked"))
  expect(state.push).toHaveBeenCalledWith("/proxy/gateway-profiles/unp")
})

it("redirects old ?select= deep links to the detail page, keeping the rate-limits tab", async () => {
  state.query = "tab=rate_limits&select=pub"
  render(<Page />)
  await waitFor(() => expect(state.replace).toHaveBeenCalledWith("/proxy/gateway-profiles/pub?tab=rate-limits"))
  expect(state.profiles).not.toHaveBeenCalled()
})

it("hides create actions from non-admins", async () => {
  state.role = "viewer"
  render(<Page />)
  await screen.findByRole("link", { name: "Live" })
  expect(screen.queryByRole("link", { name: "New profile" })).toBeNull()
  expect(screen.queryByRole("button", { name: "Import JSON" })).toBeNull()
})
