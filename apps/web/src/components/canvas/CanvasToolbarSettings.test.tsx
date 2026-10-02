import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import CanvasToolbarSettings from "./CanvasToolbarSettings"

const state = vi.hoisted(() => ({
  prefs: { show_test_trigger: true, show_dry_run: false }, loading: false, update: vi.fn(),
}))
vi.mock("@/lib/PreferencesContext", () => ({ usePreferences: () => state }))
beforeEach(() => {
  vi.clearAllMocks()
  state.prefs = { show_test_trigger: true, show_dry_run: false }
  state.loading = false
})
afterEach(cleanup)

it("uses the saved workspace toolbar preferences", () => {
  state.prefs = { show_test_trigger: false, show_dry_run: true }
  render(<CanvasToolbarSettings />)
  expect(screen.getByRole("switch", { name: "Show Test Trigger button" })).toHaveAttribute("aria-checked", "false")
  expect(screen.getByRole("switch", { name: "Show Dry Run button" })).toHaveAttribute("aria-checked", "true")
})

it("updates only the selected toolbar preference", () => {
  const view = render(<CanvasToolbarSettings />)
  fireEvent.click(screen.getByRole("switch", { name: "Show Test Trigger button" }))
  expect(state.update).toHaveBeenLastCalledWith({ show_test_trigger: false })
  state.prefs = { show_test_trigger: false, show_dry_run: false }
  view.rerender(<CanvasToolbarSettings />)
  fireEvent.click(screen.getByRole("switch", { name: "Show Dry Run button" }))
  expect(state.update).toHaveBeenLastCalledWith({ show_dry_run: true })
})

it("does not expose editable preferences before loading completes", () => {
  state.loading = true
  render(<CanvasToolbarSettings />)
  expect(screen.getByRole("status")).toHaveTextContent("Loading preferences")
  expect(screen.queryByRole("switch")).toBeNull()
})

it("keeps viewer controls read-only", () => {
  render(<CanvasToolbarSettings readOnly />)
  for (const control of screen.getAllByRole("switch")) {
    expect(control).toBeDisabled()
    fireEvent.click(control)
  }
  expect(state.update).not.toHaveBeenCalled()
})
