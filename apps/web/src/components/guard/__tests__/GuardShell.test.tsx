import { describe, it, expect, vi, beforeEach } from "vitest"
import { render } from "@testing-library/react"
import { screen } from "@testing-library/dom"
import type { GuardRole } from "@/hooks/useGuardRole"
import { GuardShell, GUARD_TABS } from "../GuardShell"

vi.mock("next/navigation", () => ({
  usePathname: () => "/theguard",
}))

const mockUseGuardRole = vi.fn<() => { role: GuardRole | null }>()
vi.mock("@/hooks/useGuardRole", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useGuardRole")>(
    "@/hooks/useGuardRole",
  )
  return {
    ...actual,
    useGuardRole: () => mockUseGuardRole(),
  }
})

function setRole(role: GuardRole | null) {
  mockUseGuardRole.mockReturnValue({ role })
}

const PUBLIC_LABELS = ["Activity", "Spend", "Policies", "Approvals", "Discovery"]

describe("GUARD_TABS static shape", () => {
  it("restricts Compliance to admin + security", () => {
    const compliance = GUARD_TABS.find(t => t.label === "Compliance")
    expect(compliance?.roles).toEqual(["admin", "security"])
  })

  it("restricts Settings to admin only", () => {
    const settings = GUARD_TABS.find(t => t.label === "Settings")
    expect(settings?.roles).toEqual(["admin"])
  })

  it("marks public tabs (Activity, Spend, Policies, Approvals, Discovery) with no role gate", () => {
    for (const label of PUBLIC_LABELS) {
      const tab = GUARD_TABS.find(t => t.label === label)
      expect(tab?.roles).toBeUndefined()
    }
  })
})

describe("GuardShell nav rendering by role", () => {
  beforeEach(() => {
    mockUseGuardRole.mockReset()
  })

  it("shows all 5 public tabs regardless of role (admin case)", () => {
    setRole("admin")
    render(<GuardShell>content</GuardShell>)
    for (const label of PUBLIC_LABELS) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument()
    }
  })

  it("shows all 5 public tabs when role is null (unauthenticated / loading)", () => {
    setRole(null)
    render(<GuardShell>content</GuardShell>)
    for (const label of PUBLIC_LABELS) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument()
    }
  })

  it("shows Compliance for admin", () => {
    setRole("admin")
    render(<GuardShell>content</GuardShell>)
    expect(screen.getByRole("link", { name: "Compliance" })).toBeInTheDocument()
  })

  it("shows Compliance for security", () => {
    setRole("security")
    render(<GuardShell>content</GuardShell>)
    expect(screen.getByRole("link", { name: "Compliance" })).toBeInTheDocument()
  })

  it("hides Compliance from developer", () => {
    setRole("developer")
    render(<GuardShell>content</GuardShell>)
    expect(screen.queryByRole("link", { name: "Compliance" })).not.toBeInTheDocument()
  })

  it("hides Compliance from viewer", () => {
    setRole("viewer")
    render(<GuardShell>content</GuardShell>)
    expect(screen.queryByRole("link", { name: "Compliance" })).not.toBeInTheDocument()
  })

  it("hides Compliance when role is null", () => {
    setRole(null)
    render(<GuardShell>content</GuardShell>)
    expect(screen.queryByRole("link", { name: "Compliance" })).not.toBeInTheDocument()
  })

  it("shows Settings for admin only", () => {
    setRole("admin")
    render(<GuardShell>content</GuardShell>)
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument()
  })

  it("hides Settings from security", () => {
    setRole("security")
    render(<GuardShell>content</GuardShell>)
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument()
  })

  it("hides Settings from developer", () => {
    setRole("developer")
    render(<GuardShell>content</GuardShell>)
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument()
  })

  it("hides Settings from viewer", () => {
    setRole("viewer")
    render(<GuardShell>content</GuardShell>)
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument()
  })

  it("renders children inside the shell", () => {
    setRole("admin")
    render(<GuardShell>hello body</GuardShell>)
    expect(screen.getByText("hello body")).toBeInTheDocument()
  })
})
