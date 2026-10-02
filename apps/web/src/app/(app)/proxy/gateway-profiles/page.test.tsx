import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import Page from "./page"

const state = vi.hoisted(() => ({
  tab: "profiles", role: "admin", workspace: "workspace-a", query: "", fetch: vi.fn(), profiles: vi.fn(), environments: vi.fn(), rates: vi.fn(),
}))
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(`tab=${state.tab}${state.query}`) }))
vi.mock("@/components/AppShell", () => ({ default: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/hooks/useGuardRole", () => ({ useGuardRole: () => ({ role: state.role }) }))
vi.mock("@/lib/WorkspaceContext", () => ({ useWorkspace: () => ({ activeWorkspace: { id: state.workspace } }) }))
vi.mock("@/lib/api/client", () => ({ API: "https://api.example" }))
vi.mock("@/lib/api", () => ({
  environments: { list: state.environments },
  guard: { gatewayProfilesV2: { list: state.profiles }, rateLimits: { list: state.rates } },
}))
vi.mock("@/components/settings/GatewayProfileV2DeleteDialog", () => ({ default: () => null }))
vi.mock("@/components/settings/GatewayProfileV2ImportDialog", () => ({ default: () => null }))
vi.mock("@/components/settings/GatewayProfileV2Editor", () => ({ default: () => null }))
vi.mock("@/components/settings/GatewayProfileV2PublishDialog", () => ({ default: () => null }))
beforeEach(() => {
  vi.clearAllMocks()
  state.tab = "profiles"; state.role = "admin"; state.workspace = "workspace-a"; state.query = ""
  state.profiles.mockResolvedValue([]); state.environments.mockResolvedValue([])
  state.rates.mockResolvedValue([{ id: "default", agent_identity_id: null, rpm: 60, tpm: 100000 }])
})
afterEach(cleanup)

it("keeps profiles as the default view without fetching hidden rate limits", async () => {
  render(<Page />)
  expect(screen.getByRole("tab", { name: "Profiles" })).toHaveAttribute("aria-selected", "true")
  expect(screen.getByRole("tab", { name: "Rate limits" })).toHaveAttribute("href", "/proxy/gateway-profiles?tab=rate_limits")
  await waitFor(() => expect(state.profiles).toHaveBeenCalledWith(state.fetch, "workspace-a"))
  expect(state.rates).not.toHaveBeenCalled()
})

it("loads workspace rate limits under Gateways without loading profile data", async () => {
  state.tab = "rate_limits"
  render(<Page />)
  expect(screen.getByRole("tab", { name: "Rate limits" })).toHaveAttribute("aria-selected", "true")
  await waitFor(() => expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(60))
  expect(state.profiles).not.toHaveBeenCalled()
  expect(state.environments).not.toHaveBeenCalled()
})

it("keeps profile selection in tab navigation URLs", () => {
  state.query = "&select=profile-id"
  render(<Page />)
  expect(screen.getByRole("tab", { name: "Rate limits" })).toHaveAttribute("href", "/proxy/gateway-profiles?tab=rate_limits&select=profile-id")
})

it("does not expose admin limits to viewers through a bookmarked URL", () => {
  state.tab = "rate_limits"; state.role = "viewer"
  render(<Page />)
  expect(screen.queryByRole("tab", { name: "Rate limits" })).toBeNull()
  expect(screen.getByText("Administrator access required.")).toBeInTheDocument()
  expect(state.rates).not.toHaveBeenCalled()
  expect(screen.queryByRole("spinbutton")).toBeNull()
})

it("clears old rate values immediately when the workspace changes", async () => {
  state.tab = "rate_limits"
  const view = render(<Page />)
  await waitFor(() => expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(60))
  state.workspace = "workspace-b"
  state.rates.mockReturnValue(new Promise(() => {}))
  view.rerender(<Page />)
  expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(null)
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled()
})
