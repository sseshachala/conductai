import { describe, expect, it } from "vitest"
import { isApiRequest } from "../../../e2e/network"

const web = "http://localhost:3000"
const api = "http://127.0.0.1:8000"

describe("smoke API request classification", () => {
  it("checks API calls without treating Next.js redirects, RSC, or server actions as API failures", () => {
    expect(isApiRequest(`${api}/guard/events`, web, api)).toBe(true)
    expect(isApiRequest(`${web}/api/auth/session`, web, api)).toBe(true)
    expect(isApiRequest(`${web}/theguard?_rsc=fixture`, web, api)).toBe(false)
    expect(isApiRequest(`${web}/accept-invite`, web, api)).toBe(false)
    expect(isApiRequest("https://external.example/api/chat", web, api)).toBe(false)
  })

  it("supports same-origin on-prem API prefixes without accepting lookalike paths", () => {
    expect(isApiRequest(`${web}/api/backend/projects`, web, "/api/backend")).toBe(true)
    expect(isApiRequest(`${web}/theguard`, web, "/api/backend")).toBe(false)
    expect(isApiRequest(`${web}/backend/projects`, web, "/backend")).toBe(true)
    expect(isApiRequest(`${web}/backend-other`, web, "/backend")).toBe(false)
  })
})
