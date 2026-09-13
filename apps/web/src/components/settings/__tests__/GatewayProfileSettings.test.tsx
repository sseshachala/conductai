import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import GatewayProfileSettings from "../GatewayProfileSettings"

const authFetch = vi.fn()
const listProfiles = vi.fn()
const listEnvironments = vi.fn()
const listCredentials = vi.fn()

vi.mock("@/hooks/useAuthFetch", () => ({
  useAuthFetch: () => ({ authFetch }),
}))

vi.mock("@/lib/api", () => ({
  guard: {
    gatewayProfiles: {
      list: (...args: unknown[]) => listProfiles(...args),
      create: vi.fn(),
      update: vi.fn(),
      validate: vi.fn(),
      push: vi.fn(),
    },
  },
  environments: { list: (...args: unknown[]) => listEnvironments(...args) },
  credentials: { byEnvironment: (...args: unknown[]) => listCredentials(...args) },
}))

describe("GatewayProfileSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listProfiles.mockResolvedValue([])
    listEnvironments.mockResolvedValue([{ id: "env-production", name: "Production" }])
    listCredentials.mockResolvedValue([{ handle: "anthropic", service: "anthropic" }])
  })

  it("shows only the user-facing Vault name in credential options", async () => {
    render(<GatewayProfileSettings workspaceId="workspace-1" isAdmin />)

    await waitFor(() => expect(screen.getByRole("option", { name: "Production" })).toBeInTheDocument())
    expect(screen.queryByText("Production · anthropic / anthropic")).not.toBeInTheDocument()
  })
})
