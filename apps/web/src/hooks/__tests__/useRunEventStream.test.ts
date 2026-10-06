import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook, act } from "@testing-library/react"
import { useRunEventStream } from "../useRunEventStream"

class FakeEventSource {
  static instances: FakeEventSource[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  constructor(public url: string) { FakeEventSource.instances.push(this) }
  close() { this.closed = true }
  emit(data: unknown) { this.onmessage?.({ data: typeof data === "string" ? data : JSON.stringify(data) }) }
}

const flush = () => act(async () => { await Promise.resolve() })

describe("useRunEventStream", () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal("EventSource", FakeEventSource)
    vi.useFakeTimers()
  })
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

  it("reconnects after a drop and de-duplicates the server's replay", async () => {
    const onEvent = vi.fn()
    const onDone = vi.fn()
    renderHook(() => useRunEventStream({ workflowId: "w", runId: "r", workspaceId: "ws", onEvent, onDone }))
    await flush()
    const first = FakeEventSource.instances[0]
    expect(first.url).toContain("/workflows/w/runs/r/stream?workspace_id=ws")
    first.emit({ id: "1", kind: "block_started", block_id: "a", payload: {} })
    first.onerror?.()
    expect(first.closed).toBe(true)

    await act(async () => { vi.advanceTimersByTime(1000) })
    await flush()
    const second = FakeEventSource.instances[1]
    second.emit({ id: "1", kind: "block_started", block_id: "a", payload: {} }) // replayed
    second.emit({ id: "2", kind: "block_completed", block_id: "a", payload: {} })
    second.emit("not json")
    second.emit("[DONE]")

    expect(onEvent.mock.calls.map(c => c[0].id)).toEqual(["1", "2"])
    expect(onDone).toHaveBeenCalledOnce()
    second.onerror?.() // close after [DONE] must not reconnect
    await act(async () => { vi.advanceTimersByTime(60_000) })
    expect(FakeEventSource.instances).toHaveLength(2)
  })

  it("does not connect when disabled", async () => {
    renderHook(() => useRunEventStream({ workflowId: "w", runId: "r", workspaceId: null, enabled: false, onEvent: vi.fn() }))
    await flush()
    expect(FakeEventSource.instances).toHaveLength(0)
  })
})
