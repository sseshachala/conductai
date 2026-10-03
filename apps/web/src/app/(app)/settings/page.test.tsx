import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import SettingsPage from "./page"

const state = vi.hoisted(() => ({ tab: "credentials", replace: vi.fn(), fetch: vi.fn() }))
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: state.replace }), useSearchParams: () => new URLSearchParams({ tab: state.tab }),
}))
vi.mock("@/lib/auth/runtime", () => ({ authEnabled: () => false }))
vi.mock("@/lib/auth/client", () => ({ useAuth: () => ({ userId: null, getToken: null }) }))
vi.mock("@/lib/WorkspaceContext", () => ({ useWorkspace: () => ({ activeWorkspace: null }) }))
vi.mock("@/lib/api", () => ({ API: "https://api.example" }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/components/settings/EnvironmentsManager", () => ({ default: () => <div>Vault settings</div> }))
vi.mock("@/components/settings/MembersManager", () => ({ default: () => null }))
vi.mock("@/components/settings/PreferencesPanel", () => ({ default: () => null }))
vi.mock("@/components/settings/LLMPrimitivesPanel", () => ({ default: () => null }))
vi.mock("@/components/settings/ToolSetupPanel", () => ({ default: () => null }))
vi.mock("@/components/SettingsShell", () => ({ SettingsShell: ({ tabs, panels }: {
  tabs: { key: string; label: string }[]; panels: Record<string, ReactNode>;
}) => <><nav>{tabs.map(tab => <button key={tab.key} role="tab">{tab.label}</button>)}</nav>{panels[state.tab]}</> }))

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal("localStorage", { getItem: vi.fn(() => "1"), setItem: vi.fn() })
  state.tab = "credentials"
  state.fetch.mockResolvedValue(new Response("[]"))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it("keeps configuration tabs but removes canvas toolbar preferences from global settings", () => {
  render(<SettingsPage />)
  expect(screen.getByRole("tab", { name: "Tool Setup" })).toBeInTheDocument()
  expect(screen.getByRole("tab", { name: "Vault" })).toBeInTheDocument()
  expect(screen.queryByRole("tab", { name: "Canvas" })).toBeNull()
  expect(screen.queryByRole("tab", { name: "Rate limits" })).toBeNull()
  expect(screen.queryByText("Canvas toolbar")).toBeNull()
})

it("redirects old canvas settings bookmarks to workflows", async () => {
  state.tab = "canvas"
  render(<SettingsPage />)
  await waitFor(() => expect(state.replace).toHaveBeenCalledWith("/workflows"))
})

it("preserves the existing proxy settings redirect", async () => {
  state.tab = "proxy"
  render(<SettingsPage />)
  await waitFor(() => expect(state.replace).toHaveBeenCalledWith("/theguard/connections/proxy"))
})

it("redirects old rate-limit settings bookmarks to Gateways", async () => {
  state.tab = "rate_limits"
  render(<SettingsPage />)
  await waitFor(() => expect(state.replace).toHaveBeenCalledWith("/proxy/gateway-profiles"))
})
