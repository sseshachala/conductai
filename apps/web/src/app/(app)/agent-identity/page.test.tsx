import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import Page from "./page"

const state = vi.hoisted(() => ({ query: "", replace: vi.fn(), rates: vi.fn(), fetch: vi.fn() }))
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: state.replace }),
  useSearchParams: () => new URLSearchParams(state.query) }))
vi.mock("@/lib/auth/runtime", () => ({ authEnabled: () => false }))
vi.mock("@/components/AppShell", () => ({ default: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/lib/WorkspaceContext", () => ({ useWorkspace: () => ({ activeWorkspace: { id: "workspace-a" } }) }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/lib/api", () => ({ API: "https://api.example.test" }))
vi.mock("@/components/federation/FederationPanel", () => ({ FederationPanel: () => null }))
vi.mock("@/components/gateway/AgentRateLimitsPanel", () => ({ default: (props: unknown) => {
  state.rates(props); return <div data-testid="agent-rate-limits" />
} }))
beforeEach(() => {
  vi.clearAllMocks(); state.query = ""
  state.fetch.mockImplementation(async (url: string) => ({ ok: true, json: async () =>
    url.endsWith("/my-role") ? { role: "admin" } : url.includes("/config/installed") ? {} : [] }))
})
afterEach(cleanup)

it("places Rate limits immediately below Lens sessions and loads only on selection", async () => {
  render(<Page />)
  const names = screen.getAllByRole("tab").map(tab => tab.textContent)
  expect(names[names.indexOf("Lens sessions") + 1]).toBe("Rate limits")
  expect(state.rates).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("tab", { name: "Rate limits" }))
  expect(screen.getByRole("tabpanel", { name: "Rate limits" })).toContainElement(screen.getByTestId("agent-rate-limits"))
  expect(state.replace).toHaveBeenCalledWith("/agent-identity?tab=rate_limits", { scroll: false })
  await waitFor(() => expect(state.rates).toHaveBeenLastCalledWith({ workspaceId: "workspace-a", isAdmin: true }))
})

it("opens the Rate limits deep link", async () => {
  state.query = "tab=rate_limits"
  render(<Page />)
  expect(screen.getByRole("tab", { name: "Rate limits" })).toHaveAttribute("aria-selected", "true")
  await waitFor(() => expect(state.rates).toHaveBeenLastCalledWith({ workspaceId: "workspace-a", isAdmin: true }))
})
