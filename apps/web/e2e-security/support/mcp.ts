import { expect, type Page } from "@playwright/test"

/** Real HTTP probe shared by unfederated and future federated client journeys. */
export async function expectMcpInvocation(
  page: Page,
  endpoint: string,
  credential: string,
) {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${credential}`,
    Accept: "application/json, text/event-stream",
  }
  let nextId = 1
  async function request(method: string, params: Record<string, unknown>, notification = false) {
    let response
    try {
      response = await page.request.post(endpoint, {
        headers,
        data: { jsonrpc: "2.0", ...(notification ? {} : { id: nextId++ }), method, params },
        timeout: 30_000,
        maxRedirects: 0,
      })
    } catch {
      throw new Error(`MCP ${method} transport failed; credentials omitted`)
    }
    if (notification) {
      expect([202, 204].includes(response.status()), "MCP notification accepted").toBe(true)
    } else {
      expect(response.status(), `MCP ${method} status`).toBe(200)
    }
    const session = response.headers()["mcp-session-id"]
    if (session) headers["Mcp-Session-Id"] = session
    if (notification) return undefined
    let envelope
    try {
      const body = await response.text()
      if (response.headers()["content-type"]?.includes("text/event-stream")) {
        const messages = body.split(/\r?\n\r?\n/).filter(event => event.split(/\r?\n/).some(line => line.startsWith("data:")))
        const responses = messages.map(event => JSON.parse(event.split(/\r?\n/)
          .filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n")))
        envelope = responses.find(message => message.id === nextId - 1)
      } else {
        envelope = JSON.parse(body)
      }
    } catch {
      throw new Error(`MCP ${method} returned an invalid envelope; body omitted`)
    }
    expect(envelope?.id === nextId - 1, "MCP response correlation").toBe(true)
    expect(Boolean(envelope?.error), `MCP ${method} protocol error`).toBe(false)
    return envelope.result
  }

  const initialized = await request("initialize", {
    protocolVersion: "2025-03-26",
    capabilities: {}, clientInfo: { name: "conduct-identity-compatibility", version: "1.0" },
  })
  expect(typeof initialized?.protocolVersion === "string").toBe(true)
  headers["MCP-Protocol-Version"] = initialized.protocolVersion
  await request("notifications/initialized", {}, true)
  const listed = await request("tools/list", {})
  expect(Array.isArray(listed?.tools)).toBe(true)
  expect(listed.tools.some((tool: { name: string }) => tool.name === "guard_status")).toBe(true)
  const result = await request("tools/call", { name: "guard_status", arguments: {} })
  expect(result?.isError === true, "guard_status must succeed").toBe(false)
  expect(Array.isArray(result?.content) && result.content.length > 0).toBe(true)
}
