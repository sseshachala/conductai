import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ToolExecutions, ToolExecutionsList } from "./ToolExecutions"

const state = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock("@/hooks/useAuthFetch", () => ({ useAuthFetch: () => ({ authFetch: state.fetch, workspaceId: "workspace" }) }))

describe("tool executions", () => {
  it("shows the empty state when no outcomes were reported", () => {
    render(<ToolExecutionsList data={{ correlation_ids: { call_abc: "9c4f3e21a7b0d8e1" }, executions: [] }} />)
    expect(screen.getByText("No execution outcomes reported yet")).toBeTruthy()
  })
  it("lists joined executions", () => {
    render(<ToolExecutionsList data={{ correlation_ids: {}, executions: [{
      correlation_id: "9c4f3e21a7b0d8e1", tool_call_id: "call_abc", tool_name: "send_email",
      execution_status: "success", duration_ms: 340, correlation_source: "reported", ts: null,
    }] }} />)
    expect(screen.getByText("send_email")).toBeTruthy()
    expect(screen.getByText("9c4f3e21a7b0d8e1")).toBeTruthy()
    expect(screen.getByText("340 ms")).toBeTruthy()
  })
  it("loads from the selected workspace", async () => {
    state.fetch.mockReset().mockResolvedValue({ ok: true, json: async () => ({ correlation_ids: {}, executions: [] }) })
    render(<ToolExecutions eventId="event" />)
    await screen.findByText("No execution outcomes reported yet")
    expect(state.fetch.mock.calls[0][0]).toContain("/guard/events/event/tool-executions?workspace_id=workspace")
  })
  it("surfaces fetch failure", async () => {
    state.fetch.mockReset().mockResolvedValue({ ok: false })
    render(<ToolExecutions eventId="event" />)
    await screen.findByRole("alert")
  })
})
