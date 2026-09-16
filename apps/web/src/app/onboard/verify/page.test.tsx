import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import VerifyTrialPage from "./page"

afterEach(() => vi.unstubAllGlobals())

it("does not redeem on navigation and strips the challenge from the URL", async () => {
  window.history.replaceState(null, "", "/onboard/verify?ct=test-challenge")
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "new", agent_token: "never-render-this" }) })
  vi.stubGlobal("fetch", fetcher)
  render(<VerifyTrialPage />)
  expect(window.location.search).toBe("")
  expect(fetcher).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Verify email" }))
  await screen.findByText("Your trial workspace is ready")
  expect(fetcher).toHaveBeenCalledOnce()
  expect(document.body.textContent).not.toContain("never-render-this")
})

it("explains expired links without automatically retrying redemption", async () => {
  window.history.replaceState(null, "", "/onboard/verify?ct=expired-test")
  const fetcher = vi.fn().mockResolvedValue({ ok: false, status: 410 })
  vi.stubGlobal("fetch", fetcher)
  render(<VerifyTrialPage />)
  fireEvent.click(screen.getByRole("button", { name: "Verify email" }))
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("expired or was already used"))
  expect(fetcher).toHaveBeenCalledOnce()
})
