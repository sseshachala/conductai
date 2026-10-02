import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

const state = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch }) }))
vi.mock("@/lib/api", () => ({ API: "https://local.example" }))
import McpInventoryLinks from "./McpInventoryLinks"

const registered = { id: "server", name: "Docs registry", review_status: "approved" }
function installation(linked = false) {
  return {
    agent_id: "agent", framework: "codex", device_id: "device-1", installation_id: "a".repeat(64),
    last_seen_at: "2026-10-01T00:00:00Z", revision: linked ? 3 : 2,
    servers: [{ reference_id: "b".repeat(64), name: "docs", scope: "user", transport: "stdio",
      discovery_status: "discovered", registration_status: linked ? "linked" : "unlinked",
      registration: linked ? registered : null, association_source: linked ? "administrator" : null,
      endpoint_identity: "unverified", enforcement_status: "not_observed", linked_at: null }],
  }
}
function response(linked = false, next: number | null = null) {
  return new Response(JSON.stringify({ registrations: [registered], installations: [installation(linked)], next_offset: next }))
}
beforeEach(() => { vi.clearAllMocks(); state.fetch.mockImplementation(async () => response()) })
afterEach(cleanup)

it("shows discovery separately from registration, review and enforcement", async () => {
  state.fetch.mockImplementation(async () => response(true))
  render(<McpInventoryLinks workspaceId="workspace" isAdmin={false} />)
  expect(await screen.findByText("Approved catalog")).toBeInTheDocument()
  expect(screen.getByText("Discovered")).toBeInTheDocument()
  expect(screen.getByText("Not observed")).toBeInTheDocument()
  expect(screen.getByText("Endpoint identity unverified")).toBeInTheDocument()
  expect(screen.queryByRole("combobox")).toBeNull()
  expect(screen.queryByRole("button", { name: "Unlink docs" })).toBeNull()
  expect(screen.getByRole("link", { name: "Review registered servers" })).toHaveAttribute("href", "/integrations")
})

it("links explicitly with the current revision and selected workspace", async () => {
  render(<McpInventoryLinks workspaceId="workspace" isAdmin />)
  fireEvent.change(await screen.findByRole("combobox"), { target: { value: "server" } })
  state.fetch.mockResolvedValueOnce(new Response(JSON.stringify(installation(true))))
  fireEvent.click(screen.getByRole("button", { name: "Link docs" }))
  expect(await screen.findByText("Approved catalog")).toBeInTheDocument()
  expect(state.fetch.mock.calls[1][0]).toContain("/agents/agent/mcp-links/" + "b".repeat(64) + "?workspace_id=workspace")
  expect(JSON.parse(state.fetch.mock.calls[1][1].body)).toEqual({ server_id: "server", revision: 2 })
  expect(screen.getByText("Not observed")).toBeInTheDocument()
})

it("unlinks without deleting a registration", async () => {
  state.fetch.mockResolvedValueOnce(response(true))
  render(<McpInventoryLinks workspaceId="workspace" isAdmin />)
  await screen.findByText("Approved catalog")
  state.fetch.mockResolvedValueOnce(new Response(JSON.stringify(installation())))
  fireEvent.click(screen.getByRole("button", { name: "Unlink docs" }))
  expect(await screen.findByText("Not linked")).toBeInTheDocument()
  expect(JSON.parse(state.fetch.mock.calls[1][1].body)).toEqual({ server_id: null, revision: 3 })
})

it("keeps stale evidence visible without offering new links", async () => {
  const item = installation(true)
  item.servers[0].discovery_status = "stale"
  state.fetch.mockResolvedValueOnce(new Response(JSON.stringify({ registrations: [registered], installations: [item], next_offset: null })))
  render(<McpInventoryLinks workspaceId="workspace" isAdmin />)
  expect(await screen.findByText("Stale scan")).toBeInTheDocument()
  expect(screen.queryByRole("combobox")).toBeNull()
  expect(screen.getByRole("button", { name: "Unlink docs" })).toBeInTheDocument()
})

it("reports conflict without pretending the link succeeded", async () => {
  render(<McpInventoryLinks workspaceId="workspace" isAdmin />)
  fireEvent.change(await screen.findByRole("combobox"), { target: { value: "server" } })
  state.fetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Refresh before retrying" }), { status: 409 }))
  fireEvent.click(screen.getByRole("button", { name: "Link docs" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("Refresh before retrying")
  expect(screen.queryByText("Approved catalog")).toBeNull()
})

it("paginates and clears prior workspace findings on access denial", async () => {
  state.fetch.mockResolvedValueOnce(response(false, 100))
  const view = render(<McpInventoryLinks key="a" workspaceId="a" isAdmin={false} />)
  await screen.findByText("Not linked")
  fireEvent.click(screen.getByRole("button", { name: "Next MCP page" }))
  await waitFor(() => expect(state.fetch.mock.calls[1][0]).toContain("offset=100"))
  state.fetch.mockResolvedValueOnce(new Response("{}", { status: 403 }))
  view.rerender(<McpInventoryLinks key="b" workspaceId="b" isAdmin={false} />)
  expect(await screen.findByRole("alert")).toHaveTextContent("access denied")
  expect(screen.queryByText("docs")).toBeNull()
})
