import { cleanup, render } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

const state = vi.hoisted(() => ({
  workspace: "workspace-a", teamId: null as string | null, loading: true,
  tokenGuardrails: vi.fn(), getToken: vi.fn(), fetch: vi.fn(), list: vi.fn(),
}))
vi.mock("@/lib/auth/client", () => ({
  useAuth: () => ({ getToken: state.getToken }), useUser: () => ({ user: null }),
}))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/hooks/useGuardTeam", () => ({ useGuardTeam: () => ({ teamId: state.teamId, loading: state.loading }) }))
vi.mock("@/hooks/useGuardRole", () => ({ useGuardRole: () => ({ permissions: { canViewAllActivity: true }, loading: false }) }))
vi.mock("@/hooks/useGuardSavings", () => ({ useGuardSavings: () => ({ savings: null, loading: false }) }))
vi.mock("@/hooks/useTokenGuardrails", () => ({ useTokenGuardrails: state.tokenGuardrails }))
vi.mock("@/lib/WorkspaceContext", () => ({ useWorkspace: () => ({ activeWorkspace: { id: state.workspace } }) }))
vi.mock("@/components/AppShell", () => ({ default: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/components/guard/GuardShell", () => ({ GuardShell: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/components/guard/overview/OverviewHero", () => ({ OverviewHero: () => null }))
vi.mock("@/features/guard/spend/SpendGlance", () => ({ SpendGlance: () => null }))
vi.mock("@/lib/api", () => ({ guard: {
  events: { list: state.list }, policies: { list: state.list },
  developerTools: { list: state.list }, spend: { get: state.list, sessions: state.list },
} }))

import GuardPage from "./page"

beforeEach(() => {
  vi.clearAllMocks()
  state.workspace = "workspace-a"; state.teamId = null; state.loading = true
  state.tokenGuardrails.mockReturnValue({ guardrails: null })
  state.getToken.mockResolvedValue(null)
  state.fetch.mockResolvedValue(new Response("{}"))
  state.list.mockResolvedValue([])
  vi.stubGlobal("EventSource", class { close() {} })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it("waits for Guard configuration before reading token guardrails", () => {
  const view = render(<GuardPage />)
  expect(state.tokenGuardrails).toHaveBeenLastCalledWith(null)
  state.teamId = state.workspace; state.loading = false
  view.rerender(<GuardPage />)
  expect(state.tokenGuardrails).toHaveBeenLastCalledWith("workspace-a")
})

it("does not read the previous team's guardrails while switching workspaces", () => {
  state.teamId = "workspace-a"; state.loading = false; state.workspace = "workspace-b"
  render(<GuardPage />)
  expect(state.tokenGuardrails).toHaveBeenLastCalledWith(null)
})
