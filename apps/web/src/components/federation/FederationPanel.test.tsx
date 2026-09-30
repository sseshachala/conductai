import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { FederationPanel } from "./FederationPanel"
import { Overview } from "./types"

const authFetch = vi.fn()
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch }) }))
const overview: Overview = {
  connections: [], principals: [], bindings: [], grants: [], callers: [],
  actions: ["mcp.guard_check", "mcp.guard_check_prompt", "gateway.inference", "workflows.run"],
}
const response = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body })

describe("federation management", () => {
  beforeEach(() => authFetch.mockReset())

  const principal = { id: "principal", revision: 1, status: "active" as const,
    issuer: "https://identity.example", subject: "alice-subject", kind: "human" as const,
    display_name: "Alice", actions: ["mcp.guard_check_prompt"] }
  const binding = { id: "binding", revision: 1, status: "active" as const,
    caller_id: "caller", connection_id: "connection", actions: principal.actions }
  const grant = { id: "grant", revision: 1, status: "active" as const,
    binding_id: binding.id, principal_id: principal.id, actions: principal.actions,
    expires_at: "2099-01-01T00:00:00Z" }
  const populated: Overview = { ...overview, principals: [principal], bindings: [binding], grants: [grant],
    callers: [{ id: "caller", name: "Test caller" }] }

  it("edits and persists the principal name without changing identity", async () => {
    authFetch.mockResolvedValue(response(populated))
    render(<FederationPanel workspace="workspace" mode="delegation" />)
    fireEvent.click(await screen.findByRole("button", { name: "Edit Alice" }))
    expect(screen.queryByRole("button", { name: "Add principal" })).not.toBeInTheDocument()
    expect(screen.getByLabelText("Subject")).toBeDisabled()
    expect(screen.getByLabelText("Issuer")).toBeDisabled()
    fireEvent.change(screen.getByLabelText("Name (optional)"), { target: { value: "Alice Example" } })
    fireEvent.click(screen.getByRole("button", { name: "Save approval" }))
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith(expect.stringContaining("/principals/principal"), expect.objectContaining({ method: "PUT" })))
    const [, options] = authFetch.mock.calls.find(([, options]) => options?.method === "PUT")!
    expect(JSON.parse(options.body)).toMatchObject({ display_name: "Alice Example", subject: "alice-subject", expected_revision: 1 })
    expect(await screen.findByRole("button", { name: "Add principal" })).toBeVisible()
  })

  it.each([
    ["Principals", "Edit Alice", "Add principal"],
    ["Caller bindings", "Edit binding", "Add binding"],
    ["Grants", "Edit grant", "Add grant"],
  ])("hides add controls while editing %s and restores on cancel", async (tab, edit, add) => {
    authFetch.mockResolvedValue(response(populated))
    render(<FederationPanel workspace="workspace" mode="delegation" />)
    fireEvent.click(await screen.findByRole("tab", { name: tab }))
    fireEvent.click(screen.getByRole("button", { name: edit }))
    expect(screen.queryByRole("button", { name: add })).not.toBeInTheDocument()
    if (tab === "Grants") expect(screen.getByRole("option", { name: "Alice (alice-subject)" })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(screen.getByRole("button", { name: add })).toBeVisible()
  })

  it("supports unnamed legacy principals and hides add while creating", async () => {
    authFetch.mockResolvedValue(response({ ...overview, principals: [{ ...principal, display_name: null }] }))
    render(<FederationPanel workspace="workspace" mode="delegation" />)
    expect(await screen.findByRole("button", { name: "Edit alice-subject" })).toBeVisible()
    fireEvent.click(screen.getByRole("button", { name: "Add principal" }))
    expect(screen.getByLabelText("Name (optional)")).toHaveValue("")
    expect(screen.queryByRole("button", { name: "Add principal" })).not.toBeInTheDocument()
  })

  it("denies admin controls when the API denies access", async () => {
    authFetch.mockResolvedValue(response({ detail: "forbidden" }, 403))
    render(<FederationPanel workspace="workspace" mode="connections" />)
    expect(await screen.findByRole("alert")).toHaveTextContent("administrator")
    expect(screen.queryByRole("button", { name: "New connection" })).not.toBeInTheDocument()
  })

  it("creates a generic draft without product-specific configuration", async () => {
    authFetch.mockResolvedValue(response(overview))
    render(<FederationPanel workspace="workspace" mode="connections" />)
    fireEvent.click(await screen.findByRole("button", { name: "New connection" }))
    fireEvent.change(screen.getByLabelText("Connection name"), { target: { value: "Enterprise production" } })
    fireEvent.change(screen.getByLabelText("Issuer URL"), { target: { value: "https://issuer.example" } })
    fireEvent.change(screen.getByLabelText("Audience"), { target: { value: "conduct" } })
    fireEvent.change(screen.getByLabelText("JWKS URL"), { target: { value: "https://issuer.example/keys" } })
    fireEvent.click(screen.getByRole("button", { name: "Save" }))
    await waitFor(() => expect(authFetch).toHaveBeenCalledWith(expect.stringContaining("/federation/connections"), expect.objectContaining({ method: "POST" })))
    const [, options] = authFetch.mock.calls.find(([, options]) => options?.method === "POST")!
    expect(JSON.parse(options.body)).toMatchObject({ name: "Enterprise production", config: { status: "draft", integration_type: "generic" } })
    expect(await screen.findByRole("button", { name: "New connection" })).toBeVisible()
    expect(screen.getByRole("link", { name: "Manage principals and delegation" })).toBeVisible()
    expect(screen.queryByLabelText("Connection name")).not.toBeInTheDocument()
  })

  it("hides connection list controls while creating and restores them on cancel", async () => {
    authFetch.mockResolvedValue(response(overview))
    render(<FederationPanel workspace="workspace" mode="connections" />)
    fireEvent.click(await screen.findByRole("button", { name: "New connection" }))
    expect(screen.getByLabelText("Connection name")).toBeVisible()
    expect(screen.queryByRole("button", { name: "New connection" })).not.toBeInTheDocument()
    expect(screen.queryByText("No OIDC connections configured.")).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Manage principals and delegation" })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))
    expect(screen.getByRole("button", { name: "New connection" })).toBeVisible()
    expect(screen.getByText("No OIDC connections configured.")).toBeVisible()
    expect(screen.getByRole("link", { name: "Manage principals and delegation" })).toBeVisible()
    expect(screen.queryByLabelText("Connection name")).not.toBeInTheDocument()
  })

  it("retains edits and shows a refresh instruction on revision conflict", async () => {
    authFetch.mockImplementation((_url, options) => Promise.resolve(options ? response({ detail: "federation_revision_conflict" }, 409) : response(overview)))
    render(<FederationPanel workspace="workspace" mode="connections" />)
    fireEvent.click(await screen.findByRole("button", { name: "New connection" }))
    fireEvent.change(screen.getByLabelText("Connection name"), { target: { value: "Retained" } })
    fireEvent.submit(screen.getByRole("button", { name: "Save" }).closest("form")!)
    expect(await screen.findByRole("alert")).toHaveTextContent("Refresh before saving")
    expect(screen.getByLabelText("Connection name")).toHaveValue("Retained")
  })

  it("does not authorize an empty action set", async () => {
    authFetch.mockResolvedValue(response(overview))
    render(<FederationPanel workspace="workspace" mode="delegation" />)
    fireEvent.click(await screen.findByRole("button", { name: "Add principal" }))
    expect(screen.getByRole("button", { name: "Approve principal" })).toBeDisabled()
    fireEvent.click(screen.getByLabelText("gateway.inference"))
    expect(screen.getByRole("button", { name: "Approve principal" })).toBeEnabled()
  })

  it("does not display a previous workspace result after remount", async () => {
    let complete: (value: unknown) => void = () => {}
    authFetch.mockReturnValueOnce(new Promise(resolve => { complete = resolve }))
    const view = render(<FederationPanel key="first" workspace="first" mode="connections" />)
    authFetch.mockResolvedValue(response(overview))
    view.rerender(<FederationPanel key="second" workspace="second" mode="connections" />)
    await screen.findByText("No OIDC connections configured.")
    complete(response({ ...overview, connections: [{ name: "Foreign", id: "foreign", config: { status: "active" } }] }))
    await waitFor(() => expect(screen.queryByText("Foreign")).not.toBeInTheDocument())
  })
})
