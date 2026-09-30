import { execFileSync, spawn } from "node:child_process"
import { resolve } from "node:path"
import { expect, test, type Browser, type BrowserContext } from "@playwright/test"
import { expectMcpInvocation } from "../e2e-security/support/mcp"

const api = "https://localhost:3444"
const web = "https://localhost:3443"
const workspace = "bbbbbbbb-0000-4000-8000-000000000001"
type Actor = "ADMIN" | "VIEWER" | "UNMAPPED"
type Session = { token: string; expires_at: number; user: { id: string; name: string } }
const contexts: BrowserContext[] = []

async function login(browser: Browser, actor: Actor) {
  const context = await browser.newContext({ baseURL: web, ignoreHTTPSErrors: false })
  contexts.push(context)
  const page = await context.newPage()
  await page.goto("/theguard")
  await page.locator('input[name="username"]').fill(process.env[`CONSOLE_E2E_${actor}_USERNAME`]!)
  await page.locator('input[name="password"]').fill(process.env[`CONSOLE_E2E_${actor}_PASSWORD`]!)
  await page.getByRole("button", { name: /sign in/i }).click()
  await page.waitForURL(url => url.origin === web)
  return { context, page }
}

async function session(context: BrowserContext): Promise<Session> {
  const response = await context.request.post(`${web}/api/auth/session`, { headers: { Origin: web }, maxRedirects: 0 })
  expect(response.status(), "Mapped console identity authenticated").toBe(200)
  const result = await response.json()
  expect(typeof result.token === "string" && typeof result.user?.id === "string").toBe(true)
  return result
}

async function projects(context: BrowserContext, token: string) {
  return context.request.get(`${api}/projects`, { headers: { Authorization: `Bearer ${token}` }, maxRedirects: 0 })
}

function mapping(action: "enable" | "disable") {
  try {
    execFileSync(process.env.CONSOLE_E2E_PYTHON || "python3", [
      resolve("../../tools/console-e2e/mapping_control.py"), action,
    ], { stdio: "pipe", timeout: 30_000 })
  } catch { throw new Error("Local viewer mapping fixture update failed; details omitted") }
}

test.afterEach(async () => {
  for (const context of contexts.splice(0)) await context.close()
})

test("@console admin logs in and accesses only the provisioned workspace", async ({ browser }) => {
  const { context } = await login(browser, "ADMIN")
  const current = await session(context)
  const response = await projects(context, current.token)
  expect(response.status()).toBe(200)
  const rows = await response.json()
  expect(Array.isArray(rows) && rows.some((row: { id: string }) => row.id === workspace)).toBe(true)
  const foreign = await context.request.get(`${api}/projects/bbbbbbbb-0000-4000-8000-000000000099/members`, {
    headers: { Authorization: `Bearer ${current.token}` }, maxRedirects: 0,
  })
  expect([403, 404].includes(foreign.status())).toBe(true)
})

test("@console viewer reads but cannot mutate membership", async ({ browser }) => {
  const { context } = await login(browser, "VIEWER")
  const current = await session(context)
  expect((await projects(context, current.token)).status()).toBe(200)
  const mutation = await context.request.post(`${api}/projects/${workspace}/members`, {
    headers: { Authorization: `Bearer ${current.token}` },
    data: { clerk_user_id: "console-e2e-must-not-be-created", role: "admin" }, maxRedirects: 0,
  })
  expect(mutation.status()).toBe(403)
})

test("@console unmapped IdP login cannot obtain Conduct session", async ({ browser }) => {
  const { context } = await login(browser, "UNMAPPED")
  const response = await context.request.post(`${web}/api/auth/session`, { headers: { Origin: web }, maxRedirects: 0 })
  expect([401, 403].includes(response.status())).toBe(true)
})

test("@console forged identity headers do not authenticate", async ({ request }) => {
  const response = await request.get(`${api}/projects`, { headers: {
    "X-Auth-Request-User": "admin", "X-Forwarded-User": "admin",
    "X-Auth-Request-Email": "admin@example.invalid",
  }, maxRedirects: 0 })
  expect([401, 403].includes(response.status())).toBe(true)
})

test("@console session endpoint rejects cross-origin CSRF", async ({ browser }) => {
  const { context } = await login(browser, "ADMIN")
  const response = await context.request.post(`${web}/api/auth/session`, {
    headers: { Origin: "https://foreign.example.invalid", "Sec-Fetch-Site": "cross-site" }, maxRedirects: 0,
  })
  expect(response.status()).toBe(403)
})

test("@console expired API session is rejected and browser can renew", async ({ browser }) => {
  const { context } = await login(browser, "VIEWER")
  const current = await session(context)
  const delay = current.expires_at * 1000 - Date.now() + 2500
  expect(delay > 0 && delay < 90_000, "Bounded console session lifetime").toBe(true)
  await new Promise(resolve => setTimeout(resolve, delay))
  expect([401, 403].includes((await projects(context, current.token)).status())).toBe(true)
  const renewed = await session(context)
  expect((await projects(context, renewed.token)).status()).toBe(200)
})

test("@console disabled mapping rejects an existing session and restoration works", async ({ browser }) => {
  const { context } = await login(browser, "VIEWER")
  const current = await session(context)
  try {
    mapping("disable")
    expect([401, 403].includes((await projects(context, current.token)).status())).toBe(true)
    const response = await context.request.post(`${web}/api/auth/session`, { headers: { Origin: web }, maxRedirects: 0 })
    expect([401, 403].includes(response.status())).toBe(true)
  } finally { mapping("enable") }
  expect((await projects(context, (await session(context)).token)).status()).toBe(200)
})

test("@console logout clears proxy session", async ({ browser }) => {
  const { context, page } = await login(browser, "ADMIN")
  await session(context)
  await page.getByRole("button", { name: /account/i }).click()
  await page.getByRole("button", { name: /sign out/i }).click()
  await page.waitForURL(url => url.pathname === "/signed-out")
  const response = await context.request.post(`${web}/api/auth/session`, { headers: { Origin: web }, maxRedirects: 0 })
  expect([401, 403].includes(response.status())).toBe(true)
})

test("@console CLI token exchange refresh replay and MCP access", async ({ browser }) => {
  const { context, page } = await login(browser, "ADMIN")
  const current = await session(context)
  const issued = await context.request.post(`${api}/oauth/token`, { form: {
    grant_type: "urn:ietf:params:oauth:grant-type:token-exchange", subject_token: current.token,
    subject_token_type: "urn:ietf:params:oauth:token-type:jwt", resource: workspace,
  } })
  expect(issued.status()).toBe(200)
  const pair = await issued.json()
  await expectMcpInvocation(page, `${api}/mcp?workspace_id=${workspace}`, pair.access_token)
  const refresh = () => context.request.post(`${api}/oauth/token`, { form: {
    grant_type: "refresh_token", refresh_token: pair.refresh_token,
  } })
  const rotated = await refresh()
  expect(rotated.status()).toBe(200)
  const next = await rotated.json()
  expect(typeof next.refresh_token === "string" && next.refresh_token !== pair.refresh_token).toBe(true)
  await expectMcpInvocation(page, `${api}/mcp?workspace_id=${workspace}`, next.access_token)
  expect([400, 401, 403].includes((await refresh()).status())).toBe(true)
})

test("@console real CLI browser callback yields a usable local credential", async ({ browser }) => {
  const { page } = await login(browser, "ADMIN")
  const child = spawn(process.env.CONSOLE_E2E_PYTHON || "python3", [
    resolve("../../tools/console-e2e/cli_callback.py"),
  ], { env: process.env, stdio: ["ignore", "pipe", "pipe"] })
  let passed = false
  const exit = new Promise<number | null>(resolve => child.once("close", resolve))
  const url = new Promise<string>((resolve, reject) => {
    let pending = ""
    child.stdout.on("data", chunk => {
      pending += chunk.toString()
      let newline: number
      while ((newline = pending.indexOf("\n")) >= 0) {
        const line = pending.slice(0, newline)
        pending = pending.slice(newline + 1)
        if (line.startsWith("LOGIN_URL ")) resolve(line.slice(10).trim())
        if (line === "CLI_PASS") passed = true
      }
    })
    child.once("error", () => reject(new Error("CLI child could not start")))
    child.once("close", () => reject(new Error("CLI child closed before browser navigation")))
  })
  child.stderr.resume()
  const timer = setTimeout(() => child.kill(), 120_000)
  try {
    const target = new URL(await url)
    expect(target.origin === web && target.pathname === "/cli-auth").toBe(true)
    await page.goto(target.toString())
    expect(await exit).toBe(0)
    expect(passed).toBe(true)
  } finally {
    clearTimeout(timer)
    if (child.exitCode === null) child.kill()
    await exit
  }
})
