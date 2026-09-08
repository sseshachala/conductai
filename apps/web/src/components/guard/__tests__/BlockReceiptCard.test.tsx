import { describe, it, expect } from "vitest"
import { render } from "@testing-library/react"
import { screen } from "@testing-library/dom"

import { BlockReceiptCard } from "../BlockReceiptCard"
import type { BlockReceipt } from "@/lib/api/guard"

const receipt: BlockReceipt = {
  receipt_id: "01JAX00000000000000000000",
  ts: "2026-09-07T21:00:00Z",
  decision: "blocked",
  rule_id: "pii.customer_email_in_prompt",
  rule_message: "Customer email detected in prompt",
  provider: "anthropic",
  model: "claude-sonnet-4-5",
  ai_tool: "cursor",
  input_summary: "please normalize alice@example.com",
  evaluated_rules: [{ id: "pii.customer_email_in_prompt" }],
  defense_score: 90,
  conductai_run_id: null,
  hook_session_id: null,
}

describe("BlockReceiptCard", () => {
  it("renders rule + prompt summary + 4 CTAs", () => {
    render(<BlockReceiptCard receipt={receipt} />)
    expect(screen.getByText("Customer email detected in prompt")).toBeTruthy()
    expect(screen.getByText(/please normalize/)).toBeTruthy()
    // 4 pre-canned prompts
    expect(screen.getByText("Why did this block? →")).toBeTruthy()
    expect(screen.getByText("Show me the rule →")).toBeTruthy()
    expect(screen.getByText("What would have allowed it? →")).toBeTruthy()
    expect(screen.getByText("Draft an exception →")).toBeTruthy()
  })

  it("workspace mode links CTA straight to /lens?q=...", () => {
    render(<BlockReceiptCard receipt={receipt} mode="workspace" />)
    const link = screen.getByText("Why did this block? →").closest("a") as HTMLAnchorElement
    expect(link).toBeTruthy()
    expect(link.getAttribute("href")).toMatch(/^\/lens\?q=/)
    // Question includes the rule id so Lens has enough to answer
    expect(decodeURIComponent(link.getAttribute("href") ?? "")).toContain("pii.customer_email_in_prompt")
    expect(decodeURIComponent(link.getAttribute("href") ?? "")).toContain(receipt.receipt_id)
  })

  it("public mode routes CTA through /sign-up?next=/lens?q=... for anonymous trial users", () => {
    render(<BlockReceiptCard receipt={receipt} mode="public" />)
    const link = screen.getByText("Why did this block? →").closest("a") as HTMLAnchorElement
    expect(link.getAttribute("href")).toMatch(/^\/sign-up\?next=/)
    const href = decodeURIComponent(link.getAttribute("href") ?? "")
    expect(href).toContain("/lens?q=")
    expect(href).toContain("pii.customer_email_in_prompt")
  })
})
