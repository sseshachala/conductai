import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { renderMd } from "./glensMarkdown"
import { fmtDate } from "@/lib/glens/formatters"
import { LensResultsLayout } from "./LensResultsLayout"
import { ResultTableView } from "./ResultTableView"

afterEach(cleanup)
it("keeps columns and citations accessible and expands without losing the table", () => {
  render(<LensResultsLayout><input aria-label="Chat" defaultValue="Unsaved question" />{renderMd("| Started | Workflow | Link |\n| --- | --- | --- |\n| 2026-09-26T10:30:00Z | long_workflow_name | [View](/runs/one) |")}</LensResultsLayout>)
  const region = screen.getByRole("region", { name: "Result table" })
  expect(region).toHaveStyle({ overflowX: "auto" })
  expect(screen.getByRole("link", { name: "View" })).toHaveAttribute("href", "/runs/one")
  const expand = screen.getByRole("button", { name: "Expand table" })
  fireEvent.click(expand)
  expect(screen.getByRole("complementary", { name: "Expanded result table" })).toBeVisible()
  expect(screen.queryByRole("dialog")).toBeNull()
  expect(screen.getByRole("textbox", { name: "Chat" })).toBeEnabled()
  expect(screen.getByRole("button", { name: "Close results pane" })).toHaveFocus()
  fireEvent.keyDown(screen.getByRole("button", { name: "Close results pane" }), { key: "Escape" })
  expect(screen.queryByRole("complementary")).toBeNull()
  expect(screen.getByRole("textbox", { name: "Chat" })).toHaveValue("Unsaved question")
  expect(expand).toHaveFocus()
  expect(within(region).getByText("long_workflow_name")).toBeVisible()
})

it("refreshes the selected table and replaces it when another table opens", () => {
  const view = (value: string) => <LensResultsLayout><ResultTableView><p>{value}</p></ResultTableView><ResultTableView><p>Second result</p></ResultTableView></LensResultsLayout>
  const mounted = render(view("First result"))
  fireEvent.click(screen.getAllByRole("button", { name: "Expand table" })[0])
  mounted.rerender(view("Updated result"))
  expect(within(screen.getByRole("complementary")).getByText("Updated result")).toBeVisible()
  fireEvent.click(screen.getAllByRole("button", { name: "Expand table" })[1])
  expect(screen.getAllByRole("complementary")).toHaveLength(1)
  expect(within(screen.getByRole("complementary")).getByText("Second result")).toBeVisible()
})

it("closes stale results on session changes and restores the drawer width", () => {
  const changed = vi.fn()
  const view = (session: string) => <LensResultsLayout resetKey={session} onExpandedChange={changed}><ResultTableView><p>Evidence</p></ResultTableView></LensResultsLayout>
  const mounted = render(view("one"))
  fireEvent.click(screen.getByRole("button", { name: "Expand table" }))
  expect(changed).toHaveBeenLastCalledWith(true)
  mounted.rerender(view("two"))
  expect(screen.queryByRole("complementary")).toBeNull()
  expect(changed).toHaveBeenLastCalledWith(false)
})
it("formats the same instant in explicit UTC without inventing missing timezones", () => {
  expect(fmtDate("2026-09-26T05:30:00-05:00")).toBe("26 Sept 2026 10:30:00 UTC")
  expect(fmtDate("2026-09-26")).toBe("2026-09-26")
  expect(fmtDate("unknown")).toBe("unknown")
})
