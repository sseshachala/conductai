import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"
import { AttributionDetails } from "./AttributionDetails"

it("separates historical caller and acting principal without claiming current access", () => {
  render(<AttributionDetails value={{ caller_id: "service-caller", principal_id: "external-principal",
    grant_id: "grant", connection_id: "trust", mapping_version: "3", request_id: "request",
    evidence_expires_at: "2026-09-29T12:00:00Z" }} />)
  expect(screen.getByText("Calling integration")).toBeInTheDocument()
  expect(screen.getByText("Acting principal")).toBeInTheDocument()
  expect(screen.getByText("external-principal")).toBeInTheDocument()
  expect(screen.getByRole("link", { name: "service-caller" })).toHaveAttribute("href", "/agent-identity?tab=identities&id=service-caller")
  expect(screen.getByText(/Current authorization may differ/)).toBeInTheDocument()
})
