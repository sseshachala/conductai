import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { LensChat } from "./LensChat"
import { LensPanel } from "./LensPanel"
import { LENS_ENTRY_EVENT, openLensEntry, lensEntryHref, type LensEntry } from "@/lib/lens-entry"

const state = vi.hoisted(() => ({ fetch: vi.fn(), push: vi.fn(), workspace: "11111111-1111-4111-8111-111111111111" }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch, workspaceId: state.workspace }) }))
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: state.push }) }))
vi.mock("./LensSettings", () => ({ LensSettings: () => null }))
vi.mock("@/components/glens/bubbles/AnswerBubble", () => ({ AnswerBubble: ({ text }: { text: string }) => <div>{text}</div> }))
vi.mock("@/components/glens/bubbles/ActionConfirmBubble", () => ({ ActionConfirmBubble: () => null }))

const entry: LensEntry = { kind: "event", workspace_id: state.workspace, resource_id: "22222222-2222-4222-8222-222222222222" }
const done = () => new Response('data: {"type":"done","answer":"Recorded evidence","session_id":"session-1"}\n\n')
beforeEach(() => { vi.resetAllMocks(); state.workspace = entry.workspace_id })
afterEach(cleanup)

it("only accepts an in-page handoff when a mounted listener handles it", () => {
  expect(openLensEntry(entry)).toBe(false)
  const accept = (e: Event) => { expect((e as CustomEvent).detail).toEqual(entry); e.preventDefault() }
  window.addEventListener(LENS_ENTRY_EVENT, accept)
  try { expect(openLensEntry(entry)).toBe(true) }
  finally { window.removeEventListener(LENS_ENTRY_EVENT, accept) }
})

it("sends selected record and page, then uses the returned session for follow-ups", async () => {
  state.fetch.mockImplementation(done)
  render(<LensChat initialEntry={entry} initialSessionId="old-session" pathname="/logs/guard" />)
  await waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(1))
  expect(JSON.parse(state.fetch.mock.calls[0][1].body)).toMatchObject({ entry_context: entry, page_context: "/logs/guard" })
  expect(JSON.parse(state.fetch.mock.calls[0][1].body)).not.toHaveProperty("session_id")
  await waitFor(() => expect(screen.getByRole("textbox")).not.toBeDisabled())
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Why?" } })
  fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" })
  await waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(2))
  expect(JSON.parse(state.fetch.mock.calls[1][1].body)).toEqual({ message: "Why?", session_id: "session-1", page_context: "/logs/guard" })
})

it.each(["http", "truncated", "malformed", "network"])("retains record context for retry after %s failure", async (failure) => {
  if (failure === "network") state.fetch.mockRejectedValueOnce(new TypeError("Failed to fetch"))
  else state.fetch.mockResolvedValueOnce(failure === "http" ? new Response("", { status: 503 }) : new Response(failure === "malformed" ? "data: invalid\n\n" : 'data: {"type":"token","text":"partial"}\n\n'))
  state.fetch.mockImplementation(done)
  render(<LensChat initialEntry={entry} />)
  fireEvent.click(await screen.findByRole("button", { name: "Retry" }))
  await waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(2))
  expect(JSON.parse(state.fetch.mock.calls[1][1].body).entry_context).toEqual(entry)
  await waitFor(() => expect(screen.queryByRole("button", { name: "Retry" })).toBeNull())
})

it("does not send a record into another workspace", async () => {
  state.workspace = "33333333-3333-4333-8333-333333333333"
  render(<LensChat initialEntry={entry} />)
  await screen.findByText("Switch to the originating workspace and reopen Ask Lens.")
  expect(state.fetch).not.toHaveBeenCalled()
})

it("expands pending context without dropping the record", () => {
  state.fetch.mockImplementation(() => new Promise(() => {}))
  render(<LensPanel open initialQuery={null} initialEntry={entry} pathname="/logs/guard" onClose={vi.fn()} />)
  fireEvent.click(screen.getByRole("button", { name: "Expand to full Lens" }))
  expect(state.push).toHaveBeenCalledWith(lensEntryHref(entry))
})

it("expands a completed investigation to its saved session", async () => {
  state.fetch.mockImplementation(done)
  render(<LensPanel open initialQuery={null} initialEntry={entry} pathname="/logs/guard" onClose={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole("textbox")).not.toBeDisabled())
  fireEvent.click(screen.getByRole("button", { name: "Expand to full Lens" }))
  expect(state.push).toHaveBeenCalledWith("/lens/session-1")
})
