import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { GuardRoleClerkProvider, useGuardRoleContext } from "../GuardRoleContext"

const mocks = vi.hoisted(() => ({
  auth: { getToken: vi.fn(), isLoaded: true, isSignedIn: true },
  user: { user: { primaryEmailAddress: { emailAddress: "dev@example.com" } } as unknown },
  workspace: { activeWorkspace: { id: "ws-1" } as unknown },
}))

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => mocks.auth,
  useUser: () => mocks.user,
}))

vi.mock("@/lib/WorkspaceContext", () => ({
  useWorkspace: () => mocks.workspace,
}))

function ContextProbe() {
  const { role, permissions, loading } = useGuardRoleContext()
  return (
    <div>
      <span data-testid="role">{role ?? "null"}</span>
      <span data-testid="loading">{loading ? "yes" : "no"}</span>
      <span data-testid="edit-policies">{permissions.canEditPolicies ? "yes" : "no"}</span>
      <span data-testid="edit-settings">{permissions.canEditSettings ? "yes" : "no"}</span>
      <span data-testid="view-all-activity">{permissions.canViewAllActivity ? "yes" : "no"}</span>
      <span data-testid="view-own-spend">{permissions.canViewOwnSpend ? "yes" : "no"}</span>
    </div>
  )
}

function mountShell() {
  return render(
    <GuardRoleClerkProvider>
      <ContextProbe />
    </GuardRoleClerkProvider>,
  )
}

describe("GuardRoleClerkProvider fetch flow", () => {
  const originalFetch = global.fetch
  const originalApiUrl = process.env.NEXT_PUBLIC_API_URL

  beforeEach(() => {
    mocks.auth.getToken = vi.fn().mockResolvedValue("clerk-token-abc")
    mocks.auth.isLoaded = true
    mocks.auth.isSignedIn = true
    mocks.user.user = { primaryEmailAddress: { emailAddress: "dev@example.com" } }
    mocks.workspace.activeWorkspace = { id: "ws-1" }
    process.env.NEXT_PUBLIC_API_URL = "https://api.test"
  })

  afterEach(() => {
    global.fetch = originalFetch
    process.env.NEXT_PUBLIC_API_URL = originalApiUrl
    vi.restoreAllMocks()
  })

  it("calls /me/permissions with workspace_id and email query params + Bearer token", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ role: "developer", permissions: [] }),
    })
    global.fetch = fetchSpy as unknown as typeof fetch

    mountShell()
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1))

    const [urlArg, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(urlArg).toContain("https://api.test/me/permissions?")
    expect(urlArg).toContain("workspace_id=ws-1")
    expect(urlArg).toContain("email=dev%40example.com")
    const headers = init.headers as Record<string, string>
    expect(headers.Authorization).toBe("Bearer clerk-token-abc")
  })

  it("parses role and permissions from API response", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        role: "security",
        permissions: ["guard.policies.edit", "guard.activity.view_all"],
      }),
    }) as unknown as typeof fetch

    mountShell()

    await waitFor(() => expect(screen.getByTestId("role").textContent).toBe("security"))
    expect(screen.getByTestId("edit-policies").textContent).toBe("yes")
    expect(screen.getByTestId("view-all-activity").textContent).toBe("yes")
    expect(screen.getByTestId("edit-settings").textContent).toBe("no")
  })

  it("granting only view_own_spend leaves canEditPolicies false", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        role: "developer",
        permissions: ["guard.spend.view_own"],
      }),
    }) as unknown as typeof fetch

    mountShell()

    await waitFor(() => expect(screen.getByTestId("role").textContent).toBe("developer"))
    expect(screen.getByTestId("view-own-spend").textContent).toBe("yes")
    expect(screen.getByTestId("edit-policies").textContent).toBe("no")
    expect(screen.getByTestId("view-all-activity").textContent).toBe("no")
  })

  it("empty permissions array falls back to VIEWER_PERMISSIONS", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ role: "viewer", permissions: [] }),
    }) as unknown as typeof fetch

    mountShell()

    await waitFor(() => expect(screen.getByTestId("role").textContent).toBe("viewer"))
    expect(screen.getByTestId("edit-policies").textContent).toBe("no")
    expect(screen.getByTestId("view-own-spend").textContent).toBe("no")
    expect(screen.getByTestId("view-all-activity").textContent).toBe("no")
  })

  it("non-OK response leaves role null and degrades to VIEWER_PERMISSIONS", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    }) as unknown as typeof fetch

    mountShell()

    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("no"))
    expect(screen.getByTestId("role").textContent).toBe("null")
    expect(screen.getByTestId("edit-policies").textContent).toBe("no")
  })

  it("fetch throw is swallowed and provider degrades to viewer", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("network down")) as unknown as typeof fetch

    mountShell()

    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("no"))
    expect(screen.getByTestId("role").textContent).toBe("null")
  })

  it("skips fetch when not signed in", async () => {
    mocks.auth.isSignedIn = false
    const fetchSpy = vi.fn()
    global.fetch = fetchSpy as unknown as typeof fetch

    mountShell()

    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("no"))
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(screen.getByTestId("role").textContent).toBe("null")
  })

  it("skips fetch when no active workspace", async () => {
    mocks.workspace.activeWorkspace = null
    const fetchSpy = vi.fn()
    global.fetch = fetchSpy as unknown as typeof fetch

    mountShell()

    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("no"))
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("skips fetch when getToken returns null", async () => {
    mocks.auth.getToken = vi.fn().mockResolvedValue(null)
    const fetchSpy = vi.fn()
    global.fetch = fetchSpy as unknown as typeof fetch

    mountShell()

    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("no"))
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("omits email query param when user has no primaryEmailAddress", async () => {
    mocks.user.user = { primaryEmailAddress: null }
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ role: "viewer", permissions: [] }),
    })
    global.fetch = fetchSpy as unknown as typeof fetch

    mountShell()
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1))

    const [urlArg] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(urlArg).toContain("workspace_id=ws-1")
    expect(urlArg).not.toContain("email=")
  })

  it("full admin permission set from API grants every flag", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        role: "admin",
        permissions: [
          "guard.policies.edit",
          "guard.settings.edit",
          "guard.spend.budgets.edit",
          "guard.activity.view_all",
          "guard.spend.view_all",
          "guard.spend.view_own",
          "guard.activity.export",
        ],
      }),
    }) as unknown as typeof fetch

    mountShell()

    await waitFor(() => expect(screen.getByTestId("role").textContent).toBe("admin"))
    expect(screen.getByTestId("edit-policies").textContent).toBe("yes")
    expect(screen.getByTestId("edit-settings").textContent).toBe("yes")
    expect(screen.getByTestId("view-all-activity").textContent).toBe("yes")
    expect(screen.getByTestId("view-own-spend").textContent).toBe("yes")
  })
})
