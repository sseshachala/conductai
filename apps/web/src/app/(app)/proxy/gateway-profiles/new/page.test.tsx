import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import Page from "./page"

const state = vi.hoisted(() => ({
  role: "admin", fetch: vi.fn(), create: vi.fn(), list: vi.fn(), push: vi.fn(),
}))
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: state.push }) }))
vi.mock("@/components/AppShell", () => ({ default: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/hooks/useGuardRole", () => ({ useGuardRole: () => ({ role: state.role }) }))
vi.mock("@/lib/WorkspaceContext", () => ({ useWorkspace: () => ({ activeWorkspace: { id: "ws" } }) }))
vi.mock("@/lib/api", () => ({
  environments: { list: vi.fn().mockResolvedValue([]) },
  guard: { gatewayProfilesV2: { create: state.create, list: state.list } },
}))
vi.mock("@/components/settings/GatewayProfileV2Editor", () => ({
  default: ({ mode, onSaved }: { mode: string; onSaved: (p: { id: string }) => void }) => (
    <button onClick={() => onSaved({ id: "new-id" })}>editor-{mode}</button>
  ),
}))

beforeEach(() => {
  vi.clearAllMocks()
  state.role = "admin"
  state.list.mockResolvedValue([])
  state.create.mockResolvedValue({ id: "created" })
})
afterEach(cleanup)

it("navigates to the new profile's detail page after the editor saves", async () => {
  render(<Page />)
  fireEvent.click(await screen.findByRole("button", { name: "editor-create" }))
  expect(state.push).toHaveBeenCalledWith("/proxy/gateway-profiles/new-id")
})

it("creates a mixed Claude/OpenAI SDK fallback preset and opens its detail page", async () => {
  render(<Page />)
  fireEvent.click(await screen.findByRole("button", { name: "Claude + OpenAI fallback via LiteLLM" }))
  await waitFor(() => expect(state.create).toHaveBeenCalled())
  const workingCopy = state.create.mock.calls[0][2].working_copy
  expect(workingCopy.accepts).toEqual(["anthropic_messages", "openai_chat_completions"])
  expect(workingCopy.targets.map((t: { transport: string; provider: string }) => [t.transport, t.provider]))
    .toEqual([["litellm_sdk", "anthropic"], ["litellm_sdk", "openai"]])
  expect(workingCopy.model_alias).not.toBe("")
  await waitFor(() => expect(state.push).toHaveBeenCalledWith("/proxy/gateway-profiles/created"))
})

it("uniqueifies a preset name that is already taken", async () => {
  state.list.mockResolvedValue([{ name: "claude-openai" }])
  render(<Page />)
  await waitFor(() => expect(state.list).toHaveBeenCalled())
  await Promise.resolve()
  fireEvent.click(await screen.findByRole("button", { name: "Claude + OpenAI fallback via LiteLLM" }))
  await waitFor(() => expect(state.create).toHaveBeenCalled())
  expect(state.create.mock.calls[0][2].name).toBe("claude-openai-2")
})

it("blocks non-admins", async () => {
  state.role = "viewer"
  render(<Page />)
  expect(await screen.findByText(/Only workspace admins/)).toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "editor-create" })).toBeNull()
})
