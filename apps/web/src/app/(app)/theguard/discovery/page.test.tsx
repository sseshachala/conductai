import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import Page from "./page"

const mocks = vi.hoisted(() => ({ summary: vi.fn(), agents: vi.fn(), scans: vi.fn(), authFetch: vi.fn(), workspaceId: "workspace-a" }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: mocks.authFetch, workspaceId: mocks.workspaceId }) }))
vi.mock("@/lib/api", () => ({ guard: { discover: mocks } }))
vi.mock("@/components/AppShell", () => ({ default: ({ children }: any) => children }))
vi.mock("@/components/guard/GuardShell", () => ({ GuardShell: ({ children }: any) => children }))
vi.mock("@/components/glens/AskLensLink", () => ({ AskLensLink: ({ resourceId }: any) => <a href={`#${resourceId}`}>Ask Lens</a> }))

const agent = { id: "one", framework: "codex", device_id: "device-one", installation_id: "a", detection: "installed",
  freshness: "fresh", hooks_status: "configured", gateway_status: "unverified", last_seen_at: "2026-09-27T12:00:00Z",
  hook_observed_at: null, hook_event_id: null, mcp_configured: false, evidence: { signals: ["tool_installation"] },
  evidence_note: "Configuration is not proof of enforcement.", remediation: { label: "Configure tool", command: "conduct guard sync", detail: "Restart and rescan." } }

beforeEach(() => {
  vi.clearAllMocks()
  mocks.workspaceId = "workspace-a"
  mocks.summary.mockResolvedValue({ total: 1, confirmed: 1, possible_integrations: 0, recent_hook_evidence: 0, needs_attention: 1 })
  mocks.agents.mockResolvedValue([agent])
  mocks.scans.mockResolvedValue([])
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", "") }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); this.dispatchEvent(new Event("close")) }
})

describe("discovery evidence", () => {
  it("shows separate states and evidence without claiming coverage", async () => {
    render(<Page/>)
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
    render(<Page/>)
    await screen.findByText("Codex")
    fireEvent.change(screen.getByLabelText("Search tool or device"), { target: { value: "missing" } })
    expect(screen.getByText("No findings match these filters.")).toBeTruthy()
    fireEvent.change(screen.getByLabelText("Search tool or device"), { target: { value: "device-one" } })
    expect(screen.getByText("Codex")).toBeTruthy()
  })
  it("shows failures rather than an empty success", async () => {
    mocks.agents.mockRejectedValue(new Error("offline"))
    render(<Page/>)
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load discovery")
    expect(screen.queryByText("No discovery findings.")).toBeNull()
  })
  it("loads subsequent pages", async () => {
    mocks.summary.mockResolvedValue({ total: 101, confirmed: 101 })
    mocks.agents.mockImplementation((_: unknown, offset: number) => Promise.resolve(offset ? [{ ...agent, id: "two", framework: "cursor" }] : [agent]))
    render(<Page/>)
    fireEvent.click(await screen.findByRole("button", { name: "Load more" }))
    await screen.findByText("Cursor")
    expect(mocks.agents).toHaveBeenCalledWith(mocks.authFetch, 100, 100, "current")
  })
  it("clears old workspace results immediately", async () => {
    const view = render(<Page/>)
    await screen.findByText("Codex")
    mocks.workspaceId = "workspace-b"
    mocks.agents.mockReturnValue(new Promise(() => {}))
    view.rerender(<Page/>)
    expect(screen.queryByText("Codex")).toBeNull()
  })
  it("keeps the legacy filter accessible when only legacy findings exist", async () => {
    mocks.summary.mockResolvedValue({ total: 1, confirmed: 0, legacy_unverified: 1 })
    mocks.agents.mockImplementation((_: unknown, __: unknown, ___: unknown, inventory: string) => Promise.resolve(inventory === "legacy" ? [{ ...agent, detection: "legacy_unverified" }] : []))
    render(<Page/>)
    fireEvent.change(await screen.findByLabelText("Filter findings"), { target: { value: "legacy_unverified" } })
    await screen.findByText("Codex")
    expect(mocks.agents).toHaveBeenCalledWith(mocks.authFetch, 0, 100, "legacy")
  })
})
