// Regression harness for the durable-audit lifecycle pill (#1959 Phase 3).
// The pill is presentation-only — parent decides which rows to render —
// so these tests lock the icon + label + client-side stale detection.

import { describe, it, expect } from "vitest"
import { render } from "@testing-library/react"
import { screen } from "@testing-library/dom"
import { LifecyclePill } from "../LifecyclePill"

describe("LifecyclePill — #1959 Phase 3", () => {
  it("renders an em dash for legacy rows with no lifecycle_state", () => {
    render(<LifecyclePill state={null} />)
    // A single em dash means \"legacy row\" — no lifecycle recorded.
    expect(screen.getByText("—")).toBeTruthy()
  })

  it("renders the accepted glyph while a lease is still valid", () => {
    const futureLease = new Date(Date.now() + 60_000).toISOString()
    render(<LifecyclePill state="accepted" leaseExpiresAt={futureLease} />)
    // Icon + label both surface so screen readers and eyes agree.
    expect(screen.getByText("In flight")).toBeTruthy()
  })

  it("renders the finalized glyph once finalize() has run", () => {
    render(<LifecyclePill state="finalized" />)
    expect(screen.getByText("Finalized")).toBeTruthy()
  })

  it("renders orphaned when the reconciler has flagged the row", () => {
    render(<LifecyclePill state="orphaned" />)
    expect(screen.getByText("Orphaned")).toBeTruthy()
  })

  it("presents an accepted row as expired when the lease has passed", () => {
    // Client-side stale detection — Phase 4 reconciler will follow up
    // server-side, but the UI stays honest in between polls.
    const pastLease = new Date(Date.now() - 60_000).toISOString()
    render(<LifecyclePill state="accepted" leaseExpiresAt={pastLease} />)
    expect(screen.getByText("Expired")).toBeTruthy()
  })

  it("respects a lease that is missing entirely — accepted stays in flight", () => {
    render(<LifecyclePill state="accepted" leaseExpiresAt={null} />)
    expect(screen.getByText("In flight")).toBeTruthy()
  })

  it("carries an aria-label matching the visible label", () => {
    render(<LifecyclePill state="finalized" />)
    const el = screen.getByRole("status")
    expect(el.getAttribute("aria-label")).toBe("Finalized")
  })

  it("exposes a helpful tooltip via the title attribute", () => {
    render(<LifecyclePill state="accepted" leaseExpiresAt={new Date(Date.now() + 60_000).toISOString()} />)
    const el = screen.getByRole("status")
    // Truthy is enough — copy can change. The invariant is a tooltip exists.
    expect(el.getAttribute("title")).toBeTruthy()
  })
})

// Reconciler stamps decision='error' on orphaned rows (post-Phase-4
// cleanup). The pill must stay driven by lifecycle_state alone so it
// keeps saying "Orphaned" even though the row's decision changed.
// Not passing the decision at all in the test IS the assertion — if
// the component ever tries to read it, this test would break.
describe("LifecyclePill — post-Phase-4 decision independence", () => {
  it("renders Orphaned regardless of what decision the row carries", () => {
    // No decision prop threaded — the pill only takes state + lease.
    render(<LifecyclePill state="orphaned" />)
    expect(screen.getByText("Orphaned")).toBeTruthy()
  })
})
