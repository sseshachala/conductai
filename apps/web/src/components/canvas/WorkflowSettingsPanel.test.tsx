import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import WorkflowSettingsPanel from "./WorkflowSettingsPanel"

const state = vi.hoisted(() => ({ get: vi.fn(), update: vi.fn(), prefsUpdate: vi.fn(), profiles: vi.fn(), persona: vi.fn() }))
vi.mock("@/lib/WorkspaceContext", () => ({ useWorkspace: () => ({ activeWorkspace: { id: "workspace" } }) }))
vi.mock("@/lib/PreferencesContext", () => ({ usePreferences: () => ({
  prefs: { show_test_trigger: true, show_dry_run: false }, loading: false, update: state.prefsUpdate,
}) }))
vi.mock("@/lib/api", () => ({
  workflows: { get: state.get, update: state.update },
  guard: { config: { persona: state.persona }, gatewayProfilesV2: { list: state.profiles } },
}))
beforeEach(() => {
  vi.clearAllMocks()
  state.get.mockResolvedValue({ id: "workflow", name: "Example workflow", default_max_turns: null, agent_identity_required: true })
  state.persona.mockResolvedValue({ workspace_runtime_persona: "conservative" })
  state.profiles.mockResolvedValue([])
})
afterEach(cleanup)

it("shows toolbar preferences inside workflow settings without editing the workflow", async () => {
  render(<WorkflowSettingsPanel workflowId="workflow" getToken={null} onDelete={vi.fn()} />)
  const toolbar = await screen.findByRole("region", { name: "Canvas toolbar" })
  fireEvent.click(within(toolbar).getByRole("switch", { name: "Show Dry Run button" }))
  expect(state.prefsUpdate).toHaveBeenCalledWith({ show_dry_run: true })
  expect(state.update).not.toHaveBeenCalled()
})

it("passes viewer permissions through to the moved toolbar controls", async () => {
  render(<WorkflowSettingsPanel workflowId="workflow" getToken={null} onDelete={vi.fn()} isViewer />)
  const toolbar = await screen.findByRole("region", { name: "Canvas toolbar" })
  for (const control of within(toolbar).getAllByRole("switch")) expect(control).toBeDisabled()
})
