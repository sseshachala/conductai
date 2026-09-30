import { afterEach, describe, expect, it, vi } from "vitest"
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"

vi.mock("@clerk/nextjs", () => ({
  useAuth: vi.fn(() => { throw new Error("Clerk must not run in proxy mode") }),
  useUser: vi.fn(() => { throw new Error("Clerk must not run in proxy mode") }),
  useSession: vi.fn(() => { throw new Error("Clerk must not run in proxy mode") }),
  useClerk: vi.fn(() => { throw new Error("Clerk must not run in proxy mode") }),
}))
import * as clerk from "@clerk/nextjs"
import { ClerkAuthBridge, ConsoleProvider, useAuth, useUser, useSession, useClerk } from "./client"

afterEach(() => { cleanup(); vi.unstubAllEnvs(); vi.unstubAllGlobals() })

describe("console client adapter", () => {
  it("preserves Clerk hook results through the Clerk provider bridge", () => {
    const auth = { isLoaded: true, isSignedIn: true, userId: "clerk_alice" }
    const user = { isLoaded: true, user: { id: "clerk_alice" } }
    const session = { isLoaded: true, session: { id: "session_alice" } }
    const sdk = { signOut: vi.fn() }
    vi.mocked(clerk.useAuth).mockReturnValueOnce(auth as ReturnType<typeof clerk.useAuth>)
    vi.mocked(clerk.useUser).mockReturnValueOnce(user as ReturnType<typeof clerk.useUser>)
    vi.mocked(clerk.useSession).mockReturnValueOnce(session as ReturnType<typeof clerk.useSession>)
    vi.mocked(clerk.useClerk).mockReturnValueOnce(sdk as unknown as ReturnType<typeof clerk.useClerk>)
    const fetcher = vi.fn()
    vi.stubGlobal("fetch", fetcher)
    const { result } = renderHook(() => ({ auth: useAuth(), user: useUser(), session: useSession(), sdk: useClerk() }),
      { wrapper: ClerkAuthBridge })
    expect(result.current).toEqual({ auth, user, session, sdk })
    expect(fetcher).not.toHaveBeenCalled()
  })

  it("loads and refreshes a proxy session without invoking Clerk", async () => {
    vi.stubEnv("AUTH_MODE", "proxy")
    const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ token: "conduct-session", expires_at: Date.now() / 1000 + 60,
      user: { id: "oidc_alice", name: "Alice" } })).mockResolvedValueOnce(new Response(null, { status: 401 }))
    vi.stubGlobal("fetch", fetcher)
    const { result } = renderHook(() => ({ auth: useAuth(), profile: useUser() }), { wrapper: ConsoleProvider })
    await waitFor(() => expect(result.current.auth.isSignedIn).toBe(true))
    expect(result.current.auth.userId).toBe("oidc_alice")
    expect(result.current.profile.user?.fullName).toBe("Alice")
    expect(await result.current.auth.getToken()).toBe("conduct-session")
    expect(fetcher).toHaveBeenCalledTimes(1)
    await act(async () => { expect(await result.current.auth.getToken({ skipCache: true })).toBeNull() })
    expect(result.current.auth.isSignedIn).toBe(false)
  })

  it("does not treat a failed session exchange as authenticated", async () => {
    vi.stubEnv("AUTH_MODE", "proxy")
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 403 })))
    const { result } = renderHook(() => useAuth(), { wrapper: ConsoleProvider })
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    expect(result.current.isSignedIn).toBe(false)
    expect(result.current.userId).toBeNull()
  })

  it("supports only explicitly selected local development without a provider", () => {
    vi.stubEnv("AUTH_MODE", "development")
    vi.stubEnv("ENVIRONMENT", "local")
    const { result } = renderHook(() => useAuth())
    expect(result.current.isLoaded).toBe(true)
    expect(result.current.userId).toBe("dev")
  })
})
