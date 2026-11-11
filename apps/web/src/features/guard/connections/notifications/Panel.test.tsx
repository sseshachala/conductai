import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor, fireEvent } from "@testing-library/react"

const listNotifs = vi.fn()
const createNotif = vi.fn()
const channelEntries = vi.fn()

const stableFetch = { authFetch: vi.fn() } // stable identity: effects depend on it
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => stableFetch }))
vi.mock("@/lib/api", () => ({
  guard: {
    notifications: {
      list: (...a: unknown[]) => listNotifs(...a),
      create: (...a: unknown[]) => createNotif(...a),
      remove: vi.fn(),
      test: vi.fn(),
    },
  },
  environments: { list: () => Promise.resolve([{ id: "env-prod", name: "Production" }, { id: "env-staging", name: "Staging" }]) },
  credentials: {
    slack: { integration: () => Promise.resolve([]) },
    channelEntries: (...a: unknown[]) => channelEntries(...a),
  },
}))
vi.mock("./AlertsCard", () => ({ default: () => null, parseSourceFilter: () => null }))

import NotificationsPanel from "./Panel"

const groups = (channels: unknown[]) => ({
  workspace_id: "w",
  groups: ["block", "warn", "audit", "approval", "fail_open", "drift"].map(action => ({
    action, channels: action === "block" ? channels : [],
  })),
})

beforeEach(() => {
  vi.clearAllMocks()
  createNotif.mockResolvedValue({})
  listNotifs.mockResolvedValue(groups([]))
  channelEntries.mockImplementation((_f: unknown, _w: string, service: string) => Promise.resolve(
    service === "pagerduty"
      ? [
          { id: "pd-prod", handle: "pagerduty", environment_id: "env-prod", environment_name: "Production" },
          { id: "pd-staging", handle: "pagerduty", environment_id: "env-staging", environment_name: "Staging" },
        ]
      : service === "email"
        ? [{ id: "em-prod", handle: "email", environment_id: "env-prod", environment_name: "Production" }]
        : [],
  ))
})

async function openAdd(label: string) {
  fireEvent.click((await screen.findAllByText("+ Add channel ▾"))[0])
  fireEvent.click(screen.getByText(label))
}

describe("Guard rules card Vault pickers", () => {
  it("PagerDuty picks an entry from the selected Vault, no secret field", async () => {
    render(<NotificationsPanel workspaceId="w" isAdmin />)
    await screen.findByLabelText("Vault")
    fireEvent.change(screen.getByLabelText("Vault"), { target: { value: "env-staging" } })
    await openAdd("PagerDuty")
    expect(screen.queryByPlaceholderText(/routing key/i)).toBeNull()
    fireEvent.click(screen.getByText("Save"))
    await waitFor(() => expect(createNotif).toHaveBeenCalled())
    expect(createNotif.mock.calls[0][2]).toMatchObject({
      action: "block", channel_type: "pagerduty", integration_id: "pd-staging", channel_ref: "",
    })
  })

  it("Webhook with no entry in the Vault links to Settings and cannot be saved", async () => {
    render(<NotificationsPanel workspaceId="w" isAdmin />)
    await openAdd("Webhook")
    expect(screen.getByText(/No Webhook entry — add one in Settings → Vault/)).toBeTruthy()
    expect((screen.getByText("Save") as HTMLButtonElement).disabled).toBe(true)
  })

  it("Email asks for a recipient and sends the optional Vault entry", async () => {
    render(<NotificationsPanel workspaceId="w" isAdmin />)
    await openAdd("Email")
    fireEvent.change(screen.getByLabelText("Recipient address"), { target: { value: "ops@example.com" } })
    fireEvent.change(screen.getByLabelText("Email Vault entry"), { target: { value: "em-prod" } })
    fireEvent.click(screen.getByText("Save"))
    await waitFor(() => expect(createNotif).toHaveBeenCalled())
    expect(createNotif.mock.calls[0][2]).toMatchObject({
      channel_type: "email", channel_ref: "ops@example.com", integration_id: "em-prod",
    })
  })

  it("rows show the Vault environment, and legacy rows the move-to-Vault hint", async () => {
    listNotifs.mockResolvedValue(groups([
      { id: "1", action: "block", channel_type: "pagerduty", integration_id: "pd-prod", channel_ref: "vault:pagerduty",
        vault_handle: "pagerduty", environment_name: "Production", legacy_ref: false, enabled: true },
      { id: "2", action: "block", channel_type: "pagerduty", integration_id: null, channel_ref: "abcd…wxyz",
        legacy_ref: true, enabled: true },
    ]))
    render(<NotificationsPanel workspaceId="w" isAdmin />)
    expect(await screen.findByText(/· Production/)).toBeTruthy()
    expect(screen.getAllByText(/Typed key — move to Vault/)).toHaveLength(1)
    expect(screen.getByText(/abcd…wxyz/)).toBeTruthy()
  })
})
