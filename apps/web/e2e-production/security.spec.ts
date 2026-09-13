import { randomUUID } from "node:crypto"
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test"

type Account = { email: string; password: string }
type Session = { context: BrowserContext; page: Page; userId: string }
type Workspace = { id: string; name: string; owner_id: string }
type Member = { clerk_user_id: string; role: string }
type Identity = { id: string; name: string }

const apiBase = "https://api.conductai.ai"
const accountA = (): Account => ({
  email: process.env.PROD_E2E_A_EMAIL!,
  password: process.env.PROD_E2E_A_PASSWORD!,
})
const accountB = (): Account => ({
  email: process.env.PROD_E2E_B_EMAIL!,
  password: process.env.PROD_E2E_B_PASSWORD!,
})

async function verificationCode(email: string, afterMs: number): Promise<string | null> {
  const url = process.env.PROD_E2E_OTP_BROKER_URL
  const token = process.env.PROD_E2E_OTP_BROKER_TOKEN
  if (!url || !token) return null
  const response = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ email, after_ms: afterMs }),
    signal: AbortSignal.timeout(100_000),
  })
  const result = await response.json() as { code?: string; error?: string }
  if (!response.ok || !/^\d{6}$/.test(result.code ?? "")) {
    throw new Error(`Local OTP broker failed (${response.status}): ${result.error ?? "invalid response"}`)
  }
  return result.code!
}

async function fillVerificationCode(page: Page, code: string): Promise<void> {
  const otp = page.locator('input[autocomplete="one-time-code"]')
  if (await otp.count() === 1) await otp.fill(code)
  else for (let index = 0; index < code.length; index++) await otp.nth(index).fill(code[index])
}

async function login(browser: Browser, account: Account, label: "A" | "B"): Promise<Session> {
  const context = await browser.newContext({ baseURL: "https://app.conductai.ai" })
  const page = await context.newPage()
  let stage = "open-sign-in"
  const authStatuses: { operation: string; status: number }[] = []
  page.on("response", response => {
    const url = new URL(response.url())
    if (!url.hostname.includes("clerk")) return
    const operation = url.pathname.split("/").filter(Boolean).at(-1) ?? "unknown"
    authStatuses.push({
      operation: operation.replace(/^(?:client|sess|sia|user|org)_[A-Za-z0-9]+$/, ":id"),
      status: response.status(),
    })
  })
  try {
    await page.goto("/sign-in")
    stage = "submit-email"
    await page.getByLabel(/email address/i).fill(account.email)
    await page.getByRole("button", { name: "Continue", exact: true }).click()
    stage = "submit-password"
    await page.locator('input[name="password"]').fill(account.password)
    const otpRequestedAfter = Date.now()
    await page.getByRole("button", { name: "Continue", exact: true }).click()
    stage = "await-active-session"
    const otp = page.locator('input[autocomplete="one-time-code"]')
    await expect.poll(async () => {
      if (await otp.first().isVisible()) return "verification"
      return page.evaluate(() => (window as any).Clerk?.session?.status === "active" ? "active" : "pending")
        .catch(() => "pending")
    }, { timeout: 30_000, message: "Clerk must activate the session or request verification" })
      .not.toBe("pending")
    if (await otp.first().isVisible()) {
      stage = "submit-verification-code"
      const code = await verificationCode(account.email, otpRequestedAfter)
      if (code) await fillVerificationCode(page, code)
      else console.log(`Enter the Clerk verification code for production test account ${label} in the browser`)
    }
    await expect.poll(
      () => page.evaluate(() => ({
        userId: (window as any).Clerk?.user?.id ?? null,
        status: (window as any).Clerk?.session?.status ?? null,
      })).catch(() => null),
      { timeout: 120_000, message: "Dedicated production account must reach an active Clerk session" },
    ).toMatchObject({ status: "active" })
    const userId = await page.evaluate(() => (window as any).Clerk.user.id as string)
    return { context, page, userId }
  } catch {
    const state = await page.evaluate(() => ({
      path: location.pathname,
      sessionStatus: (window as any).Clerk?.session?.status ?? null,
      passwordVisible: Boolean(document.querySelector('input[name="password"]')),
      verificationVisible: Boolean(document.querySelector('input[autocomplete="one-time-code"]')),
    })).catch(() => null)
    await context.close().catch(() => {})
    throw new Error(`Production test-account login failed at ${stage}; ${JSON.stringify({ state, authStatuses })}`)
  }
}

async function jwt(page: Page): Promise<string> {
  const token = await page.evaluate(async () => {
    const clerk = (window as any).Clerk
    return clerk?.session?.getToken ? clerk.session.getToken() : null
  })
  if (!token) throw new Error("Production Clerk session did not issue a token")
  return token
}

async function api(page: Page, path: string, method = "GET", body?: unknown, workspaceId?: string) {
  return page.request.fetch(`${apiBase}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${await jwt(page)}`,
      ...(workspaceId ? { "X-Workspace-Id": workspaceId } : {}),
    },
    data: body,
  })
}

async function ownedWorkspace(session: Session): Promise<Workspace> {
  const response = await api(session.page, "/projects")
  expect(response.status()).toBe(200)
  const projects = await response.json() as Workspace[]
  const owned = projects.filter(project => project.owner_id === session.userId)
  if (owned.length !== 1) {
    throw new Error("Each production test account must own exactly one disposable workspace")
  }
  return owned[0]
}

async function members(page: Page, workspaceId: string): Promise<Member[]> {
  const response = await api(page, `/projects/${workspaceId}/members`, "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Member[])
    .map(({ clerk_user_id, role }) => ({ clerk_user_id, role }))
    .sort((a, b) => a.clerk_user_id.localeCompare(b.clerk_user_id))
}

async function identities(page: Page, workspaceId: string): Promise<Identity[]> {
  const response = await api(page, `/workspaces/${workspaceId}/agent-identities`, "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Identity[])
    .map(({ id, name }) => ({ id, name }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

async function exchange(page: Page, workspaceId: string) {
  return page.request.post(`${apiBase}/oauth/token`, { form: {
    grant_type: "urn:ietf:params:oauth:grant-type:token-exchange",
    subject_token: await jwt(page),
    subject_token_type: "urn:ietf:params:oauth:token-type:jwt",
    resource: workspaceId,
  } })
}

test("production credential issuance respects membership and revocation", async ({ browser }) => {
  const sessions: Session[] = []
  let a: Session | undefined
  let b: Session | undefined
  let workspaceB: Workspace | undefined
  let originalMembersB: Member[] | undefined
  try {
    a = await login(browser, accountA(), "A"); sessions.push(a)
    b = await login(browser, accountB(), "B"); sessions.push(b)
    if (a.userId === b.userId) throw new Error("Production test accounts must be distinct")

    const workspaceA = await ownedWorkspace(a)
    workspaceB = await ownedWorkspace(b)
    if (workspaceA.id === workspaceB.id) throw new Error("Production test workspaces must be distinct")

    originalMembersB = await members(b.page, workspaceB.id)
    if (originalMembersB.some(member => member.clerk_user_id === a!.userId)) {
      throw new Error("Account A must begin outside account B's disposable workspace")
    }
    const originalIdentitiesB = await identities(b.page, workspaceB.id)

    const ownerIssued = await exchange(a.page, workspaceA.id)
    expect(ownerIssued.status()).toBe(200)
    const ownerPair = await ownerIssued.json()
    expect(typeof ownerPair.access_token === "string" && ownerPair.access_token.startsWith("cond_agt_")).toBe(true)
    const mcp = await a.page.request.post(`${apiBase}/guard/mcp?workspace_id=${workspaceA.id}`, {
      headers: { Authorization: `Bearer ${ownerPair.access_token}` },
      data: { jsonrpc: "2.0", id: 1, method: "tools/list", params: {} },
    })
    expect(mcp.status()).toBe(200)
    expect(Array.isArray((await mcp.json()).result?.tools)).toBe(true)
    const identitiesABeforeUnknown = await identities(a.page, workspaceA.id)

    const outsider = await exchange(a.page, workspaceB.id)
    expect(outsider.status()).toBe(403)
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
    expect(await identities(b.page, workspaceB.id)).toEqual(originalIdentitiesB)

    const unknown = await exchange(a.page, randomUUID())
    expect(unknown.status()).toBe(403)
    expect(await identities(a.page, workspaceA.id)).toEqual(identitiesABeforeUnknown)

    const added = await api(
      b.page,
      `/projects/${workspaceB.id}/members`,
      "POST",
      { clerk_user_id: a.userId, role: "developer" },
      workspaceB.id,
    )
    expect(added.status()).toBe(201)

    const memberIssued = await exchange(a.page, workspaceB.id)
    expect(memberIssued.status()).toBe(200)
    const memberPair = await memberIssued.json()
    expect(typeof memberPair.refresh_token === "string" && memberPair.refresh_token.startsWith("cond_ref_")).toBe(true)

    const removed = await api(
      b.page,
      `/projects/${workspaceB.id}/members/${a.userId}`,
      "DELETE",
      undefined,
      workspaceB.id,
    )
    expect(removed.status()).toBe(204)
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)

    const refresh = await a.page.request.post(`${apiBase}/oauth/token`, { form: {
      grant_type: "refresh_token",
      refresh_token: memberPair.refresh_token,
    } })
    expect([401, 403]).toContain(refresh.status())
    expect((await exchange(a.page, workspaceB.id)).status()).toBe(403)
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
  } finally {
    if (a && b && workspaceB && originalMembersB) {
      const current = await members(b.page, workspaceB.id).catch(() => [])
      if (!originalMembersB.some(member => member.clerk_user_id === a!.userId)
          && current.some(member => member.clerk_user_id === a!.userId)) {
        await api(
          b.page,
          `/projects/${workspaceB.id}/members/${a.userId}`,
          "DELETE",
          undefined,
          workspaceB.id,
        ).catch(() => undefined)
      }
    }
    await Promise.all(sessions.map(session => session.context.close().catch(() => {})))
  }
})
