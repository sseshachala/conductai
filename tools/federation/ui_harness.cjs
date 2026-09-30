// Browser-only fixture test. Does not contact a live workspace or identity provider.
const { createRequire } = require("node:module")
const path = require("node:path")
const { chromium } = createRequire(path.join(__dirname, "../../apps/web/package.json"))("@playwright/test")
const assert = require("node:assert/strict")
const origin = process.env.FEDERATION_WEB_URL || "http://127.0.0.1:3116"
const api = "http://127.0.0.1:59112"
const ws = "a1000000-0000-4000-8000-000000000001"
const connection = {
  id: "a1000000-0000-4000-8000-000000000002", integration_id: "a1000000-0000-4000-8000-000000000003",
  revision: 1, name: "Enterprise production", config: {
    status: "draft", integration_type: "generic", method: "oauth_access_token", issuer: "https://identity.example",
    audience: "conduct", jwks_uri: "https://identity.example/keys", discovery_uri: null,
    token_profile: "at+jwt", algorithms: ["RS256"], claim_mappings: [],
  },
}
const data = { connections: [connection], principals: [], bindings: [], grants: [], callers: [],
  actions: ["mcp.guard_check", "mcp.guard_check_prompt", "gateway.inference", "workflows.run"] }
const principal = { id: "a1000000-0000-4000-8000-000000000004", revision: 1,
  status: "active", issuer: connection.config.issuer, subject: "synthetic-alice-subject",
  display_name: "Alice Test", kind: "human", actions: ["mcp.guard_check_prompt"] }
data.principals.push(principal)
data.callers.push({ id: "a1000000-0000-4000-8000-000000000005", name: "Test caller" })
data.bindings.push({ id: "a1000000-0000-4000-8000-000000000006", revision: 1,
  caller_id: data.callers[0].id, connection_id: connection.id, status: "active", actions: principal.actions })
data.grants.push({ id: "a1000000-0000-4000-8000-000000000007", revision: 1,
  binding_id: data.bindings[0].id, principal_id: principal.id, status: "active",
  actions: principal.actions, expires_at: "2099-01-01T00:00:00Z" })

async function main() {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } })
    const errors = []
    page.on("pageerror", error => errors.push(error.message))
    await page.route(`${api}/**`, async route => {
      const path = new URL(route.request().url()).pathname
      let body = []
      if (path === "/projects") body = [{ id: ws, name: "Fixture workspace", is_approved: true }]
      else if (path.endsWith("/my-role")) body = { role: "admin" }
      else if (path.endsWith("/federation/overview")) body = data
      else if (path.endsWith("/federation/validate")) body = { signing_keys: 1, validated_at: new Date().toISOString() }
      else if (path.endsWith("/federation") && route.request().method() === "PUT") {
        const update = route.request().postDataJSON()
        assert.equal(update.expected_revision, connection.revision)
        connection.config = update.config; connection.revision += 1; body = connection
      }
      else if (path.endsWith(`/principals/${principal.id}`) && route.request().method() === "PUT") {
        const update = route.request().postDataJSON()
        assert.equal(update.subject, principal.subject)
        principal.display_name = update.display_name; principal.revision += 1; body = principal
      }
      else if (path.endsWith("/config")) body = { configured: false }
      else if (path.endsWith("/preferences")) body = {}
      await route.fulfill({ json: body })
    })
    await page.goto(`${origin}/agent-identity?tab=integrations&integration=oidc`)
    await page.getByRole("heading", { name: "OIDC connections" }).waitFor()
    await page.getByRole("cell").filter({ hasText: "Enterprise production" }).waitFor()
    await page.getByRole("button", { name: "Validate Enterprise production" }).click()
    await page.getByRole("status").filter({ hasText: "signing key" }).waitFor()
    await page.getByRole("button", { name: "Enable", exact: true }).click()
    await page.getByRole("button", { name: "Confirm", exact: true }).click()
    await page.getByRole("button", { name: "Disable", exact: true }).waitFor()
    await page.getByRole("button", { name: "Edit Enterprise production" }).click()
    await page.screenshot({ path: "/private/tmp/federation-phase6-desktop.png", fullPage: true })
    await page.getByRole("button", { name: "Save changes" }).click()
    await page.getByRole("button", { name: "Confirm changes" }).waitFor()
    await page.getByRole("button", { name: "Cancel", exact: true }).click()
    await page.getByRole("tab", { name: "Okta", exact: true }).click()
    await page.getByText("Okta integration", { exact: true }).waitFor()
    await page.getByRole("tab", { name: "OIDC", exact: true }).click()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole("button", { name: "New connection" }).click()
    await page.screenshot({ path: "/private/tmp/federation-phase6-mobile.png", fullPage: true })
    const box = await page.getByLabel("Issuer URL", { exact: true }).boundingBox()
    assert(box && box.width > 100 && box.x >= 0 && box.x + box.width <= 391)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
    await page.setViewportSize({ width: 1440, height: 1050 })
    await page.goto(`${origin}/agent-identity?tab=delegation`)
    await page.getByRole("button", { name: "Edit Alice Test", exact: true }).click()
    assert.equal(await page.getByRole("button", { name: "Add principal", exact: true }).count(), 0)
    await page.getByLabel("Name (optional)").fill("Alice Demo")
    await page.screenshot({ path: "/private/tmp/federation-principal-desktop.png", fullPage: true })
    await page.getByRole("button", { name: "Save approval", exact: true }).click()
    await page.getByRole("button", { name: "Edit Alice Demo", exact: true }).waitFor()
    await page.getByRole("tab", { name: "Grants", exact: true }).click()
    await page.getByRole("button", { name: `Edit ${data.grants[0].id}`, exact: true }).click()
    assert.equal(await page.getByRole("button", { name: "Add grant", exact: true }).count(), 0)
    assert.equal(await page.getByRole("option", { name: "Alice Demo (synthetic-alice-subject)", exact: true }).count(), 1)
    await page.getByRole("button", { name: "Cancel", exact: true }).click()
    await page.getByRole("button", { name: "Add grant", exact: true }).waitFor()
    await page.getByRole("tab", { name: "Principals", exact: true }).click()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole("button", { name: "Edit Alice Demo", exact: true }).click()
    await page.screenshot({ path: "/private/tmp/federation-principal-mobile.png", fullPage: true })
    const nameBox = await page.getByLabel("Name (optional)").boundingBox()
    assert(nameBox && nameBox.x >= 0 && nameBox.width > 100 && nameBox.x + nameBox.width <= 391)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
    assert.deepEqual(errors, [])
    console.log("PASS: OIDC lifecycle, principal names/save, grant labels, edit controls, desktop/mobile layout")
  } finally { await browser.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
