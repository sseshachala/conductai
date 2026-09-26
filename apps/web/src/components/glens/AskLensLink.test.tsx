import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { AskLensLink } from "./AskLensLink"
import { LENS_ENTRY_EVENT } from "@/lib/lens-entry"

vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ workspaceId: "11111111-1111-4111-8111-111111111111" }) }))
vi.mock("next/link", () => ({ default: ({ children, ...props }: React.ComponentProps<"a">) => <a {...props}>{children}</a> }))
afterEach(cleanup)

it("opens the embedded panel without navigation when the shell accepts context", () => {
  const accept = vi.fn((e: Event) => e.preventDefault())
  window.addEventListener(LENS_ENTRY_EVENT, accept)
  try {
    render(<AskLensLink kind="event" resourceId="22222222-2222-4222-8222-222222222222" />)
    expect(fireEvent.click(screen.getByRole("link"))).toBe(false)
    expect(accept).toHaveBeenCalledOnce()
  } finally { window.removeEventListener(LENS_ENTRY_EVENT, accept) }
})

it("preserves a real context URL and modified-click behavior", () => {
  const accept = vi.fn((e: Event) => e.preventDefault())
  window.addEventListener(LENS_ENTRY_EVENT, accept)
  try {
    render(<AskLensLink kind="run" resourceId="22222222-2222-4222-8222-222222222222" blockId="step-1" />)
    const link = screen.getByRole("link")
    expect(link.getAttribute("href")).toContain("/lens?context=")
    expect(fireEvent.click(link, { ctrlKey: true })).toBe(true)
    expect(accept).not.toHaveBeenCalled()
  } finally { window.removeEventListener(LENS_ENTRY_EVENT, accept) }
})
