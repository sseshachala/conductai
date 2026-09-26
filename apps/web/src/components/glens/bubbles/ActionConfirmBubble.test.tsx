import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { ActionConfirmBubble } from "./ActionConfirmBubble"
import type { LensEvent } from "@/hooks/useLensSessionStream"

vi.mock("@/components/runs/RunDetailPanel", () => ({ default: () => null }))
afterEach(cleanup)
const base = { toolName: "run_workflow", approvalRequestId: "approval-1", summary: "Run workflow", stream: null, onResult: vi.fn() }

it("never offers Confirm while a delayed finalized status is loading", async () => {
  let resolve!: (r: Response) => void
  const fetch = vi.fn(() => new Promise<Response>(r => { resolve = r }))
  render(<ActionConfirmBubble {...base} authFetch={fetch} />)
  expect(screen.getByRole("status")).toHaveTextContent("Checking")
  expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull()
  await act(async () => resolve(new Response(JSON.stringify({ status: "approved" }))))
  expect(await screen.findByText("approved")).toBeVisible()
  expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull()
})

it("fails closed and allows retry when status cannot be read", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response("", { status: 503 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ status: "pending" })))
  render(<ActionConfirmBubble {...base} authFetch={fetch} />)
  fireEvent.click(await screen.findByRole("button", { name: "Retry status check" }))
  expect(await screen.findByRole("button", { name: "Confirm" })).toBeEnabled()
})

it("reconciles after focus and suppresses stale controls during refresh", async () => {
  let resolve!: (r: Response) => void
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ status: "pending" })))
    .mockImplementationOnce(() => new Promise<Response>(r => { resolve = r }))
  render(<ActionConfirmBubble {...base} authFetch={fetch} />)
  await screen.findByRole("button", { name: "Confirm" })
  fireEvent(window, new Event("focus"))
  expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull()
  await act(async () => resolve(new Response(JSON.stringify({ status: "rejected" }))))
  await screen.findByText("rejected")
})

it("dispatches only once for repeated confirm clicks", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ status: "pending" })))
    .mockImplementationOnce(() => new Promise(() => {}))
  render(<ActionConfirmBubble {...base} authFetch={fetch} />)
  const confirm = await screen.findByRole("button", { name: "Confirm" })
  fireEvent.click(confirm)
  fireEvent.click(confirm)
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  expect(fetch.mock.calls[1][1].method).toBe("POST")
})

it("starts a fresh status check when switching to another approval", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ status: "pending" })))
    .mockImplementationOnce(() => new Promise(() => {}))
  const view = render(<ActionConfirmBubble {...base} authFetch={fetch} />)
  await screen.findByRole("button", { name: "Confirm" })
  view.rerender(<ActionConfirmBubble {...base} approvalRequestId="approval-2" authFetch={fetch} />)
  expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull()
  expect(screen.getByRole("status")).toHaveTextContent("Checking")
})

it("refreshes on stream reconnect and ignores a pending snapshot arriving after a decision event", async () => {
  const subscribers: { predicate: (e: LensEvent) => boolean; handler: (e: LensEvent) => void }[] = []
  const stream = { subscribe: (predicate: (e: LensEvent) => boolean, handler: (e: LensEvent) => void) => {
    subscribers.push({ predicate, handler }); return () => {}
  } }
  const emit = (event: LensEvent) => subscribers.forEach(s => { if (s.predicate(event)) s.handler(event) })
  let resolve!: (r: Response) => void
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ status: "pending" })))
    .mockImplementationOnce(() => new Promise<Response>(r => { resolve = r }))
  const onResult = vi.fn()
  render(<ActionConfirmBubble {...base} authFetch={fetch} stream={stream} onResult={onResult} />)
  await screen.findByRole("button", { name: "Confirm" })
  act(() => emit({ id: "", type: "connection.ready", at: "now" }))
  expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull()
  act(() => emit({ id: "event-1", type: "action.cancelled", at: "now", entity: { type: "approval", id: "approval-1" } }))
  await act(async () => resolve(new Response(JSON.stringify({ status: "pending" }))))
  expect(screen.queryByRole("button", { name: "Confirm" })).toBeNull()
  expect(onResult).toHaveBeenCalledWith("Action cancelled.")
})
