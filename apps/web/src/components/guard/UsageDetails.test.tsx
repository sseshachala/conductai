import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { UsageDetails, UsageDetailsView, type UsageData } from "./UsageDetails"
import { formatTokensUsed, usageSourceLabel, usageStatusLabel } from "./common/formatTokens"

const state = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch, workspaceId: "workspace" }) }))

const attempt = (over: object) => ({
  id: "a", attempt_ordinal: 1, provider: "anthropic", model: "claude-x", execution_outcome: "success",
  usage_completeness: "complete", total_input_tokens: 10, total_output_tokens: 5,
  calculated_cost_microdollars: 1500, ...over,
})
const base = (over: Partial<UsageData>): UsageData => ({
  event_id: "e",
  row: { input_tokens: 10, output_tokens: 5, source: "provider", status: "complete", cost_usd: 0.0015 },
  attempts: [], totals: null, coverage: null, ...over,
})
const ok = (v: number | null) => ({ value: v, status: "complete" as const })

describe("usage formatting", () => {
  it("distinguishes null from a known zero", () => {
    expect(formatTokensUsed(null, null)).toBeNull()
    expect(formatTokensUsed(0, 0)).toBe("0 in / 0 out")
    expect(formatTokensUsed(12, null)).toBe("12 in / — out")
  })
  it("labels sources and statuses", () => {
    expect(usageSourceLabel("estimated")).toBe("Estimated")
    expect(usageSourceLabel("client_reported")).toBe("Client-reported")
    expect(usageSourceLabel("provider")).toBe("Provider-reported")
    expect(usageStatusLabel("no_upstream")).toBe("No upstream call")
    expect(usageStatusLabel("complete")).toBeNull()
    expect(usageStatusLabel(null)).toBeNull()
  })
})

describe("usage details", () => {
  it("renders a known zero as 0 and unknown as a dash", () => {
    render(<UsageDetailsView data={base({
      row: { input_tokens: 0, output_tokens: null, source: "provider", status: "partial", cost_usd: null },
    })} />)
    expect(screen.getByText(/0 in \/ — out/)).toBeTruthy()
    expect(screen.getByText("Partial")).toBeTruthy()
  })
  it("labels estimates", () => {
    render(<UsageDetailsView data={base({
      row: { input_tokens: 40, output_tokens: null, source: "estimated", status: "no_upstream", cost_usd: null },
    })} />)
    expect(screen.getByText("Estimated")).toBeTruthy()
    expect(screen.getByText("No upstream call")).toBeTruthy()
  })
  it("shows partial totals when an attempt is unknown", () => {
    render(<UsageDetailsView data={base({
      attempts: [attempt({}), attempt({ id: "b", attempt_ordinal: 2, total_input_tokens: null, total_output_tokens: null, calculated_cost_microdollars: null, usage_completeness: "unavailable" })],
      totals: { input_tokens: { value: 10, status: "partial" }, output_tokens: { value: 5, status: "partial" }, calculated_cost_microdollars: { value: 1500, status: "partial" } },
    })} />)
    expect(screen.getAllByText("partial")).toHaveLength(3)
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3)
  })
  it("shows complete totals without a partial badge", () => {
    render(<UsageDetailsView data={base({
      attempts: [attempt({})],
      totals: { input_tokens: ok(10), output_tokens: ok(5), calculated_cost_microdollars: ok(1500) },
    })} />)
    expect(screen.queryByText("partial")).toBeNull()
  })
  it("renders a pending row without inventing zeros", async () => {
    state.fetch.mockReset().mockResolvedValue({ ok: true, json: async () => base({
      row: { input_tokens: null, output_tokens: null, source: null, status: "pending", cost_usd: null },
    }) })
    render(<UsageDetails eventId="event" />)
    await screen.findByText("Pending")
    expect(screen.getByText(/— in \/ — out/)).toBeTruthy()
    expect(screen.getByText("Source unknown")).toBeTruthy()
    expect(state.fetch.mock.calls[0][0]).toContain("/guard/events/event/usage?workspace_id=workspace")
  })
  it("surfaces fetch failure", async () => {
    state.fetch.mockReset().mockResolvedValue({ ok: false })
    render(<UsageDetails eventId="event" />)
    await screen.findByRole("alert")
  })
})
