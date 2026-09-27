import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it } from "vitest"
import { renderMd } from "./glensMarkdown"
import { LensResultsLayout } from "./LensResultsLayout"

afterEach(cleanup)

it("renders evidence headings and escaped identifiers instead of Markdown syntax", () => {
  render(<>{renderMd("## Recorded Conduct Activity\n\n### Decision\n\n**warned**: surface\\-codex\\-desktop\\-warn\\-exec\n\nProvider: cond\\-e785vpmb\\-gpt\\-4o")}</>)
  expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Recorded Conduct Activity")
  expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Decision")
  expect(screen.getByText(/surface-codex-desktop-warn-exec/)).toBeVisible()
  expect(screen.getByText(/cond-e785vpmb-gpt-4o/)).toBeVisible()
  expect(screen.getByText("warned").tagName).toBe("STRONG")
})

it("supports lists, inline code, fenced code and authorized citations", () => {
  render(<>{renderMd("1. First\n2. Second\n\n- Use `request_id`\n\n```json\n{\"ok\": true}\n```\n\n[Flight Recorder](/logs/guard?id=123)")}</>)
  expect(screen.getAllByRole("list")).toHaveLength(2)
  expect(screen.getByText("request_id").tagName).toBe("CODE")
  expect(screen.getByText('{"ok": true}').parentElement?.tagName).toBe("PRE")
  expect(screen.getByRole("link")).toHaveAttribute("href", "/logs/guard?id=123")
})

it("does not execute HTML, load images, or create unsafe links", () => {
  const { container } = render(<>{renderMd('<script>alert(1)</script>\n\n[bad](javascript:alert%281%29)\n\n![tracker](https://example.test/pixel)\n\n&lt;img src=x onerror=alert(1)&gt;')}</>)
  expect(container.querySelector("script, img, iframe")).toBeNull()
  expect(screen.queryByRole("link")).toBeNull()
  expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeVisible()
})

it("preserves expandable tables and escaped pipes in cells", () => {
  render(<LensResultsLayout>{renderMd("| Rule | Link |\n| --- | --- |\n| a\\|b | [View](/logs/guard?id=123) |")}</LensResultsLayout>)
  expect(screen.getByRole("button", { name: "Expand table" })).toBeVisible()
  expect(screen.getByRole("cell", { name: "a|b" })).toBeVisible()
  expect(screen.getByRole("link", { name: "View" })).toHaveAttribute("href", "/logs/guard?id=123")
})
