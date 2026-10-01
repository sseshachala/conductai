import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { SessionUsageDetails, type SessionUsageEvidence } from "./SessionUsageDetails"

const evidence: SessionUsageEvidence = {
  source: "client_reported", observed_at: "2026-10-01T12:00:00Z",
  reconciliation: "unreconciled", budget_eligible: false,
  pricing_version: "test-v1", cost_status: "unpriced", estimated_microdollars: null,
  slices: [{ model: null, provider: null, uncached_input_tokens: 100,
    cache_read_tokens: 20, cache_write_tokens: 0, output_tokens: 30 }],
}

describe("session usage", () => {
  it("keeps unknown cost and model explicit", () => {
    render(<SessionUsageDetails value={evidence} />)
    expect(screen.getByText(/Cost unavailable/)).toBeTruthy()
    expect(screen.getByText("Model unavailable")).toBeTruthy()
    expect(screen.getByText(/Excluded from budgets/)).toBeTruthy()
    expect(screen.queryByText(/\$0/)).toBeNull()
  })
  it("labels estimates with provenance, not bills", () => {
    render(<SessionUsageDetails value={{ ...evidence, cost_status: "estimated", estimated_microdollars: 123 }} />)
    expect(screen.getByText(/Estimated cost: \$0.000123/)).toBeTruthy()
    expect(screen.getAllByText(/Pricing test-v1/).length).toBeGreaterThan(0)
  })
})
