import { describe, it, expect, vi } from "vitest"
import { render } from "@testing-library/react"
import { screen } from "@testing-library/dom"
import { GuardShell } from "../GuardShell"
import { GUARD_SECTIONS } from "@/lib/navigation/guardSections"

vi.mock("next/navigation", () => ({
  usePathname: () => "/theguard",
}))

describe("GuardShell — six-section IA", () => {
  it("renders every GUARD_SECTIONS entry as a nav link", () => {
    render(<GuardShell>content</GuardShell>)
    for (const s of GUARD_SECTIONS) {
      expect(screen.getByRole("link", { name: s.label })).toBeInTheDocument()
    }
  })

  it("keeps Compliance and Settings OUT of the rail (palette-only)", () => {
    render(<GuardShell>content</GuardShell>)
    expect(screen.queryByRole("link", { name: "Compliance" })).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument()
  })

  it("renders children inside the shell", () => {
    render(<GuardShell>hello body</GuardShell>)
    expect(screen.getByText("hello body")).toBeInTheDocument()
  })
})
