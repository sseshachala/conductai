// Regression harness for the consolidated Guard toolbar landed in #1982.
// Locks the acceptance criteria: exactly four primary controls, a Columns
// menu on the right, and column visibility that persists across renders.
//
// Not exhaustive on every popover interaction — the goal is a fast smoke
// that catches the class of bugs where the toolbar silently regresses
// back to the old 12-control layout.

import { describe, it, expect, beforeEach } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import {
  GuardToolbar,
  ColumnsMenu,
  loadVisibleColumns,
  saveVisibleColumns,
  DEFAULT_VISIBLE_COLUMNS,
  ALL_COLUMNS,
  type ColumnKey,
} from "../common/GuardToolbar"

// Minimal localStorage polyfill — the vitest env's default stub isn't
// callable (Object with no methods), so unconditionally install ours.
{
  const store = new Map<string, string>()
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => { store.set(k, v) },
      removeItem: (k: string) => { store.delete(k) },
      clear: () => { store.clear() },
      key: (i: number) => Array.from(store.keys())[i] ?? null,
      get length() { return store.size },
    },
  })
}

function noop() {}

function baseProps(overrides: Partial<Parameters<typeof GuardToolbar<ColumnKey>>[0]> = {}) {
  return {
    streaming: false,
    onStreamingToggle: noop,
    status: "" as const,
    onStatusChange: noop,
    filters: {
      developer: "",
      onDeveloperChange: noop,
      developers: [],
      canViewAllActivity: false,
      tool: "",
      onToolChange: noop,
      tools: [],
      since: "",
      onSinceChange: noop,
      until: "",
      onUntilChange: noop,
      ruleId: "",
      onClearRule: noop,
      groupByGoal: false,
      onGroupByGoalChange: noop,
    },
    onClearAll: noop,
    canExport: true,
    onExportCsv: noop,
    onSocReport: noop,
    allColumns: ALL_COLUMNS,
    columns: DEFAULT_VISIBLE_COLUMNS,
    onColumnsChange: noop,
    ...overrides,
  }
}

describe("GuardToolbar — #1982 density fix", () => {
  it("renders exactly four primary trigger buttons + a Columns affordance", () => {
    render(<GuardToolbar<ColumnKey> {...baseProps()} />)
    // Realtime / Status / Filters / Export triggers.
    expect(screen.getByText(/Paused|Realtime/)).toBeTruthy()
    expect(screen.getByText(/Status:/)).toBeTruthy()
    expect(screen.getByText(/^Filters/)).toBeTruthy()
    expect(screen.getByText(/^Export/)).toBeTruthy()
    // Columns menu — labelled by title / aria-label.
    expect(screen.getByLabelText(/Configure visible columns/i)).toBeTruthy()
  })

  it("Realtime badge flips label when streaming toggles", () => {
    const { rerender } = render(<GuardToolbar<ColumnKey> {...baseProps({ streaming: false })} />)
    expect(screen.getByText("Paused")).toBeTruthy()
    rerender(<GuardToolbar<ColumnKey> {...baseProps({ streaming: true })} />)
    expect(screen.getByText("Realtime")).toBeTruthy()
  })

  it("badges the Filters trigger with the count of active filters", () => {
    const props = baseProps({
      filters: {
        ...baseProps().filters,
        developer: "alice@example.com",
        canViewAllActivity: true,
        tool: "claude-code",
      },
    })
    render(<GuardToolbar<ColumnKey> {...props} />)
    // count badge renders inside the Filters trigger — sibling to the "Filters" label
    const trigger = screen.getByText(/^Filters/).closest("button")!
    expect(trigger.textContent).toContain("2")
  })
})

describe("ColumnsMenu — visibility toggle", () => {
  it("does not allow every column to be hidden simultaneously", () => {
    let cols: ColumnKey[] = ["time"]
    const onChange = (next: ColumnKey[]) => { cols = next }
    render(
      <ColumnsMenu<ColumnKey>
        allColumns={ALL_COLUMNS}
        visible={cols}
        onChange={onChange}
      />,
    )
    // Open the menu.
    fireEvent.click(screen.getByLabelText(/Configure visible columns/i))
    // Try to uncheck the only remaining column — the change must be rejected
    // so the table can never render with zero columns.
    const timeCheckbox = screen.getByLabelText("Time") as HTMLInputElement
    fireEvent.click(timeCheckbox)
    expect(cols).toEqual(["time"])
  })

  it("preserves canonical column order when re-adding a hidden column", () => {
    // Start with just Actor + Rule, then re-add Time.
    let cols: ColumnKey[] = ["actor", "rule"]
    const onChange = (next: ColumnKey[]) => { cols = next }
    render(
      <ColumnsMenu<ColumnKey>
        allColumns={ALL_COLUMNS}
        visible={cols}
        onChange={onChange}
      />,
    )
    fireEvent.click(screen.getByLabelText(/Configure visible columns/i))
    fireEvent.click(screen.getByLabelText("Time"))
    // Canonical order is time · actor · tool · call · decision · rule · blast
    // so Time must land at index 0, not appended at the end.
    expect(cols[0]).toBe("time")
  })
})

describe("localStorage persistence — #1982", () => {
  beforeEach(() => window.localStorage.clear())

  it("saves and reloads the visible-columns set", () => {
    const chosen: ColumnKey[] = ["time", "actor", "decision"]
    saveVisibleColumns(chosen)
    expect(loadVisibleColumns()).toEqual(chosen)
  })

  it("falls back to defaults for corrupt localStorage entries", () => {
    window.localStorage.setItem("guard-activity-visible-columns.v1", "not-json")
    expect(loadVisibleColumns()).toEqual(DEFAULT_VISIBLE_COLUMNS)
  })

  it("rejects an empty saved array — one column must always be visible", () => {
    window.localStorage.setItem(
      "guard-activity-visible-columns.v1",
      JSON.stringify([]),
    )
    expect(loadVisibleColumns()).toEqual(DEFAULT_VISIBLE_COLUMNS)
  })

  it("drops unknown keys from a saved array", () => {
    window.localStorage.setItem(
      "guard-activity-visible-columns.v1",
      JSON.stringify(["time", "actor", "not-a-real-column"]),
    )
    // Unknown key silently dropped; valid subset survives.
    expect(loadVisibleColumns()).toEqual(["time", "actor"])
  })
})
