import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

const state = vi.hoisted(() => ({
  workspace: "workspace-a", role: "viewer", fetch: vi.fn(),
  summary: vi.fn(), agents: vi.fn(), scans: vi.fn(),
}))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ workspaceId: state.workspace, authFetch: state.fetch }) }))
vi.mock("@/components/AppShell", () => ({ default: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/components/guard/GuardShell", () => ({ GuardShell: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/components/guard/common", () => ({ GuardPageHeader: ({ title }: { title: string }) => <h1>{title}</h1> }))
vi.mock("@/components/glens/AskLensLink", () => ({ AskLensLink: ({ resourceId }: { resourceId: string }) => <a href={`#${resourceId}`}>Ask Lens</a> }))
vi.mock("@/lib/api", () => ({ API: "https://api.example", guard: { discover: {
  summary: state.summary, agents: state.agents, scans: state.scans,
} } }))
import DiscoveryPage from "./page"

const agent = {
  id: "agent", framework: "codex", device_id: "device-1", installation_id: "install-1",
  detection: "installed", freshness: "fresh", hooks_status: "observed",
  gateway_status: "connection_verified", mcp_configured: true, last_seen_at: "2026-10-02T12:21:00Z",
  evidence: { signals: ["tool_installation"] },
  hook_observed_at: null, hook_event_id: null,
  evidence_note: "Configuration is not proof of enforcement.",
  remediation: { label: "Configure tool", command: "conduct guard sync", detail: "Restart and rescan." },
}
const inventory = {
  registrations: [{ id: "server", name: "Docs registry", review_status: "approved" }], next_offset: null,
  installations: [{ agent_id: "agent", framework: "codex", device_id: "device-1", installation_id: "install-1",
    last_seen_at: agent.last_seen_at, revision: 0, servers: [{ reference_id: "reference", name: "docs", scope: "user", transport: "stdio",
      discovery_status: "discovered", registration_status: "unlinked", registration: null,
      association_source: null, linked_at: null, endpoint_identity: "unverified", enforcement_status: "not_observed" }] }],
}

beforeEach(() => {
  vi.clearAllMocks()
  state.workspace = "workspace-a"; state.role = "viewer"
  state.summary.mockResolvedValue({ total: 1, confirmed: 1, possible_integrations: 0, recent_hook_evidence: 1, needs_attention: 0, legacy_unverified: 0 })
  state.agents.mockResolvedValue([agent]); state.scans.mockResolvedValue([])
  state.fetch.mockImplementation(async (url: string) => new Response(JSON.stringify(
    url.endsWith("/my-role") ? { role: state.role } : inventory)))
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", "") }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); this.dispatchEvent(new Event("close")) }
})
afterEach(cleanup)

function openInventory() {
  const details = screen.getByText("MCP inventory").closest("details")!
  details.open = true
  fireEvent(details, new Event("toggle"))
}

it("shows installation and MCP status beside hook and Gateway evidence", async () => {
  render(<DiscoveryPage />)
  const table = await screen.findByRole("table", { name: "Discovered tool installations" })
  expect(within(table).getByText("device-1 / install-")).toBeInTheDocument()
  expect(within(table).getByText("Activity observed")).toBeInTheDocument()
  expect(within(table).getByText("Configured")).toBeInTheDocument()
  expect(within(table).getByText("Connection verified")).toBeInTheDocument()
  expect(screen.getByRole("link", { name: "Tool Setup" })).toHaveAttribute("href", "/settings?tab=tool_setup")
  expect(state.fetch.mock.calls.some(([url]) => url.includes("mcp-reconciliation"))).toBe(false)
})

it.each(["viewer", "admin"])("loads MCP inventory on expansion with %s permissions", async role => {
  state.role = role
  render(<DiscoveryPage />)
  await screen.findByRole("table", { name: "Discovered tool installations" })
  openInventory()
  const table = await screen.findByRole("table", { name: "MCP inventory associations" })
  expect(within(table).getByText("docs")).toBeInTheDocument()
  expect(within(table).getByText("Not observed")).toBeInTheDocument()
  await waitFor(() => expect(state.fetch.mock.calls.some(([url]) => url.includes("workspace_id=workspace-a"))).toBe(true))
  if (role === "admin") expect(await within(table).findByRole("combobox", { name: "Registration for docs" })).toBeInTheDocument()
  else expect(within(table).queryByRole("combobox")).toBeNull()
})

it("clears prior workspace inventory and admin controls when workspace access fails", async () => {
  state.role = "admin"
  const view = render(<DiscoveryPage />)
  await screen.findByRole("table", { name: "Discovered tool installations" })
  openInventory()
  await screen.findByRole("combobox", { name: "Registration for docs" })
  state.workspace = "workspace-b"
  state.agents.mockRejectedValueOnce(new Error("denied"))
  state.fetch.mockImplementation(async () => new Response("{}", { status: 403 }))
  view.rerender(<DiscoveryPage />)
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load discovery")
  expect(screen.queryByText("docs")).toBeNull()
  expect(screen.queryByText("device-1 / install-")).toBeNull()
  expect(screen.queryByRole("combobox", { name: "Registration for docs" })).toBeNull()
})

describe("discovery evidence", () => {
  it("shows passive MCP references without claiming approval", async () => {
    state.agents.mockResolvedValue([{ ...agent, evidence: { signals: [], mcp_servers: [
      { id: "mcp-one", name: "github", scope: "project", transport: "http", disabled: false },
      { id: "mcp-two", name: "filesystem", scope: "user", transport: "stdio", disabled: true },
    ] } }])
    render(<DiscoveryPage />)
    fireEvent.click(await screen.findByRole("button", { name: "Evidence" }))
    expect(screen.getByText("MCP configuration")).toBeTruthy()
    expect(screen.getByText("github")).toBeTruthy()
    expect(screen.getByText("user · stdio · Disabled")).toBeTruthy()
    expect(screen.queryByText("Approved")).toBeNull()
  })

  it("shows separate states and evidence without claiming coverage", async () => {
    state.agents.mockResolvedValue([{ ...agent, hooks_status: "configured", mcp_configured: false }])
    render(<DiscoveryPage />)
    await screen.findByText("Codex")
    expect(screen.getByText("Configured")).toBeTruthy()
    expect(screen.queryByText(/Under Guard|coverage.*%/)).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Evidence" }))
    expect(await screen.findByRole("dialog")).toBeTruthy()
    expect(screen.getByText("conduct guard sync")).toBeTruthy()
    expect(screen.getByText("Configuration is not proof of enforcement.")).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Close evidence" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("filters loaded findings", async () => {
    render(<DiscoveryPage />)
    await screen.findByText("Codex")
    fireEvent.change(screen.getByLabelText("Search tool or device"), { target: { value: "missing" } })
    expect(screen.getByText("No findings match these filters.")).toBeTruthy()
    fireEvent.change(screen.getByLabelText("Search tool or device"), { target: { value: "device-1" } })
    expect(screen.getByText("Codex")).toBeTruthy()
  })

  it("shows failures rather than an empty success", async () => {
    state.agents.mockRejectedValue(new Error("offline"))
    render(<DiscoveryPage />)
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load discovery")
    expect(screen.queryByText("No discovery findings.")).toBeNull()
  })

  it("loads subsequent pages", async () => {
    state.summary.mockResolvedValue({ total: 101, confirmed: 101 })
    state.agents.mockImplementation((_: unknown, offset: number) => Promise.resolve(offset ? [{ ...agent, id: "two", framework: "cursor" }] : [agent]))
    render(<DiscoveryPage />)
    fireEvent.click(await screen.findByRole("button", { name: "Load more" }))
    await screen.findByText("Cursor")
    expect(state.agents).toHaveBeenCalledWith(state.fetch, 100, 100, "current")
  })

  it("clears old workspace results immediately", async () => {
    const view = render(<DiscoveryPage />)
    await screen.findByText("Codex")
    state.workspace = "workspace-b"
    state.agents.mockReturnValue(new Promise(() => {}))
    view.rerender(<DiscoveryPage />)
    expect(screen.queryByText("Codex")).toBeNull()
  })

  it("keeps the legacy filter accessible when only legacy findings exist", async () => {
    state.summary.mockResolvedValue({ total: 1, confirmed: 0, legacy_unverified: 1 })
    state.agents.mockImplementation((_: unknown, __: unknown, ___: unknown, inventory: string) => Promise.resolve(inventory === "legacy" ? [{ ...agent, detection: "legacy_unverified" }] : []))
    render(<DiscoveryPage />)
    fireEvent.change(await screen.findByLabelText("Filter findings"), { target: { value: "legacy_unverified" } })
    await screen.findByText("Codex")
    expect(state.agents).toHaveBeenCalledWith(state.fetch, 0, 100, "legacy")
  })
})
