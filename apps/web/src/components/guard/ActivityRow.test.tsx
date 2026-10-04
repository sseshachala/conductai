import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
vi.mock("@/components/glens/AskLensLink", () => ({ AskLensLink: () => null }))
vi.mock("./SessionSpend", () => ({ SessionSpend: () => null }))
import { ActivityRow, type AuditEvent } from "./ActivityRow"

afterEach(cleanup)
const ev: AuditEvent = {
  id: "request-a", ts: "2026-10-03T12:00:00Z", user_email: "alice@example.test", ai_tool: "codex",
  tool_call: "openai/v1/responses", input_summary: "fixture request", decision: "allowed", rule_id: null,
  agent_identity_id: "44444444-1111-4111-8111-111111111111",
  routing_meta: { gateway_profile_id: "profile-a", gateway_profile: "cond-abcdefgh-coding" },
}

it.each(["allowed", "blocked"])("shows token identity and Gateway profile on a %s request", decision => {
  const view = render(<ActivityRow ev={{ ...ev, decision }} />)
  fireEvent.click(view.container.firstElementChild!)
  expect(screen.getByText("Agent ID")).toBeInTheDocument()
  expect(screen.getByRole("link", { name: ev.agent_identity_id! })).toHaveAttribute(
    "href", "/agent-identity?tab=identities&id=" + ev.agent_identity_id,
  )
  expect(screen.getByRole("link", { name: "cond-abcdefgh-coding" })).toHaveAttribute(
    "href", "/proxy/gateway-profiles?select=profile-a",
  )
})

it("does not invent identity or profile attribution for old events", () => {
  const view = render(<ActivityRow ev={{ ...ev, agent_identity_id: null, routing_meta: null }} />)
  fireEvent.click(view.container.firstElementChild!)
  expect(screen.queryByText("Agent ID")).toBeNull()
  expect(screen.queryByText("Gateway profile")).toBeNull()
})
