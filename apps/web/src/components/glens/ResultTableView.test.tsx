import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { renderMd } from "./glensMarkdown"
import { fmtDate } from "@/lib/glens/formatters"

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function(this: HTMLDialogElement) { this.setAttribute("open", "") })
  HTMLDialogElement.prototype.close = vi.fn(function(this: HTMLDialogElement) { this.removeAttribute("open"); this.dispatchEvent(new Event("close")) })
})
afterEach(cleanup)
it("keeps columns and citations accessible and expands without losing the table", () => {
  render(<>{renderMd("| Started | Workflow | Link |\n| --- | --- | --- |\n| 2026-09-26T10:30:00Z | long_workflow_name | [View](/runs/one) |")}</>)
  const region = screen.getByRole("region", { name: "Result table" })
  expect(region).toHaveStyle({ overflowX: "auto" })
  expect(screen.getByRole("link", { name: "View" })).toHaveAttribute("href", "/runs/one")
  const expand = screen.getByRole("button", { name: "Expand table" })
  fireEvent.click(expand)
  expect(screen.getByRole("dialog", { name: "Expanded result table" })).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Close expanded table" }))
  expect(screen.queryByRole("dialog")).toBeNull()
  expect(expand).toHaveFocus()
  expect(within(region).getByText("long_workflow_name")).toBeVisible()
})
it("formats the same instant in explicit UTC without inventing missing timezones", () => {
  expect(fmtDate("2026-09-26T05:30:00-05:00")).toBe("26 Sept 2026 10:30:00 UTC")
  expect(fmtDate("2026-09-26")).toBe("2026-09-26")
  expect(fmtDate("unknown")).toBe("unknown")
})
