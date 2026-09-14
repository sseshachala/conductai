import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import GatewayProfileSettings from "../GatewayProfileSettings"

const authFetch = vi.fn()
const listProfiles = vi.fn()
const listEnvironments = vi.fn()
const createProfile = vi.fn()

vi.mock("@/hooks/useAuthFetch", () => ({
  useAuthFetch: () => ({ authFetch }),
}))

vi.mock("@/lib/api", () => ({
  guard: {
    gatewayProfiles: {
      list: (...args: unknown[]) => listProfiles(...args),
      create: (...args: unknown[]) => createProfile(...args),
      update: vi.fn(),
      validate: vi.fn(),
      push: vi.fn(),
    },
  },
  environments: { list: (...args: unknown[]) => listEnvironments(...args) },
}))

describe("GatewayProfileSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listProfiles.mockResolvedValue([])
    listEnvironments.mockResolvedValue([{ id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", name: "Production" }])
    createProfile.mockResolvedValue({ json: async () => ({ id: "gateway-1" }) })
  })

  it("stores the selected Vault as a canonical environment-scoped reference", async () => {
    render(<GatewayProfileSettings workspaceId="workspace-1" isAdmin />)

    const vault = await screen.findByRole("combobox", { name: "Vault" })
    fireEvent.change(vault, { target: { value: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" } })
    fireEvent.click(screen.getByRole("button", { name: "Save gateway" }))

    await waitFor(() => expect(createProfile).toHaveBeenCalled())
    expect(createProfile.mock.calls[0][2]).toMatchObject({
      credential_ref: "vault://aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/anthropic",
    })
    expect(screen.queryByText("Production · anthropic / anthropic")).not.toBeInTheDocument()
  })

  it("maps a legacy handle-only reference to the Default Vault", async () => {
    listProfiles.mockResolvedValue([{
      id: "gateway-1",
      name: "default",
      provider: "anthropic",
      protocol: "anthropic",
      credential_ref: "vault://anthropic",
      deployments: [],
    }])
    listEnvironments.mockResolvedValue([
      { id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", name: "Default" },
    ])

    render(<GatewayProfileSettings workspaceId="workspace-1" isAdmin />)

    await waitFor(() => expect(screen.getByRole("combobox", { name: "Vault" })).toHaveValue(
      "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    ))
  })
})
