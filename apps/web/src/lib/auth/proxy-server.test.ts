// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
vi.mock("server-only", () => ({}))
import { exchangeProxyIdentity, requireSameOrigin } from "./proxy-server"
import { POST as session } from "@/app/api/auth/session/route"
import { GET as getBackend, POST as postBackend } from "@/app/api/backend/[...path]/route"

beforeEach(() => {
  vi.stubEnv("AUTH_MODE", "proxy")
  vi.stubEnv("APP_URL", "https://console.example.test")
  vi.stubEnv("API_URL", "http://internal-api:8000")
  vi.stubEnv("CONSOLE_PROXY_SECRET", "unit-fixture-not-a-secret-" + "x".repeat(32))
})
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe("proxy console server boundary", () => {
  it("rejects cross-origin and absent-origin mutations", () => {
    for (const origin of ["", "https://attacker.test", "https://sub.console.example.test"]) {
      expect(() => requireSameOrigin(new Request("https://console.example.test/api/auth/session", {
        headers: { origin }, method: "POST",
      }))).toThrow()
    }
  })
  it("does not accept identity headers without signed bearer evidence", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch)
    await expect(exchangeProxyIdentity(new Headers({ "x-auth-user": "admin" }))).rejects.toThrow()
    expect(fetch).not.toHaveBeenCalled()
  })
  it("exchanges identity only at the configured API, without browser cookies", async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json({ token: "short-session" }))
    vi.stubGlobal("fetch", fetch)
    await exchangeProxyIdentity(new Headers({ authorization: "Bearer identity-evidence", cookie: "private-cookie" }))
    expect(fetch.mock.calls[0][0]).toBe("http://internal-api:8000/auth/console/session")
    const options = fetch.mock.calls[0][1]
    expect(options.redirect).toBe("error")
    expect(options.headers.Cookie).toBeUndefined()
    expect(options.body).toBe(JSON.stringify({ identity_token: "identity-evidence" }))
  })
  it("returns no cacheable session", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ token: "short-session" })))
    const response = await session(new Request("https://console.example.test/api/auth/session", {
      method: "POST", headers: { origin: "https://console.example.test", authorization: "Bearer signed" },
    }))
    expect(response.status).toBe(200)
    expect(response.headers.get("cache-control")).toBe("no-store")
  })
  it("forwards only a minted session and allowlisted headers", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(Response.json({ token: "minted" }))
      .mockResolvedValueOnce(Response.json({ result: true }, { headers: { "Set-Cookie": "upstream=secret" } }))
    vi.stubGlobal("fetch", fetch)
    const result = await getBackend(new Request("https://console.example.test/api/backend/projects?workspace_id=one", {
      headers: { authorization: "Bearer identity", cookie: "secret", "x-auth-user": "admin", "x-workspace-id": "one" },
    }), { params: Promise.resolve({ path: ["projects"] }) })
    expect(result.status).toBe(200)
    expect(result.headers.get("set-cookie")).toBeNull()
    const forwarded = fetch.mock.calls[1][1].headers as Headers
    expect(forwarded.get("authorization")).toBe("Bearer minted")
    expect(forwarded.get("cookie")).toBeNull()
    expect(forwarded.get("x-auth-user")).toBeNull()
  })
  it("blocks path escapes, exchange access, and cross-origin mutations before fetching", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch)
    for (const path of [["..", "secret"], ["https://attacker.test"], ["auth", "console", "session"]]) {
      const response = await getBackend(new Request("https://console.example.test/api/backend/x"), { params: Promise.resolve({ path }) })
      expect(response.status).toBeGreaterThanOrEqual(400)
    }
    expect((await postBackend(new Request("https://console.example.test/api/backend/projects", { method: "POST" }),
      { params: Promise.resolve({ path: ["projects"] }) })).status).toBe(403)
    expect(fetch).not.toHaveBeenCalled()
  })
})
