// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest"
import { NextRequest, NextResponse } from "next/server"
import { createRequire } from "node:module"

const { clerkHandler } = vi.hoisted(() => ({ clerkHandler: vi.fn() }))
vi.mock("@clerk/nextjs/server", () => ({
  clerkMiddleware: () => clerkHandler,
  createRouteMatcher: () => () => false,
}))

import middleware from "./middleware"
const nextConfig = createRequire(import.meta.url)("../next.config.js")

afterEach(() => {
  vi.unstubAllEnvs()
  vi.clearAllMocks()
})

describe("anonymous bootstrap routes", () => {
  it("serves verification without authentication and without referrer leakage", async () => {
    vi.stubEnv("NODE_ENV", "production")
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "")
    const response = await middleware(new NextRequest("https://app.conductai.ai/onboard/verify?ct=test"), {})
    expect(response.status).toBe(200)
    expect(response.headers.get("Referrer-Policy")).toBe("no-referrer")
    expect(response.headers.get("Cache-Control")).toBe("no-store")
    expect(clerkHandler).not.toHaveBeenCalled()
  })
  it("keeps the installer rewrite and shell content type", async () => {
    expect(await nextConfig.rewrites()).toContainEqual({ source: "/install", destination: "/install.sh" })
    for (const source of ["/install", "/install.sh"]) {
      expect(await nextConfig.headers()).toContainEqual({
        source, headers: [{ key: "Content-Type", value: "text/x-shellscript; charset=utf-8" }],
      })
    }
  })

  it("redirects obsolete documentation links", async () => {
    const redirects = await nextConfig.redirects()
    expect(redirects).toContainEqual({ source: "/docs/self-hosted", destination: "/deployment", permanent: true })
    expect(redirects).toContainEqual({ source: "/docs/templates", destination: "/registry", permanent: true })
  })
  it.each(["/install", "/install.sh", "/llms.txt"])("serves %s without Clerk", async (path) => {
    vi.stubEnv("NODE_ENV", "production")
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "")
    const response = await middleware(new NextRequest(`https://conductai.ai${path}`), {})
    expect(response.status).toBe(200)
    expect(response.headers.get("location")).toBeNull()
    expect(response.headers.get("x-content-type-options")).toBe("nosniff")
    expect(clerkHandler).not.toHaveBeenCalled()
  })

  it.each(["/dashboard", "/install/private", "/llms.txt/private"])("does not exempt %s", async (path) => {
    vi.stubEnv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "test-key")
    clerkHandler.mockResolvedValue(NextResponse.redirect("https://app.conductai.ai/sign-in"))
    const response = await middleware(new NextRequest(`https://app.conductai.ai${path}`), {})
    expect(clerkHandler).toHaveBeenCalledOnce()
    expect(response.status).toBe(307)
  })
})
