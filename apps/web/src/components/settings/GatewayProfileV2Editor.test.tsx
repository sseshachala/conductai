import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { GatewayProfileV2Out } from "@/lib/api/guard"
import { GatewayValidationError } from "@/lib/api/guard"
import Editor from "./GatewayProfileV2Editor"
import PublishDialog from "./GatewayProfileV2PublishDialog"

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), update: vi.fn(), publish: vi.fn(), credentials: vi.fn() }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: mocks.fetch }) }))
vi.mock("@/lib/api", () => ({
  API: "https://api.example", credentials: { byEnvironment: mocks.credentials },
  guard: { gatewayProfilesV2: { updateWorkingCopy: mocks.update, publish: mocks.publish } },
}))

function profile(alias = "coding"): GatewayProfileV2Out {
  return {
    id: "profile", workspace_id: "workspace", name: "Case 3", model_alias: alias, cond_code: "abc12345",
    active_revision_id: null, revisions: [], created_at: "2026-10-02", updated_at: "2026-10-02",
    working_copy: { name: "Case 3", model_alias: alias, timeout_seconds: 60, max_attempts: 2,
      accepts: ["anthropic_messages"], targets: [{ id: "primary", transport: "native_http",
        provider: "anthropic", model: "claude-sonnet-4-6",
        credential_ref: "vault://bbbbbbbb-0000-4000-8000-000000000001/anthropic" }] },
  }
}
function renderEditor(p = profile(), isAdmin = true) {
  return render(<Editor workspaceId="workspace" profile={p} isAdmin={isAdmin} onSaved={vi.fn()}
    envs={[{ id: "bbbbbbbb-0000-4000-8000-000000000001", name: "Production" }]} />)
}
beforeEach(() => {
  vi.clearAllMocks()
  mocks.fetch.mockResolvedValue(new Response(JSON.stringify({ tier_map: { anthropic: { balanced: "claude-sonnet-4-6" } } })))
  mocks.credentials.mockResolvedValue([{ handle: "anthropic" }])
  mocks.update.mockResolvedValue(profile())
  mocks.publish.mockResolvedValue(profile())
})
afterEach(cleanup)

it("flags the missing alias next to the field and prevents invalid saves", () => {
  renderEditor(profile(""))
  const alias = screen.getByRole("textbox", { name: "Alias" })
  expect(alias).toBeRequired()
  expect(alias).toHaveAttribute("aria-invalid", "true")
  expect(alias).toHaveAccessibleDescription("Enter an alias.")
  const save = screen.getByRole("button", { name: "Save working copy" })
  expect(save).toBeDisabled()
  fireEvent.click(save)
  expect(mocks.update).not.toHaveBeenCalled()
})

it("clears the alias error and saves once it is filled", async () => {
  renderEditor(profile(""))
  fireEvent.change(screen.getByRole("textbox", { name: "Alias" }), { target: { value: "  coding  " } })
  expect(screen.queryByText("Enter an alias.")).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Save working copy" }))
  await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(mocks.fetch, "workspace", "profile",
    expect.objectContaining({ name: "Case 3", model_alias: "coding" })))
})

it("requires a name", () => {
  renderEditor()
  fireEvent.change(screen.getByRole("textbox", { name: "Name" }), { target: { value: " " } })
  expect(screen.getByRole("textbox", { name: "Name" })).toHaveAccessibleDescription("Enter a name.")
  expect(screen.getByRole("button", { name: "Save working copy" })).toBeDisabled()
})

it.each([
  ["Timeout (s)", "601", "Enter a whole number from 1 to 600 seconds."],
  ["Timeout (s)", "1.5", "Enter a whole number from 1 to 600 seconds."],
  ["Max attempts", "6", "Enter a whole number from 1 to 5."],
])("validates %s against the API limits", (name, value, message) => {
  renderEditor()
  fireEvent.change(screen.getByRole("spinbutton", { name }), { target: { value } })
  expect(screen.getByRole("spinbutton", { name })).toHaveAccessibleDescription(message)
  expect(screen.getByRole("button", { name: "Save working copy" })).toBeDisabled()
  fireEvent.change(screen.getByRole("spinbutton", { name }), { target: { value: "2" } })
  expect(screen.getByRole("button", { name: "Save working copy" })).toBeEnabled()
})

it("shows a readable server error and clears it on correction", async () => {
  mocks.update.mockRejectedValue(new GatewayValidationError("schema invalid", [
    { path: "model_alias", target_index: null, type: "string_too_short", message: "String should have at least 1 character" },
  ]))
  renderEditor()
  fireEvent.click(screen.getByRole("button", { name: "Save working copy" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("Alias: Enter an alias.")
  fireEvent.change(screen.getByRole("textbox", { name: "Alias" }), { target: { value: "claude" } })
  expect(screen.queryByRole("alert")).toBeNull()
})

it("does not add editable validation controls to published read-only profiles", () => {
  renderEditor(profile(""), false)
  expect(screen.getByRole("textbox", { name: "Alias" })).toBeDisabled()
  expect(screen.queryByText("Enter an alias.")).toBeNull()
  expect(screen.queryByRole("button", { name: "Save working copy" })).toBeNull()
})

it("explains why an invalid saved draft cannot be published", () => {
  render(<PublishDialog workspaceId="workspace" profile={profile(" ")} onClose={vi.fn()} onPublished={vi.fn()} />)
  expect(screen.getByRole("alert")).toHaveTextContent("Enter an alias.")
  const publish = screen.getByRole("button", { name: "Publish" })
  expect(publish).toBeDisabled()
  fireEvent.click(publish)
  expect(mocks.publish).not.toHaveBeenCalled()
})

it("publishes a valid saved draft", async () => {
  const onPublished = vi.fn()
  render(<PublishDialog workspaceId="workspace" profile={profile()} onClose={vi.fn()} onPublished={onPublished} />)
  fireEvent.click(screen.getByRole("button", { name: "Publish" }))
  await waitFor(() => expect(onPublished).toHaveBeenCalled())
  expect(mocks.publish).toHaveBeenCalledWith(mocks.fetch, "workspace", "profile")
})

it("derives SDK cross-provider operations when switching transport", async () => {
  renderEditor()
  fireEvent.change(screen.getByRole("combobox", { name: /Transport/ }), { target: { value: "litellm_sdk" } })
  fireEvent.click(screen.getByRole("button", { name: "Save working copy" }))
  await waitFor(() => expect(mocks.update).toHaveBeenCalled())
  expect(mocks.update.mock.calls[0][3].accepts).toEqual(["anthropic_messages", "anthropic_count_tokens", "openai_chat_completions"])
})

it("narrows custom operations to the selected protocol", async () => {
  const p = profile()
  p.working_copy = { ...p.working_copy, accepts: ["openai_chat_completions"], targets: [{ id: "primary", transport: "http_passthrough",
    integration: "custom", model: "fixture", endpoint: "https://fixture.example/v1",
    credential_ref: "vault://bbbbbbbb-0000-4000-8000-000000000001/anthropic", provider_options: { protocol: "openai" } }] }
  renderEditor(p)
  fireEvent.change(screen.getByRole("combobox", { name: /Protocol/ }), { target: { value: "anthropic" } })
  fireEvent.click(screen.getByRole("button", { name: "Save working copy" }))
  await waitFor(() => expect(mocks.update).toHaveBeenCalled())
  expect(mocks.update.mock.calls[0][3].accepts).toEqual(["anthropic_messages", "anthropic_count_tokens"])
})
