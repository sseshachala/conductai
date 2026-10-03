import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import Page from "./page"

const state = vi.hoisted(() => ({
  tab: "profiles", role: "admin", workspace: "workspace-a", query: "", fetch: vi.fn(), profiles: vi.fn(), create: vi.fn(), environments: vi.fn(), rates: vi.fn(),
}))
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(`tab=${state.tab}${state.query}`) }))
vi.mock("@/components/AppShell", () => ({ default: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/hooks/useGuardRole", () => ({ useGuardRole: () => ({ role: state.role }) }))
vi.mock("@/lib/WorkspaceContext", () => ({ useWorkspace: () => ({ activeWorkspace: { id: state.workspace } }) }))
vi.mock("@/lib/api/client", () => ({ API: "https://api.example" }))
vi.mock("@/lib/api", () => ({
  environments: { list: state.environments },
  guard: { gatewayProfilesV2: { list: state.profiles, create: state.create, rateLimits: { get: state.rates } } },
}))
vi.mock("@/components/settings/GatewayProfileV2DeleteDialog", () => ({ default: () => null }))
vi.mock("@/components/settings/GatewayProfileV2ImportDialog", () => ({ default: () => null }))
vi.mock("@/components/settings/GatewayProfileV2Editor", () => ({ default: () => null }))
vi.mock("@/components/settings/GatewayProfileV2PublishDialog", () => ({ default: () => null }))
beforeEach(() => {
  vi.clearAllMocks()
  state.tab = "profiles"; state.role = "admin"; state.workspace = "workspace-a"; state.query = ""
  state.profiles.mockResolvedValue([]); state.environments.mockResolvedValue([])
  state.create.mockResolvedValue({ id: "created" })
  state.rates.mockResolvedValue({ rpm: 60, tpm: 100000, agent_limits: [], available_agents: [] })
})
afterEach(cleanup)

it("does not fetch limits until a profile is selected", async () => {
  render(<Page />)
  expect(screen.queryByRole("tab", { name: "Rate limits" })).toBeNull()
  await waitFor(() => expect(state.profiles).toHaveBeenCalledWith(state.fetch, "workspace-a"))
  expect(state.rates).not.toHaveBeenCalled()
})

const profile = { id: "profile-id", name: "Production", model_alias: "coding", cond_code: "abc12345",
  active_revision_id: "revision-id", created_at: "2026-10-02", revisions: [],
  working_copy: { name: "Production", model_alias: "coding", targets: [{ id: "primary", provider: "openai" }] } }

it("opens old rate-limit bookmarks as profiles, with editable published-profile limits", async () => {
  state.tab = "rate_limits"
  state.profiles.mockResolvedValue([profile])
  render(<Page />)
  await waitFor(() => expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(60), { timeout: 5000 })
  expect(state.rates).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-id")
  expect(screen.getByRole("button", { name: "Save limits" })).toBeEnabled()
})

it("loads limits only for the selected profile", async () => {
  state.query = "&select=profile-id"
  state.profiles.mockResolvedValue([{ ...profile, id: "another-profile" }, profile])
  render(<Page />)
  await waitFor(() => expect(state.rates).toHaveBeenCalledWith(state.fetch, "workspace-a", "profile-id"))
  expect(state.rates).toHaveBeenCalledTimes(1)
})

it("does not expose admin limits to viewers through a bookmarked URL", async () => {
  state.tab = "rate_limits"; state.role = "viewer"
  state.profiles.mockResolvedValue([profile])
  render(<Page />)
  await screen.findByText("published · locked")
  expect(screen.queryByRole("tab", { name: "Rate limits" })).toBeNull()
  expect(state.rates).not.toHaveBeenCalled()
  expect(screen.queryByRole("spinbutton")).toBeNull()
})

it("clears old rate values immediately when the workspace changes", async () => {
  state.tab = "rate_limits"
  state.profiles.mockResolvedValue([profile])
  const view = render(<Page />)
  await waitFor(() => expect(screen.getByRole("spinbutton", { name: "Requests / min (RPM)" })).toHaveValue(60), { timeout: 5000 })
  state.workspace = "workspace-b"
  state.profiles.mockReturnValue(new Promise(() => {}))
  view.rerender(<Page />)
  expect(screen.queryByRole("spinbutton", { name: "Requests / min (RPM)" })).toBeNull()
  expect(screen.queryByRole("button", { name: "Save limits" })).toBeNull()
})

it("blocks publishing an invalid saved draft and names the missing alias", async () => {
  state.profiles.mockResolvedValue([{ id: "draft", name: "Case 3", model_alias: null, cond_code: "abc12345",
    active_revision_id: null, created_at: "2026-10-02", revisions: [],
    working_copy: { name: "Case 3", model_alias: "", targets: [{}] } }])
  render(<Page />)
  const publish = await screen.findByRole("button", { name: "Publish…" })
  expect(publish).toBeDisabled()
  expect(publish).toHaveAttribute("title", "Enter an alias.")
})

it("creates a mixed Claude/OpenAI SDK fallback profile with common operations", async () => {
  render(<Page />)
  fireEvent.click(await screen.findByRole("button", { name: "Claude + OpenAI fallback via LiteLLM" }))
  await waitFor(() => expect(state.create).toHaveBeenCalled())
  const workingCopy = state.create.mock.calls[0][2].working_copy
  expect(workingCopy.accepts).toEqual(["anthropic_messages", "openai_chat_completions"])
  expect(workingCopy.targets.map((target: { transport: string; provider: string }) => [target.transport, target.provider]))
    .toEqual([["litellm_sdk", "anthropic"], ["litellm_sdk", "openai"]])
  expect(workingCopy.max_attempts).toBe(2)
  expect(workingCopy.model_alias).not.toBe("")
})
