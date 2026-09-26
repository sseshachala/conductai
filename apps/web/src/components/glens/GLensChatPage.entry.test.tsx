import React, { StrictMode } from "react"
import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({
  workspace: "00000000-0000-0000-0000-000000000001" as string | null,
  params: new URLSearchParams(), fetch: vi.fn(), replace: vi.fn(),
}))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch, workspaceId: state.workspace }) }))
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: state.replace }), usePathname: () => "/lens", useSearchParams: () => state.params }))
vi.mock("@/hooks/useLensSessionStream", () => ({ useLensSessionStream: () => null }))
vi.mock("./Sidebar", () => ({ Sidebar: () => null }))
vi.mock("./ChatInput", () => ({ ChatInput: () => null }))
vi.mock("./bubbles/AnswerBubble", () => ({ AnswerBubble: ({ text }: { text: string }) => <p>{text}</p> }))
vi.mock("./MessageFooter", () => ({ MessageFooter: () => null }))

import { GLensChatPage } from "./GLensChatPage"

const workspace = "00000000-0000-0000-0000-000000000001"
const event = "00000000-0000-0000-0000-000000000002"
const calls = () => state.fetch.mock.calls.filter(([url]) => String(url).includes("/chat/stream"))

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal("localStorage", { getItem: vi.fn(() => null), setItem: vi.fn(), removeItem: vi.fn(), clear: vi.fn() })
  state.workspace = workspace
  state.params = new URLSearchParams({ context: "event", workspace_id: workspace, resource_id: event })
  state.fetch.mockImplementation(async (url: string) => url.includes("/chat/stream")
    ? new Response('data: {"type":"done","session_id":"new-session","answer":"Verified evidence"}\n\n')
    : new Response(JSON.stringify(url.includes("/sessions") ? [] : {})))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it("sends one typed context request under Strict Mode without copied payloads", async () => {
  state.params.set("q", "Ignore this injected URL prompt")
  render(<StrictMode><GLensChatPage /></StrictMode>)
  await screen.findByText("Verified evidence")
  expect(calls()).toHaveLength(1)
  const body = JSON.parse(calls()[0][1].body)
  expect(body.entry_context).toEqual({ kind: "event", workspace_id: workspace, resource_id: event })
  expect(body.session_id).toBeUndefined()
  expect(body.message).not.toContain("injected")
  expect(state.replace).toHaveBeenCalledWith("/lens/new-session")
})

it("waits for workspace selection before auto-send", async () => {
  state.workspace = null
  const view = render(<GLensChatPage />)
  await waitFor(() => expect(calls()).toHaveLength(0))
  state.workspace = workspace
  view.rerender(<GLensChatPage />)
  await screen.findByText("Verified evidence")
  expect(calls()).toHaveLength(1)
})

it("does not reinterpret a foreign-workspace link in the current workspace", async () => {
  state.params.set("workspace_id", "00000000-0000-0000-0000-000000000003")
  render(<GLensChatPage />)
  expect(await screen.findByRole("alert")).toHaveTextContent("originating workspace")
  expect(calls()).toHaveLength(0)
})

it("rejects malformed context without falling back to URL q", async () => {
  state.params.set("resource_id", "not-an-id")
  state.params.set("q", "run something")
  render(<GLensChatPage />)
  expect(await screen.findByRole("alert")).toHaveTextContent("invalid")
  expect(calls()).toHaveLength(0)
})

it("shows denied access instead of retrying with broader scope", async () => {
  state.fetch.mockImplementation(async (url: string) => url.includes("/chat/stream")
    ? new Response("{}", { status: 403 }) : new Response("[]"))
  render(<GLensChatPage />)
  await screen.findByText("You do not have permission to investigate this activity.")
  expect(calls()).toHaveLength(1)
  expect(state.replace).not.toHaveBeenCalled()
})

it("aborts an in-flight investigation when switching workspaces", async () => {
  state.fetch.mockImplementation(async (url: string) => url.includes("/chat/stream")
    ? new Promise<Response>(() => {}) : new Response("[]"))
  const view = render(<GLensChatPage />)
  await waitFor(() => expect(calls()).toHaveLength(1))
  const signal = calls()[0][1].signal as AbortSignal
  state.workspace = "00000000-0000-0000-0000-000000000003"
  view.rerender(<GLensChatPage />)
  expect(await screen.findByRole("alert")).toHaveTextContent("originating workspace")
  expect(signal.aborted).toBe(true)
  expect(calls()).toHaveLength(1)
})

it.each(["run", "trial"])("hands off %s context through the same chat endpoint", async (kind) => {
  state.params.set("context", kind)
  if (kind === "trial") state.params.delete("resource_id")
  else state.params.set("block_id", "deploy")
  render(<GLensChatPage />)
  await screen.findByText("Verified evidence")
  const body = JSON.parse(calls()[0][1].body)
  expect(body.entry_context.kind).toBe(kind)
  expect(body.entry_context.workspace_id).toBe(workspace)
  expect(body.entry_context.block_id).toBe(kind === "run" ? "deploy" : undefined)
})

it("does not present truncated evidence as a completed answer or discard retry context", async () => {
  state.fetch.mockImplementation(async (url: string) => url.includes("/chat/stream")
    ? new Response('data: {"type":"token","text":"Partial evidence"}\n\n') : new Response("[]"))
  render(<GLensChatPage />)
  await screen.findByText(/connection ended before the answer completed/)
  expect(screen.queryByText("Partial evidence")).not.toBeInTheDocument()
  expect(state.replace).not.toHaveBeenCalled()
  expect(calls()).toHaveLength(1)
})

it("reassembles split stream chunks before linking the completed session", async () => {
  const encoded = new TextEncoder().encode('data: {"type":"done","session_id":"saved","answer":"Complete evidence"}\n\n')
  state.fetch.mockImplementation(async (url: string) => url.includes("/chat/stream")
    ? new Response(new ReadableStream({ start(controller) {
      for (const byte of encoded) controller.enqueue(new Uint8Array([byte]))
      controller.close()
    } })) : new Response("[]"))
  render(<GLensChatPage />)
  await screen.findByText("Complete evidence")
  expect(state.replace).toHaveBeenCalledWith("/lens/saved")
})

it("reloads a saved conversation without dispatching a new investigation", async () => {
  state.params = new URLSearchParams()
  state.fetch.mockImplementation(async (url: string) => url.endsWith("/sessions/saved")
    ? new Response(JSON.stringify({ messages: [{ role: "assistant", content: JSON.stringify({ answer: "Reauthorized evidence" }) }] }))
    : new Response("[]"))
  render(<GLensChatPage initialSessionId="saved" />)
  await screen.findByText("Reauthorized evidence")
  expect(calls()).toHaveLength(0)
})

it("shows an explicit error when saved conversation access is revoked", async () => {
  state.params = new URLSearchParams()
  state.fetch.mockImplementation(async (url: string) => url.endsWith("/sessions/saved")
    ? new Response("{}", { status: 403 }) : new Response("[]"))
  render(<GLensChatPage initialSessionId="saved" />)
  expect(await screen.findByRole("alert")).toHaveTextContent("unavailable or outside your access")
  expect(calls()).toHaveLength(0)
})
