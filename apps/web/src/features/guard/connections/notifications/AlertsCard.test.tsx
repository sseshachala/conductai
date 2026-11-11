import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor, fireEvent } from "@testing-library/react"

const registry = vi.fn()
const list = vi.fn()
const create = vi.fn()

vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: vi.fn() }) }))
vi.mock("@/lib/api", () => ({
  guard: {
    alerts: {
      registry: (...a: unknown[]) => registry(...a),
      list: (...a: unknown[]) => list(...a),
      create: (...a: unknown[]) => create(...a),
      remove: vi.fn(),
    },
    notifications: { test: vi.fn() },
  },
}))

import AlertsCard, { parseSourceFilter } from "./AlertsCard"

const REG = {
  sources: [
    { source_type: "guard", label: "Guard rules", scoped: false, events: [] },
    {
      source_type: "gateway", label: "Gateway profile", scoped: true,
      events: [{ event_type: "upstream_5xx", label: "Upstream 5xx", description: "", severity: "error", supports_threshold: true, default_dedupe_sec: 300 }],
    },
    {
      source_type: "audit_feed", label: "Audit feed", scoped: false,
      events: [{ event_type: "collector_stale", label: "Collector stale", description: "", severity: "error", supports_threshold: false, default_dedupe_sec: 0 }],
    },
  ],
}

const VAULT = {
  environments: [{ id: "env-prod", name: "Production" }, { id: "env-staging", name: "Staging" }],
  slackIntegrations: [
    { id: "int-prod", handle: "conduct", environment_id: "env-prod", environment_name: "Production" },
    { id: "int-staging", handle: "conduct", environment_id: "env-staging", environment_name: "Staging" },
  ],
  selectedEnvId: "env-prod",
}

beforeEach(() => {
  vi.clearAllMocks()
  registry.mockResolvedValue(REG)
  list.mockResolvedValue({ workspace_id: "w", channels: [] })
  create.mockResolvedValue({})
})

describe("parseSourceFilter", () => {
  it("parses source and optional id", () => {
    expect(parseSourceFilter(null)).toBeNull()
    expect(parseSourceFilter("gateway")).toEqual({ sourceType: "gateway", sourceId: null })
    expect(parseSourceFilter("gateway:abc-123")).toEqual({ sourceType: "gateway", sourceId: "abc-123" })
  })
})

describe("AlertsCard", () => {
  it("lists every non-guard source from the registry", async () => {
    render(<AlertsCard workspaceId="w" isAdmin filter={null} />)
    expect(await screen.findByText("Upstream 5xx")).toBeTruthy()
    expect(screen.getByText("Collector stale")).toBeTruthy()
    expect(screen.queryByText("Guard rules")).toBeNull()
  })

  it("filters to one profile and scopes new channels to it", async () => {
    render(<AlertsCard workspaceId="w" isAdmin filter={{ sourceType: "gateway", sourceId: "p-1" }} {...VAULT} />)
    expect(await screen.findByText("Upstream 5xx")).toBeTruthy()
    expect(screen.queryByText("Collector stale")).toBeNull()
    expect(list).toHaveBeenCalledWith(expect.anything(), "w", { source_type: "gateway", source_id: "p-1" })

    fireEvent.click(screen.getByText("+ Add channel"))
    fireEvent.change(screen.getByLabelText("Channel target"), { target: { value: "ops" } })
    fireEvent.change(screen.getByLabelText("Threshold per minute"), { target: { value: "10" } })
    fireEvent.click(screen.getByText("Save"))
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][2]).toMatchObject({
      source_type: "gateway", source_id: "p-1", event_type: "upstream_5xx",
      channel_type: "slack", channel_ref: "ops", threshold_per_min: 10,
      integration_id: "int-prod",
    })
  })

  it("uses the Slack credential of the Vault selected on the page", async () => {
    render(<AlertsCard workspaceId="w" isAdmin filter={{ sourceType: "audit_feed", sourceId: null }} {...VAULT} selectedEnvId="env-staging" />)
    fireEvent.click(await screen.findByText("+ Add channel"))
    fireEvent.change(screen.getByLabelText("Channel target"), { target: { value: "#sec-alerts" } })
    fireEvent.click(screen.getByText("Save"))
    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][2]).toMatchObject({ channel_type: "slack", channel_ref: "sec-alerts", integration_id: "int-staging" })
  })

  it("blocks Slack channels until a Vault exists", async () => {
    render(<AlertsCard workspaceId="w" isAdmin filter={{ sourceType: "audit_feed", sourceId: null }} />)
    fireEvent.click(await screen.findByText("+ Add channel"))
    fireEvent.change(screen.getByLabelText("Channel target"), { target: { value: "ops" } })
    expect((screen.getByText("Save") as HTMLButtonElement).disabled).toBe(true)
  })

  it("hides add controls for non-admins", async () => {
    render(<AlertsCard workspaceId="w" isAdmin={false} filter={null} />)
    await screen.findByText("Upstream 5xx")
    expect(screen.queryByText("+ Add channel")).toBeNull()
  })

  describe("Vault pickers", () => {
    const ENTRIES = {
      slack: [],
      pagerduty: [
        { id: "pd-prod", handle: "pagerduty", environment_id: "env-prod", environment_name: "Production" },
        { id: "pd-staging", handle: "pagerduty", environment_id: "env-staging", environment_name: "Staging" },
      ],
      webhook: [{ id: "wh-prod", handle: "webhook", environment_id: "env-prod", environment_name: "Production" }],
      email: [{ id: "em-staging", handle: "email", environment_id: "env-staging", environment_name: "Staging" }],
    }
    const open = async (envId: string) => {
      render(<AlertsCard workspaceId="w" isAdmin filter={{ sourceType: "audit_feed", sourceId: null }}
        {...VAULT} vaultEntries={ENTRIES} selectedEnvId={envId} />)
      fireEvent.click(await screen.findByText("+ Add channel"))
    }

    it("PagerDuty picks the selected Vault's entry instead of a typed key", async () => {
      await open("env-staging")
      fireEvent.change(screen.getByLabelText("Channel type"), { target: { value: "pagerduty" } })
      expect(screen.queryByLabelText("Channel target")).toBeNull()
      fireEvent.click(screen.getByText("Save"))
      await waitFor(() => expect(create).toHaveBeenCalled())
      expect(create.mock.calls[0][2]).toMatchObject({ channel_type: "pagerduty", integration_id: "pd-staging", channel_ref: "" })
    })

    it("Webhook uses its Vault entry", async () => {
      await open("env-prod")
      fireEvent.change(screen.getByLabelText("Channel type"), { target: { value: "webhook" } })
      fireEvent.click(screen.getByText("Save"))
      await waitFor(() => expect(create).toHaveBeenCalled())
      expect(create.mock.calls[0][2]).toMatchObject({ channel_type: "webhook", integration_id: "wh-prod", channel_ref: "" })
    })

    it("Email asks for the recipient and optionally a Vault entry", async () => {
      await open("env-staging")
      fireEvent.change(screen.getByLabelText("Channel type"), { target: { value: "email" } })
      fireEvent.change(screen.getByLabelText("Channel target"), { target: { value: "ops@example.com" } })
      fireEvent.change(screen.getByLabelText("Email Vault entry"), { target: { value: "em-staging" } })
      fireEvent.click(screen.getByText("Save"))
      await waitFor(() => expect(create).toHaveBeenCalled())
      expect(create.mock.calls[0][2]).toMatchObject({ channel_type: "email", integration_id: "em-staging", channel_ref: "ops@example.com" })
    })

    it("shows the add-in-Vault link and blocks save when the Vault has no entry", async () => {
      await open("env-staging")
      fireEvent.change(screen.getByLabelText("Channel type"), { target: { value: "webhook" } })
      expect(screen.getByText(/No Webhook entry — add one in Settings → Vault/)).toBeTruthy()
      expect((screen.getByText("Save") as HTMLButtonElement).disabled).toBe(true)
    })

    it("shows the Vault environment and the typed-key hint on rows", async () => {
      list.mockResolvedValue({ workspace_id: "w", channels: [
        { id: "a", source_type: "audit_feed", source_id: null, event_type: "collector_stale", channel_type: "pagerduty",
          integration_id: "pd-prod", channel_ref: "vault:pagerduty", vault_handle: "pagerduty", environment_name: "Production",
          legacy_ref: false, enabled: true, dedupe_window_sec: 0, threshold_per_min: null, managed_elsewhere: false },
        { id: "b", source_type: "audit_feed", source_id: null, event_type: "collector_stale", channel_type: "webhook",
          integration_id: null, channel_ref: "https://example.com/…", legacy_ref: true, enabled: true, dedupe_window_sec: 0,
          threshold_per_min: null, managed_elsewhere: false },
      ] })
      render(<AlertsCard workspaceId="w" isAdmin filter={null} {...VAULT} vaultEntries={ENTRIES} />)
      expect(await screen.findByText(/· Production/)).toBeTruthy()
      expect(screen.getByText(/Typed key — move to Vault/)).toBeTruthy()
      expect(screen.getAllByText(/Typed key — move to Vault/)).toHaveLength(1)
    })
  })
})
