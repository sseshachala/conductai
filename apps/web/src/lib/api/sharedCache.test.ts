import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { cachedGet, invalidate, invalidating, bindCacheToUser, clearSharedCache } from "./sharedCache"

describe("sharedCache", () => {
  beforeEach(() => { clearSharedCache(); vi.useFakeTimers() })
  afterEach(() => vi.useRealTimers())

  it("dedupes in-flight and repeat calls within the TTL", async () => {
    const load = vi.fn().mockResolvedValue("a")
    const [x, y] = await Promise.all([cachedGet("k", load), cachedGet("k", load)])
    await cachedGet("k", load)
    expect([x, y]).toEqual(["a", "a"])
    expect(load).toHaveBeenCalledTimes(1)
  })

  it("refetches after the TTL expires", async () => {
    const load = vi.fn().mockResolvedValue("a")
    await cachedGet("k", load, 1000)
    vi.advanceTimersByTime(1001)
    await cachedGet("k", load, 1000)
    expect(load).toHaveBeenCalledTimes(2)
  })

  it("does not cache failures", async () => {
    const load = vi.fn().mockRejectedValueOnce(new Error("x")).mockResolvedValue("ok")
    await expect(cachedGet("k", load)).rejects.toThrow("x")
    await expect(cachedGet("k", load)).resolves.toBe("ok")
  })

  it("invalidates by prefix, and after a write settles", async () => {
    const load = vi.fn().mockResolvedValue(1)
    await cachedGet("/ws/1/projects", load)
    invalidate("/ws/1/")
    await cachedGet("/ws/1/projects", load)
    await invalidating("/ws/1/", Promise.resolve())
    await cachedGet("/ws/1/projects", load)
    expect(load).toHaveBeenCalledTimes(3)
  })

  it("isolates workspaces and users", async () => {
    const load = vi.fn().mockImplementation(async () => Math.random())
    const a = await cachedGet("/ws/1/projects", load)
    const b = await cachedGet("/ws/2/projects", load)
    expect(a).not.toBe(b)
    bindCacheToUser("u0")
    bindCacheToUser("u1")
    await cachedGet("/ws/1/projects", load)
    bindCacheToUser("u2")
    await cachedGet("/ws/1/projects", load)
    expect(load).toHaveBeenCalledTimes(4)
  })
})
