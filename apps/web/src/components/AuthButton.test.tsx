import { afterEach, expect, it, vi } from "vitest"
import { cleanup, render, screen } from "@testing-library/react"
import AuthButton from "./AuthButton"

const profile = vi.hoisted(() => ({ user: { fullName: "Console admin", primaryEmailAddress: null as null | { emailAddress: string } } }))
vi.mock("@/lib/auth/runtime", () => ({ authEnabled: () => true }))
vi.mock("@/lib/auth/client", () => ({ useUser: () => profile, useClerk: () => ({ signOut: vi.fn() }) }))
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock("@/lib/WorkspaceContext", () => ({ useWorkspace: () => ({ activeWorkspace: null }) }))
afterEach(() => { cleanup(); profile.user.primaryEmailAddress = null })

it("shows a generic account icon when the shared profile has no email", () => {
  render(<AuthButton />)
  const button = screen.getByRole("button", { name: "Account menu for Console admin" })
  expect(button.querySelector("svg")).not.toBeNull()
  expect(button.textContent).not.toContain("?")
})

it("preserves email initials when provided by the shared profile", () => {
  profile.user.primaryEmailAddress = { emailAddress: "admin@example.test" }
  render(<AuthButton />)
  expect(screen.getByRole("button", { name: "Account menu for Console admin" }).textContent).toBe("A")
})
