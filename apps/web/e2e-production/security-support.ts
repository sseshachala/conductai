// Shared accounts, API helpers and the two-account login harness for the
// bounded production security canaries (security.*.spec.ts).
import { expect, test, type APIResponse, type Browser, type BrowserContext, type Page } from "@playwright/test"
import { publishedGatewayFixture } from "./gateway-fixture"

export type Account = { email: string; password: string }
export type Session = { context: BrowserContext; page: Page; userId: string }
export type Workspace = { id: string; name: string; owner_id: string }
export type Member = { clerk_user_id: string; role: string }
export type Identity = { id: string; name: string }
export type Environment = { id: string; name: string }
export type ApiToken = { id: string; token_name: string; token_prefix: string; token?: string }
export type Policy = { workspace_id: string; rule_id: string; action: string; enabled: boolean }
export type AuditEntry = { id: string; actor_id: string | null; action: string; resource_id: string | null }
export type GuardEvent = {
  id: string
  workspace_id: string
  hook_session_id: string | null
  ai_tool: string
  tool_call: string | null
  source: string
  provider: string | null
  model: string | null
  decision: string
  tokens_before: number | null
  tokens_after: number | null
  cost_usd_after: number | null
  execution_status: string | null
  routing_meta: Record<string, unknown> | null
  ts: string
}

export const apiBase = "https://api.conductai.ai"
export const accountA = (): Account => ({
  email: process.env.PROD_E2E_A_EMAIL!,
  password: process.env.PROD_E2E_A_PASSWORD!,
})
export const accountB = (): Account => ({
  email: process.env.PROD_E2E_B_EMAIL!,
  password: process.env.PROD_E2E_B_PASSWORD!,
})

export async function verificationCode(email: string, afterMs: number): Promise<string | null> {
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

export async function fillVerificationCode(page: Page, code: string): Promise<void> {
  const otp = page.locator('input[autocomplete="one-time-code"]')
  if (await otp.count() === 1) await otp.fill(code)
  else for (let index = 0; index < code.length; index++) await otp.nth(index).fill(code[index])
}

export async function login(browser: Browser, account: Account, label: "A" | "B"): Promise<Session> {
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

export async function jwt(page: Page): Promise<string> {
  const token = await page.evaluate(async () => {
    const clerk = (window as any).Clerk
    return clerk?.session?.getToken ? clerk.session.getToken() : null
  })
  if (!token) throw new Error("Production Clerk session did not issue a token")
  return token
}

export async function api(page: Page, path: string, method = "GET", body?: unknown, workspaceId?: string) {
  return page.request.fetch(`${apiBase}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${await jwt(page)}`,
      ...(workspaceId ? { "X-Workspace-Id": workspaceId } : {}),
    },
    data: body,
  })
}

export async function ownedWorkspace(session: Session): Promise<Workspace> {
  const response = await api(session.page, "/projects")
  expect(response.status()).toBe(200)
  const projects = await response.json() as Workspace[]
  const owned = projects.filter(project => project.owner_id === session.userId)
  if (owned.length !== 1) {
    throw new Error("Each production test account must own exactly one disposable workspace")
  }
  return owned[0]
}

export async function members(page: Page, workspaceId: string): Promise<Member[]> {
  const response = await api(page, `/projects/${workspaceId}/members`, "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Member[])
    .map(({ clerk_user_id, role }) => ({ clerk_user_id, role }))
    .sort((a, b) => a.clerk_user_id.localeCompare(b.clerk_user_id))
}

export async function identities(page: Page, workspaceId: string): Promise<Identity[]> {
  const response = await api(page, `/workspaces/${workspaceId}/agent-identities`, "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Identity[])
    .map(({ id, name }) => ({ id, name }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

export async function removeIdentity(page: Page, workspaceId: string, identityId: string): Promise<void> {
  const response = await api(
    page,
    `/workspaces/${workspaceId}/agent-identities/${identityId}`,
    "DELETE",
    undefined,
    workspaceId,
  )
  expect(response.status()).toBe(204)
}

export async function removeStaleCanaryIdentities(page: Page, workspaceId: string): Promise<void> {
  const staleName = /^prod-e2e-[0-9a-f]{8}-/
  const stale = (await identities(page, workspaceId)).filter(identity => staleName.test(identity.name))
  for (const identity of stale) await removeIdentity(page, workspaceId, identity.id)
}

export async function removeStaleCanaryEnvironments(page: Page, workspaceId: string): Promise<void> {
  const staleName = /^prod-e2e-[0-9a-f]{8}-/
  const stale = (await environments(page, workspaceId)).filter(environment => staleName.test(environment.name))
  for (const environment of stale) {
    const response = await api(page, `/environments/${environment.id}`, "DELETE", undefined, workspaceId)
    expect(response.status()).toBe(204)
  }
}

export async function removeStaleCanaryPolicies(page: Page, workspaceId: string): Promise<void> {
  const staleName = /^prod-e2e-[0-9a-f]{8}-/
  const stale = (await policies(page, workspaceId)).filter(
    policy => policy.workspace_id === workspaceId && staleName.test(policy.rule_id),
  )
  for (const policy of stale) await removePolicy(page, workspaceId, policy.rule_id)
}

export async function exchange(page: Page, workspaceId: string) {
  return page.request.post(`${apiBase}/oauth/token`, { form: {
    grant_type: "urn:ietf:params:oauth:grant-type:token-exchange",
    subject_token: await jwt(page),
    subject_token_type: "urn:ietf:params:oauth:token-type:jwt",
    resource: workspaceId,
  } })
}

export async function environments(page: Page, workspaceId: string): Promise<Environment[]> {
  const response = await api(page, "/environments", "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Environment[])
    .map(({ id, name }) => ({ id, name }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

export async function addMember(owner: Session, workspaceId: string, userId: string): Promise<void> {
  const response = await api(
    owner.page,
    `/projects/${workspaceId}/members`,
    "POST",
    { clerk_user_id: userId, role: "developer" },
    workspaceId,
  )
  expect(response.status()).toBe(201)
}

export async function removeMember(owner: Session, workspaceId: string, userId: string): Promise<void> {
  const response = await api(
    owner.page,
    `/projects/${workspaceId}/members/${userId}`,
    "DELETE",
    undefined,
    workspaceId,
  )
  expect(response.status()).toBe(204)
}

export async function refresh(page: Page, refreshToken: string): Promise<APIResponse> {
  return page.request.post(`${apiBase}/oauth/token`, { form: {
    grant_type: "refresh_token",
    refresh_token: refreshToken,
  } })
}

export async function mcp(page: Page, workspaceId: string, accessToken: string): Promise<APIResponse> {
  return page.request.post(`${apiBase}/guard/mcp?workspace_id=${workspaceId}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { jsonrpc: "2.0", id: 1, method: "tools/list", params: {} },
  })
}

export async function setMemberRole(owner: Session, workspaceId: string, userId: string, role: string): Promise<void> {
  const response = await api(
    owner.page,
    `/projects/${workspaceId}/members/${userId}`,
    "PATCH",
    { role },
    workspaceId,
  )
  expect(response.status()).toBe(200)
}

export async function apiTokens(page: Page, workspaceId: string): Promise<ApiToken[]> {
  const response = await api(page, `/workspaces/${workspaceId}/api-tokens`, "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as ApiToken[])
    .map(({ id, token_name, token_prefix }) => ({ id, token_name, token_prefix }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

export async function createApiToken(page: Page, workspaceId: string, name: string): Promise<ApiToken & { token: string }> {
  const response = await api(
    page,
    `/workspaces/${workspaceId}/api-tokens`,
    "POST",
    { name, expires_in_days: 1 },
    workspaceId,
  )
  expect(response.status()).toBe(200)
  return await response.json() as ApiToken & { token: string }
}

export async function removeApiToken(page: Page, workspaceId: string, tokenId: string): Promise<void> {
  const response = await api(
    page,
    `/workspaces/${workspaceId}/api-tokens/${tokenId}`,
    "DELETE",
    undefined,
    workspaceId,
  )
  expect(response.status()).toBe(204)
}

export async function policies(page: Page, workspaceId: string): Promise<Policy[]> {
  const response = await api(page, "/guard/policies", "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Policy[])
    .map(({ workspace_id, rule_id, action, enabled }) => ({ workspace_id, rule_id, action, enabled }))
    .sort((a, b) => a.rule_id.localeCompare(b.rule_id))
}

export async function removePolicy(page: Page, workspaceId: string, ruleId: string): Promise<void> {
  const response = await api(page, `/guard/policies/${ruleId}`, "DELETE", undefined, workspaceId)
  expect(response.status()).toBe(204)
}

export async function auditLog(page: Page, workspaceId: string): Promise<AuditEntry[]> {
  const response = await api(page, `/workspaces/${workspaceId}/audit-log?limit=200`, "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return await response.json() as AuditEntry[]
}

export async function canonicalGatewayProfile(
  page: Page,
  workspaceId: string,
  provider: "anthropic" | "openai",
) {
  return publishedGatewayFixture(async path => {
    const response = await api(page, path, "GET", undefined, workspaceId)
    expect(response.status(), "Published Gateway canary profile must be readable").toBe(200)
    return response.json()
  }, workspaceId, provider, process.env[`PROD_E2E_${provider.toUpperCase()}_MODEL`])
}

export async function gatewayToken(page: Page, workspaceId: string): Promise<string> {
  const response = await exchange(page, workspaceId)
  expect(response.status()).toBe(200)
  const pair = await response.json() as { access_token?: string }
  expect(typeof pair.access_token === "string" && pair.access_token.startsWith("cond_agt_")).toBe(true)
  return pair.access_token!
}

export async function guardEvents(page: Page, workspaceId: string, since: string): Promise<GuardEvent[]> {
  const response = await api(
    page,
    `/guard/events?since=${encodeURIComponent(since)}&limit=200`,
    "GET",
    undefined,
    workspaceId,
  )
  expect(response.status()).toBe(200)
  return await response.json() as GuardEvent[]
}

export async function waitForGuardEvent(
  page: Page,
  workspaceId: string,
  since: string,
  predicate: (event: GuardEvent) => boolean,
): Promise<GuardEvent> {
  let found: GuardEvent | undefined
  await expect.poll(async () => {
    found = (await guardEvents(page, workspaceId, since)).find(predicate)
    return Boolean(found)
  }, { timeout: 20_000, message: "Expected Flight Recorder event was not written" }).toBe(true)
  return found!
}

export function expectNoCredentialMaterial(value: unknown): void {
  const encoded = JSON.stringify(value)
  expect(encoded).not.toMatch(/sk-ant-[A-Za-z0-9_-]{8,}/)
  expect(encoded).not.toMatch(/sk-(?:proj-)?[A-Za-z0-9_-]{20,}/)
  expect(encoded).not.toMatch(/cond_(?:agt|api|ref)_[A-Za-z0-9_-]{8,}/)
}

export type Harness = {
  a: Session
  b: Session
  workspaceA: Workspace
  workspaceB: Workspace
  originalMembersB: Member[]
}

/**
 * Registers the shared two-account login (beforeAll) and membership
 * restoration (afterAll) on the enclosing describe block. The returned
 * object is populated in beforeAll, so read it inside tests only.
 */
export function useProductionHarness(): Harness {
  const harness = {} as Harness

  test.beforeAll(async ({ browser }) => {
    const sessions: Session[] = []
    try {
      const a = await login(browser, accountA(), "A"); sessions.push(a)
      const b = await login(browser, accountB(), "B"); sessions.push(b)
      if (a.userId === b.userId) throw new Error("Production test accounts must be distinct")

      const workspaceA = await ownedWorkspace(a)
      const workspaceB = await ownedWorkspace(b)
      if (workspaceA.id === workspaceB.id) throw new Error("Production test workspaces must be distinct")

      if (process.env.PROD_E2E_GATEWAY_PREFLIGHT === "1" || process.env.PROD_E2E_RESTORE_GATEWAY_FIXTURES === "1") {
        Object.assign(harness, { a, b, workspaceA, workspaceB, originalMembersB: [] })
        return
      }

      await removeStaleCanaryIdentities(a.page, workspaceA.id)
      await removeStaleCanaryIdentities(b.page, workspaceB.id)
      await removeStaleCanaryEnvironments(a.page, workspaceA.id)
      await removeStaleCanaryEnvironments(b.page, workspaceB.id)
      await removeStaleCanaryPolicies(a.page, workspaceA.id)
      await removeStaleCanaryPolicies(b.page, workspaceB.id)

      let originalMembersB = await members(b.page, workspaceB.id)
      if (originalMembersB.some(member => member.clerk_user_id === a.userId)) {
        await removeMember(b, workspaceB.id, a.userId)
        originalMembersB = await members(b.page, workspaceB.id)
      }
      if (originalMembersB.some(member => member.clerk_user_id === a.userId)) {
        throw new Error("Could not restore account A to outsider status in account B's disposable workspace")
      }
      Object.assign(harness, { a, b, workspaceA, workspaceB, originalMembersB })
    } catch (error) {
      await Promise.all(sessions.map(session => session.context.close().catch(() => {})))
      throw error
    }
  })

  test.afterAll(async () => {
    if (!harness.a) return
    const { a, b, workspaceB, originalMembersB } = harness
    try {
      const current = await members(b.page, workspaceB.id).catch(() => [])
      if (process.env.PROD_E2E_GATEWAY_PREFLIGHT !== "1"
          && process.env.PROD_E2E_RESTORE_GATEWAY_FIXTURES !== "1"
          && !originalMembersB.some(member => member.clerk_user_id === a.userId)
          && current.some(member => member.clerk_user_id === a.userId)) {
        await removeMember(b, workspaceB.id, a.userId).catch(() => undefined)
      }
    } finally {
      await Promise.all([a.context.close().catch(() => {}), b.context.close().catch(() => {})])
    }
  })

  return harness
}
