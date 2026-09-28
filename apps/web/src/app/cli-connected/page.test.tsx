import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import CliConnectedPage, { metadata } from "./page"

describe("CLI login confirmation", () => {
  it("confirms sign-in and directs users back to their terminal", () => {
    render(<CliConnectedPage />)
    expect(screen.getByRole("heading", { name: "You're signed in." })).toBeInTheDocument()
    expect(screen.getByText("You can close this tab and return to your terminal.")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Open Conduct/ })).toHaveAttribute(
      "href", "https://app.conductai.ai/theguard",
    )
  })

  it("does not index the confirmation or forward referrers", () => {
    expect(metadata.robots).toEqual({ index: false, follow: false })
    expect(metadata.referrer).toBe("no-referrer")
  })
})
