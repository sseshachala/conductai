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
    assert.deepEqual(errors, [])
    console.log("PASS: horizontal integration tabs, OIDC validation, enable confirmation, active-edit confirmation, desktop/mobile layout")
  } finally { await browser.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
