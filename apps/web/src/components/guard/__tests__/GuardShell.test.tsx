import { describe, it, expect, vi } from "vitest"
import { render } from "@testing-library/react"
import { screen } from "@testing-library/dom"
import type { GuardRole } from "@/hooks/useGuardRole"
import { GuardShell } from "../GuardShell"
import { GUARD_SECTIONS } from "@/lib/navigation/guardSections"

vi.mock("next/navigation", () => ({
  usePathname: () => "/theguard",
}))

const mockUseGuardRole = vi.fn<() => { role: GuardRole | null; permissions: unknown; loading: boolean }>()
vi.mock("@/hooks/useGuardRole", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useGuardRole")>("@/hooks/useGuardRole")
  return { ...actual, useGuardRole: () => mockUseGuardRole() }
})

function setRole(role: GuardRole | null) {
  mockUseGuardRole.mockReturnValue({ role, permissions: {}, loading: false })
}

describe("GuardShell — six-section IA", () => {
  it("renders every GUARD_SECTIONS entry as a nav link", () => {
    setRole(null)
    render(<GuardShell>content</GuardShell>)
    for (const s of GUARD_SECTIONS) {
      expect(screen.getByRole("link", { name: s.label })).toBeInTheDocument()
    }
  })

  it("renders children in the content column", () => {
    setRole(null)
    render(<GuardShell>hello body</GuardShell>)
    expect(screen.getByText("hello body")).toBeInTheDocument()
  })
})

describe("GuardShell — admin cluster", () => {
  it("hides Compliance and Settings when role is null (loading)", () => {
    setRole(null)
    render(<GuardShell>content</GuardShell>)
    expect(screen.queryByRole("link", { name: "Compliance" })).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument()
  })

  it("shows Compliance for security", () => {
    setRole("security")
    render(<GuardShell>content</GuardShell>)
    expect(screen.getByRole("link", { name: "Compliance" })).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument()
  })

  it("shows Compliance and Settings for admin", () => {
    setRole("admin")
    render(<GuardShell>content</GuardShell>)
    expect(screen.getByRole("link", { name: "Compliance" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument()
  })

  it("hides both from developer", () => {
    setRole("developer")
    render(<GuardShell>content</GuardShell>)
    expect(screen.queryByRole("link", { name: "Compliance" })).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument()
  })

  it("hides both from viewer", () => {
    setRole("viewer")
    render(<GuardShell>content</GuardShell>)
    expect(screen.queryByRole("link", { name: "Compliance" })).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument()
  })
})

describe("GuardShell — collapse toggle", () => {
  it("renders the collapse toggle button", () => {
    setRole("admin")
    render(<GuardShell>content</GuardShell>)
    expect(screen.getByRole("button", { name: /collapse guard nav/i })).toBeInTheDocument()
  })
})
