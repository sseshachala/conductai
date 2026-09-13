import { randomUUID } from "node:crypto"
import { expect, test, type APIResponse, type Browser, type BrowserContext, type Page } from "@playwright/test"

type Account = { email: string; password: string }
type Session = { context: BrowserContext; page: Page; userId: string }
type Workspace = { id: string; name: string; owner_id: string }
type Member = { clerk_user_id: string; role: string }
type Identity = { id: string; name: string }
type Environment = { id: string; name: string }
type ApiToken = { id: string; token_name: string; token_prefix: string; token?: string }
type Policy = { workspace_id: string; rule_id: string; action: string; enabled: boolean }
type AuditEntry = { id: string; actor_id: string | null; action: string; resource_id: string | null }
type GatewayProfile = {
  id: string | null
  name: string
  provider: string
  protocol: string
  credential_ref: string | null
  environment_id: string | null
  deployments: { alias: string; model: string }[]
}
type GuardEvent = {
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

async function removeIdentity(page: Page, workspaceId: string, identityId: string): Promise<void> {
  const response = await api(
    page,
    `/workspaces/${workspaceId}/agent-identities/${identityId}`,
    "DELETE",
    undefined,
    workspaceId,
  )
  expect(response.status()).toBe(204)
}

async function removeStaleCanaryIdentities(page: Page, workspaceId: string): Promise<void> {
  const staleName = /^prod-e2e-[0-9a-f]{8}-/
  const stale = (await identities(page, workspaceId)).filter(identity => staleName.test(identity.name))
  for (const identity of stale) await removeIdentity(page, workspaceId, identity.id)
}

async function removeStaleCanaryEnvironments(page: Page, workspaceId: string): Promise<void> {
  const staleName = /^prod-e2e-[0-9a-f]{8}-/
  const stale = (await environments(page, workspaceId)).filter(environment => staleName.test(environment.name))
  for (const environment of stale) {
    const response = await api(page, `/environments/${environment.id}`, "DELETE", undefined, workspaceId)
    expect(response.status()).toBe(204)
  }
}

async function removeStaleCanaryPolicies(page: Page, workspaceId: string): Promise<void> {
  const staleName = /^prod-e2e-[0-9a-f]{8}-/
  const stale = (await policies(page, workspaceId)).filter(
    policy => policy.workspace_id === workspaceId && staleName.test(policy.rule_id),
  )
  for (const policy of stale) await removePolicy(page, workspaceId, policy.rule_id)
}

async function exchange(page: Page, workspaceId: string) {
  return page.request.post(`${apiBase}/oauth/token`, { form: {
    grant_type: "urn:ietf:params:oauth:grant-type:token-exchange",
    subject_token: await jwt(page),
    subject_token_type: "urn:ietf:params:oauth:token-type:jwt",
    resource: workspaceId,
  } })
}

async function environments(page: Page, workspaceId: string): Promise<Environment[]> {
  const response = await api(page, "/environments", "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Environment[])
    .map(({ id, name }) => ({ id, name }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

async function addMember(owner: Session, workspaceId: string, userId: string): Promise<void> {
  const response = await api(
    owner.page,
    `/projects/${workspaceId}/members`,
    "POST",
    { clerk_user_id: userId, role: "developer" },
    workspaceId,
  )
  expect(response.status()).toBe(201)
}

async function removeMember(owner: Session, workspaceId: string, userId: string): Promise<void> {
  const response = await api(
    owner.page,
    `/projects/${workspaceId}/members/${userId}`,
    "DELETE",
    undefined,
    workspaceId,
  )
  expect(response.status()).toBe(204)
}

async function refresh(page: Page, refreshToken: string): Promise<APIResponse> {
  return page.request.post(`${apiBase}/oauth/token`, { form: {
    grant_type: "refresh_token",
    refresh_token: refreshToken,
  } })
}

async function mcp(page: Page, workspaceId: string, accessToken: string): Promise<APIResponse> {
  return page.request.post(`${apiBase}/guard/mcp?workspace_id=${workspaceId}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { jsonrpc: "2.0", id: 1, method: "tools/list", params: {} },
  })
}

async function setMemberRole(owner: Session, workspaceId: string, userId: string, role: string): Promise<void> {
  const response = await api(
    owner.page,
    `/projects/${workspaceId}/members/${userId}`,
    "PATCH",
    { role },
    workspaceId,
  )
  expect(response.status()).toBe(200)
}

async function apiTokens(page: Page, workspaceId: string): Promise<ApiToken[]> {
  const response = await api(page, `/workspaces/${workspaceId}/api-tokens`, "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as ApiToken[])
    .map(({ id, token_name, token_prefix }) => ({ id, token_name, token_prefix }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

async function createApiToken(page: Page, workspaceId: string, name: string): Promise<ApiToken & { token: string }> {
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

async function removeApiToken(page: Page, workspaceId: string, tokenId: string): Promise<void> {
  const response = await api(
    page,
    `/workspaces/${workspaceId}/api-tokens/${tokenId}`,
    "DELETE",
    undefined,
    workspaceId,
  )
  expect(response.status()).toBe(204)
}

async function policies(page: Page, workspaceId: string): Promise<Policy[]> {
  const response = await api(page, "/guard/policies", "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return (await response.json() as Policy[])
    .map(({ workspace_id, rule_id, action, enabled }) => ({ workspace_id, rule_id, action, enabled }))
    .sort((a, b) => a.rule_id.localeCompare(b.rule_id))
}

async function removePolicy(page: Page, workspaceId: string, ruleId: string): Promise<void> {
  const response = await api(page, `/guard/policies/${ruleId}`, "DELETE", undefined, workspaceId)
  expect(response.status()).toBe(204)
}

async function auditLog(page: Page, workspaceId: string): Promise<AuditEntry[]> {
  const response = await api(page, `/workspaces/${workspaceId}/audit-log?limit=200`, "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  return await response.json() as AuditEntry[]
}

async function canonicalGatewayProfile(
  page: Page,
  workspaceId: string,
  provider: "anthropic" | "openai",
): Promise<GatewayProfile> {
  const response = await api(page, `/workspaces/${workspaceId}/gateways`, "GET", undefined, workspaceId)
  expect(response.status()).toBe(200)
  const profiles = await response.json() as GatewayProfile[]
  const defaults = profiles.filter(profile => profile.id && profile.environment_id === null)
  expect(defaults, `${provider} canary workspace must have exactly one persisted default Gateway Profile`).toHaveLength(1)
  const profile = defaults[0]
  expect([provider, "litellm"]).toContain(profile.provider)
  expect(
    provider === "anthropic"
      ? profile.protocol === "anthropic"
      : ["openai", "openai_compatible"].includes(profile.protocol),
  ).toBe(true)
  expect(profile.credential_ref).toMatch(/^vault:\/\/.+/)
  expect(profile.deployments.length).toBeGreaterThan(0)
  return profile
}

async function gatewayToken(page: Page, workspaceId: string): Promise<string> {
  const response = await exchange(page, workspaceId)
  expect(response.status()).toBe(200)
  const pair = await response.json() as { access_token?: string }
  expect(typeof pair.access_token === "string" && pair.access_token.startsWith("cond_agt_")).toBe(true)
  return pair.access_token!
}

async function guardEvents(page: Page, workspaceId: string, since: string): Promise<GuardEvent[]> {
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

async function waitForGuardEvent(
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

function expectNoCredentialMaterial(value: unknown): void {
  const encoded = JSON.stringify(value)
  expect(encoded).not.toMatch(/sk-ant-[A-Za-z0-9_-]{8,}/)
  expect(encoded).not.toMatch(/sk-(?:proj-)?[A-Za-z0-9_-]{20,}/)
  expect(encoded).not.toMatch(/cond_(?:agt|api|ref)_[A-Za-z0-9_-]{8,}/)
}

function uniqueDeploymentModels(profile: GatewayProfile): string[] {
  return [...new Set(profile.deployments.map(deployment => deployment.model.trim()).filter(Boolean))]
}

type Harness = {
  a: Session
  b: Session
  workspaceA: Workspace
  workspaceB: Workspace
  originalMembersB: Member[]
}

test.describe("bounded production security canaries", () => {
  let harness: Harness
  const runPrefix = `prod-e2e-${randomUUID().slice(0, 8)}`

  test.beforeAll(async ({ browser }) => {
    const sessions: Session[] = []
    try {
      const a = await login(browser, accountA(), "A"); sessions.push(a)
      const b = await login(browser, accountB(), "B"); sessions.push(b)
      if (a.userId === b.userId) throw new Error("Production test accounts must be distinct")

      const workspaceA = await ownedWorkspace(a)
      const workspaceB = await ownedWorkspace(b)
      if (workspaceA.id === workspaceB.id) throw new Error("Production test workspaces must be distinct")

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
      harness = { a, b, workspaceA, workspaceB, originalMembersB }
    } catch (error) {
      await Promise.all(sessions.map(session => session.context.close().catch(() => {})))
      throw error
    }
  })

  test.afterAll(async () => {
    if (!harness) return
    const { a, b, workspaceB, originalMembersB } = harness
    try {
      const current = await members(b.page, workspaceB.id).catch(() => [])
      if (!originalMembersB.some(member => member.clerk_user_id === a.userId)
          && current.some(member => member.clerk_user_id === a.userId)) {
        await removeMember(b, workspaceB.id, a.userId).catch(() => undefined)
      }
    } finally {
      await Promise.all([a.context.close().catch(() => {}), b.context.close().catch(() => {})])
    }
  })

  test("@prod account ownership and disposable workspace preflight", async () => {
    const { a, b, workspaceA, workspaceB, originalMembersB } = harness
    expect(a.userId).not.toBe(b.userId)
    expect(workspaceA.id).not.toBe(workspaceB.id)
    expect(workspaceA.owner_id).toBe(a.userId)
    expect(workspaceB.owner_id).toBe(b.userId)
    expect(originalMembersB.some(member => member.clerk_user_id === a.userId)).toBe(false)
  })

  test("@prod-gateway Claude compatibility probe and authentication boundary", async () => {
    const { a } = harness
    const hello = await a.page.request.head(`${apiBase}/gateway/v1/anthropic/api/hello`)
    expect(hello.status()).toBe(204)

    const missing = await a.page.request.get(`${apiBase}/gateway/v1/anthropic/v1/models?limit=1000`)
    expect(missing.status()).toBe(401)
    const invalid = await a.page.request.get(`${apiBase}/gateway/v1/anthropic/v1/models?limit=1000`, {
      headers: { "x-api-key": "invalid-production-canary-token" },
    })
    expect(invalid.status()).toBe(401)
  })

  test("@prod-gateway Claude model discovery exposes only canonical profile deployments", async () => {
    const { a, workspaceA } = harness
    const profile = await canonicalGatewayProfile(a.page, workspaceA.id, "anthropic")
    const token = await gatewayToken(a.page, workspaceA.id)
    const since = new Date(Date.now() - 1_000).toISOString()
    const response = await a.page.request.get(`${apiBase}/gateway/v1/anthropic/v1/models?limit=1000`, {
      headers: {
        "x-api-key": token,
        "x-conductai-workspace-id": workspaceA.id,
        "user-agent": "claude-code/production-canary",
      },
    })
    expect(response.status()).toBe(200)
    const body = await response.json() as { data: { id: string; display_name?: string }[] }
    expect(body.data.map(model => model.id)).toEqual(uniqueDeploymentModels(profile))
    expectNoCredentialMaterial(body)

    const event = await waitForGuardEvent(
      a.page,
      workspaceA.id,
      since,
      candidate => candidate.ai_tool === "claude-code" && candidate.model === "model-catalog",
    )
    expect(event.routing_meta).toMatchObject({ operation: "model_catalog", billable: false })
    expect(event.cost_usd_after).toBeNull()
    expectNoCredentialMaterial(event)
  })

  test("@prod-gateway Claude token counting resolves the Vault profile and stays non-billable", async () => {
    const { a, workspaceA } = harness
    const profile = await canonicalGatewayProfile(a.page, workspaceA.id, "anthropic")
    const model = uniqueDeploymentModels(profile)[0]
    const token = await gatewayToken(a.page, workspaceA.id)
    const hookSession = `${runPrefix}-count-tokens`
    const since = new Date(Date.now() - 1_000).toISOString()
    const response = await a.page.request.post(`${apiBase}/gateway/v1/anthropic/v1/messages/count_tokens`, {
      headers: {
        "x-api-key": token,
        "anthropic-version": "2023-06-01",
        "x-conduct-ai-tool": "production-canary",
        "x-conduct-session-id": hookSession,
        "x-conductai-workspace-id": workspaceA.id,
      },
      data: { model, messages: [{ role: "user", content: "Count this bounded production canary." }] },
    })
    expect(response.status()).toBe(200)
    const body = await response.json() as { input_tokens?: number }
    expect(body.input_tokens).toBeGreaterThan(0)
    expectNoCredentialMaterial(body)

    const event = await waitForGuardEvent(
      a.page,
      workspaceA.id,
      since,
      candidate => candidate.hook_session_id === hookSession,
    )
    expect(event.routing_meta).toMatchObject({ operation: "token_count", billable: false })
    expect(event.cost_usd_after).toBeNull()
    expectNoCredentialMaterial(event)
  })

  test("@prod-gateway Claude non-streaming inference records attributed billable activity", async () => {
    const { a, workspaceA } = harness
    const profile = await canonicalGatewayProfile(a.page, workspaceA.id, "anthropic")
    const model = uniqueDeploymentModels(profile)[0]
    const token = await gatewayToken(a.page, workspaceA.id)
    const hookSession = `${runPrefix}-claude-message`
    const since = new Date(Date.now() - 1_000).toISOString()
    const response = await a.page.request.post(`${apiBase}/gateway/v1/anthropic/v1/messages`, {
      headers: {
        "x-api-key": token,
        "anthropic-version": "2023-06-01",
        "x-conduct-ai-tool": "production-canary",
        "x-conduct-session-id": hookSession,
        "x-conductai-workspace-id": workspaceA.id,
      },
      data: {
        model,
        max_tokens: 16,
        messages: [{ role: "user", content: "Reply with the single word OK." }],
      },
    })
    expect(response.status()).toBe(200)
    const body = await response.json() as { content?: unknown[] }
    expect(Array.isArray(body.content) && body.content.length > 0).toBe(true)
    expectNoCredentialMaterial(body)

    const event = await waitForGuardEvent(
      a.page,
      workspaceA.id,
      since,
      candidate => candidate.hook_session_id === hookSession,
    )
    expect(event).toMatchObject({
      workspace_id: workspaceA.id,
      ai_tool: "production-canary",
      source: "proxy",
      provider: "anthropic",
      model,
      decision: "allowed",
    })
    expect(event.routing_meta?.billable).not.toBe(false)
    expect(event.tokens_before).toBeGreaterThan(0)
    expect(event.tokens_after).toBeGreaterThan(0)
    expect(typeof event.cost_usd_after).toBe("number")
    expectNoCredentialMaterial(event)
  })

  test("@prod-gateway Claude streaming inference emits content and closes cleanly", async () => {
    const { a, workspaceA } = harness
    const profile = await canonicalGatewayProfile(a.page, workspaceA.id, "anthropic")
    const model = uniqueDeploymentModels(profile)[0]
    const token = await gatewayToken(a.page, workspaceA.id)
    const hookSession = `${runPrefix}-claude-stream`
    const since = new Date(Date.now() - 1_000).toISOString()
    const response = await a.page.request.post(`${apiBase}/gateway/v1/anthropic/v1/messages`, {
      headers: {
        "x-api-key": token,
        "anthropic-version": "2023-06-01",
        accept: "text/event-stream",
        "x-conduct-ai-tool": "production-canary",
        "x-conduct-session-id": hookSession,
        "x-conductai-workspace-id": workspaceA.id,
      },
      data: {
        model,
        max_tokens: 16,
        stream: true,
        messages: [{ role: "user", content: "Reply with the single word OK." }],
      },
    })
    expect(response.status()).toBe(200)
    expect(response.headers()["content-type"]).toContain("text/event-stream")
    const body = await response.text()
    expect(body).toContain("data:")
    expect(body).toMatch(/message_stop|content_block_delta/)
    expectNoCredentialMaterial(body)
    const event = await waitForGuardEvent(
      a.page,
      workspaceA.id,
      since,
      candidate => candidate.hook_session_id === hookSession,
    )
    expect(event.execution_status).not.toBe("error")
    expectNoCredentialMaterial(event)
  })

  test("@prod-gateway OpenAI Responses inference remains functional after transport refactor", async () => {
    const { b, workspaceB } = harness
    const profile = await canonicalGatewayProfile(b.page, workspaceB.id, "openai")
    const model = uniqueDeploymentModels(profile)[0]
    const token = await gatewayToken(b.page, workspaceB.id)
    const hookSession = `${runPrefix}-openai-response`
    const since = new Date(Date.now() - 1_000).toISOString()
    const response = await b.page.request.post(`${apiBase}/gateway/v1/openai/v1/responses`, {
      headers: {
        authorization: `Bearer ${token}`,
        "x-conduct-ai-tool": "production-canary",
        "x-conduct-session-id": hookSession,
        "x-conductai-workspace-id": workspaceB.id,
      },
      data: { model, input: "Reply with the single word OK.", max_output_tokens: 16 },
    })
    expect(response.status()).toBe(200)
    const body = await response.json() as { id?: string; output?: unknown[] }
    expect(typeof body.id).toBe("string")
    expect(Array.isArray(body.output)).toBe(true)
    expectNoCredentialMaterial(body)
    const event = await waitForGuardEvent(
      b.page,
      workspaceB.id,
      since,
      candidate => candidate.hook_session_id === hookSession,
    )
    expect(event).toMatchObject({
      workspace_id: workspaceB.id,
      ai_tool: "production-canary",
      source: "proxy",
      provider: "openai",
      model,
      decision: "allowed",
    })
    expectNoCredentialMaterial(event)
  })

  test("@prod-gateway PreToolUse and PostToolUse updates correlate to one session event", async () => {
    const { a, workspaceA } = harness
    const token = await gatewayToken(a.page, workspaceA.id)
    const hookSession = `${runPrefix}-hook-correlation`
    const created = await a.page.request.post(`${apiBase}/guard/events`, {
      headers: { authorization: `Bearer ${token}` },
      data: {
        workspace_id: workspaceA.id,
        ai_tool: "codex",
        tool_call: "Read",
        input_summary: "Bounded production hook-correlation canary",
        decision: "allowed",
        hook_session_id: hookSession,
      },
    })
    expect(created.status()).toBe(201)
    const preEvent = await created.json() as GuardEvent
    expectNoCredentialMaterial(preEvent)

    const updated = await a.page.request.post(`${apiBase}/guard/events/usage`, {
      headers: { authorization: `Bearer ${token}` },
      data: {
        workspace_id: workspaceA.id,
        hook_session_id: hookSession,
        tool_name: "Read",
        tokens_input: 7,
        tokens_output: 3,
        duration_ms: 5,
        ai_tool: "codex",
        execution_status: "success",
        result_summary: "Canary completed",
      },
    })
    expect(updated.status()).toBe(200)
    expect(await updated.json()).toEqual({ updated: true })

    const events = await guardEvents(a.page, workspaceA.id, new Date(Date.now() - 60_000).toISOString())
    const correlated = events.filter(event => event.hook_session_id === hookSession)
    expect(correlated).toHaveLength(1)
    expect(correlated[0]).toMatchObject({
      id: preEvent.id,
      tokens_before: 7,
      tokens_after: 3,
      execution_status: "success",
    })
    expectNoCredentialMaterial(correlated[0])
  })

  test("@prod anonymous and forged forwarding headers do not authenticate", async () => {
    const { a, workspaceA } = harness
    const response = await a.page.request.get(`${apiBase}/projects`, {
      headers: {
        "X-Workspace-Id": workspaceA.id,
        "X-Forwarded-For": "127.0.0.1",
        "X-Real-IP": "127.0.0.1",
        "X-Forwarded-Proto": "https",
      },
    })
    expect(response.status()).toBe(401)
  })

  test("@prod owner token can list MCP tools in its workspace", async () => {
    const { a, workspaceA } = harness
    const issued = await exchange(a.page, workspaceA.id)
    expect(issued.status()).toBe(200)
    const pair = await issued.json()
    expect(typeof pair.access_token === "string" && pair.access_token.startsWith("cond_agt_")).toBe(true)

    const response = await mcp(a.page, workspaceA.id, pair.access_token)
    expect(response.status()).toBe(200)
    expect(Array.isArray((await response.json()).result?.tools)).toBe(true)
  })

  test("@prod foreign and unknown workspaces cannot issue credentials", async () => {
    const { a, b, workspaceA, workspaceB, originalMembersB } = harness
    const identitiesABefore = await identities(a.page, workspaceA.id)
    const identitiesBBefore = await identities(b.page, workspaceB.id)

    expect((await exchange(a.page, workspaceB.id)).status()).toBe(403)
    expect((await exchange(a.page, randomUUID())).status()).toBe(403)
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
    expect(await identities(a.page, workspaceA.id)).toEqual(identitiesABefore)
    expect(await identities(b.page, workspaceB.id)).toEqual(identitiesBBefore)
  })

  test("@prod foreign project and identity paths reject conflicting workspace context", async () => {
    const { a, workspaceA, workspaceB } = harness
    const projectMembers = await api(
      a.page,
      `/projects/${workspaceB.id}/members`,
      "GET",
      undefined,
      workspaceA.id,
    )
    expect([403, 404]).toContain(projectMembers.status())

    const identityList = await api(
      a.page,
      `/workspaces/${workspaceB.id}/agent-identities`,
      "GET",
      undefined,
      workspaceA.id,
    )
    expect([403, 404]).toContain(identityList.status())
  })

  test("@prod environment CRUD remains isolated to its workspace", async () => {
    const { a, b, workspaceA, workspaceB } = harness
    const before = await environments(b.page, workspaceB.id)
    const created = await api(
      b.page,
      "/environments",
      "POST",
      { name: `${runPrefix}-environment` },
      workspaceB.id,
    )
    expect(created.status()).toBe(201)
    const environment = await created.json() as Environment

    try {
      expect((await environments(b.page, workspaceB.id)).some(row => row.id === environment.id)).toBe(true)
      expect((await environments(a.page, workspaceA.id)).some(row => row.id === environment.id)).toBe(false)

      const foreignUpdate = await api(
        a.page,
        `/environments/${environment.id}`,
        "PATCH",
        { allowed_hosts: ["example.invalid"] },
        workspaceA.id,
      )
      expect(foreignUpdate.status()).toBe(404)
    } finally {
      const removed = await api(b.page, `/environments/${environment.id}`, "DELETE", undefined, workspaceB.id)
      expect(removed.status()).toBe(204)
    }
    expect(await environments(b.page, workspaceB.id)).toEqual(before)
  })

  test("@prod identity creation rejects an environment from another workspace", async () => {
    const { a, b, workspaceA, workspaceB } = harness
    const identitiesBefore = await identities(a.page, workspaceA.id)
    const created = await api(
      b.page,
      "/environments",
      "POST",
      { name: `${runPrefix}-foreign-environment` },
      workspaceB.id,
    )
    expect(created.status()).toBe(201)
    const environment = await created.json() as Environment
    let unexpectedIdentityId: string | undefined

    try {
      const rejected = await api(
        a.page,
        `/workspaces/${workspaceA.id}/agent-identities`,
        "POST",
        { name: `${runPrefix}-must-not-exist`, environment_id: environment.id },
        workspaceA.id,
      )
      if (rejected.status() === 201) {
        unexpectedIdentityId = (await rejected.json() as Identity).id
      }
      expect(rejected.status()).toBe(404)
      expect(await identities(a.page, workspaceA.id)).toEqual(identitiesBefore)
    } finally {
      if (unexpectedIdentityId) {
        await removeIdentity(a.page, workspaceA.id, unexpectedIdentityId)
      }
      const removed = await api(b.page, `/environments/${environment.id}`, "DELETE", undefined, workspaceB.id)
      expect(removed.status()).toBe(204)
    }
  })

  test("@prod run-token lookup rejects an identity from another workspace", async () => {
    const { a, b, workspaceA, workspaceB } = harness
    const before = await identities(b.page, workspaceB.id)
    const created = await api(
      b.page,
      `/workspaces/${workspaceB.id}/agent-identities`,
      "POST",
      { name: `${runPrefix}-foreign-identity` },
      workspaceB.id,
    )
    expect(created.status()).toBe(201)
    const identity = await created.json() as Identity

    try {
      const rejected = await api(
        a.page,
        `/workspaces/${workspaceA.id}/agent-identities/${identity.id}/run-tokens`,
        "GET",
        undefined,
        workspaceA.id,
      )
      expect(rejected.status()).toBe(404)
    } finally {
      await removeIdentity(b.page, workspaceB.id, identity.id)
    }
    expect(await identities(b.page, workspaceB.id)).toEqual(before)
  })

  test("@prod refresh tokens rotate and reject replay", async () => {
    const { a, b, workspaceB, originalMembersB } = harness
    await addMember(b, workspaceB.id, a.userId)
    try {
      const issued = await exchange(a.page, workspaceB.id)
      expect(issued.status()).toBe(200)
      const pair = await issued.json()
      expect(typeof pair.refresh_token === "string" && pair.refresh_token.startsWith("cond_ref_")).toBe(true)

      const rotated = await refresh(a.page, pair.refresh_token)
      expect(rotated.status()).toBe(200)
      const rotatedPair = await rotated.json()
      expect(typeof rotatedPair.refresh_token === "string" && rotatedPair.refresh_token.startsWith("cond_ref_")).toBe(true)
      expect(rotatedPair.refresh_token).not.toBe(pair.refresh_token)

      const replay = await refresh(a.page, pair.refresh_token)
      expect([401, 403]).toContain(replay.status())
    } finally {
      await removeMember(b, workspaceB.id, a.userId)
    }
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
  })

  test("@prod member removal revokes access, refresh, and new issuance", async () => {
    const { a, b, workspaceB, originalMembersB } = harness
    await addMember(b, workspaceB.id, a.userId)
    let removed = false
    try {
      const issued = await exchange(a.page, workspaceB.id)
      expect(issued.status()).toBe(200)
      const pair = await issued.json()
      expect((await mcp(a.page, workspaceB.id, pair.access_token)).status()).toBe(200)

      await removeMember(b, workspaceB.id, a.userId)
      removed = true
      expect([401, 403]).toContain((await mcp(a.page, workspaceB.id, pair.access_token)).status())
      expect([401, 403]).toContain((await refresh(a.page, pair.refresh_token)).status())
      expect((await exchange(a.page, workspaceB.id)).status()).toBe(403)
    } finally {
      if (!removed) await removeMember(b, workspaceB.id, a.userId).catch(() => undefined)
    }
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
  })

  test("@prod malformed and retired Conduct token formats are rejected", async () => {
    const { a, workspaceA } = harness
    for (const token of [
      `cond_live_${randomUUID().replaceAll("-", "")}`,
      `cond_agt_${randomUUID().replaceAll("-", "")}`,
      `cond_api_${randomUUID().replaceAll("-", "")}`,
    ]) {
      expect((await mcp(a.page, workspaceA.id, token)).status()).toBe(401)
    }
  })

  test("@prod issued access token is bound to its workspace", async () => {
    const { a, workspaceA, workspaceB } = harness
    const issued = await exchange(a.page, workspaceA.id)
    expect(issued.status()).toBe(200)
    const pair = await issued.json()

    expect((await mcp(a.page, workspaceA.id, pair.access_token)).status()).toBe(200)
    expect([401, 403]).toContain((await mcp(a.page, workspaceB.id, pair.access_token)).status())
    expect([401, 403]).toContain((await mcp(a.page, randomUUID(), pair.access_token)).status())
  })

  test("@prod foreign identity metadata, regeneration, and deletion are denied", async () => {
    const { a, b, workspaceA, workspaceB } = harness
    const before = await identities(b.page, workspaceB.id)
    const created = await api(
      b.page,
      `/workspaces/${workspaceB.id}/agent-identities`,
      "POST",
      { name: `${runPrefix}-foreign-mutations` },
      workspaceB.id,
    )
    expect(created.status()).toBe(201)
    const identity = await created.json() as Identity
    const expected = await identities(b.page, workspaceB.id)

    try {
      const attacks: [string, string, unknown][] = [
        [`/workspaces/${workspaceA.id}/agent-identities/${identity.id}`, "PATCH", { risk_tier: "tier_3" }],
        [`/workspaces/${workspaceA.id}/agent-identities/${identity.id}/regenerate`, "POST", undefined],
        [`/workspaces/${workspaceA.id}/agent-identities/${identity.id}`, "DELETE", undefined],
      ]
      for (const [path, method, body] of attacks) {
        const rejected = await api(a.page, path, method, body, workspaceA.id)
        expect([403, 404]).toContain(rejected.status())
      }
      expect(await identities(b.page, workspaceB.id)).toEqual(expected)
    } finally {
      await removeIdentity(b.page, workspaceB.id, identity.id)
    }
    expect(await identities(b.page, workspaceB.id)).toEqual(before)
  })

  test("@prod foreign environment deletion is denied", async () => {
    const { a, b, workspaceA, workspaceB } = harness
    const before = await environments(b.page, workspaceB.id)
    const created = await api(
      b.page,
      "/environments",
      "POST",
      { name: `${runPrefix}-foreign-delete` },
      workspaceB.id,
    )
    expect(created.status()).toBe(201)
    const environment = await created.json() as Environment

    try {
      const rejected = await api(
        a.page,
        `/environments/${environment.id}`,
        "DELETE",
        undefined,
        workspaceA.id,
      )
      expect([403, 404]).toContain(rejected.status())
      expect((await environments(b.page, workspaceB.id)).some(row => row.id === environment.id)).toBe(true)
    } finally {
      const removed = await api(b.page, `/environments/${environment.id}`, "DELETE", undefined, workspaceB.id)
      expect(removed.status()).toBe(204)
    }
    expect(await environments(b.page, workspaceB.id)).toEqual(before)
  })

  test("@prod owned environment updates normalize and cleanly restore", async () => {
    const { a, workspaceA } = harness
    const before = await environments(a.page, workspaceA.id)
    const created = await api(
      a.page,
      "/environments",
      "POST",
      { name: `${runPrefix}-owned-update` },
      workspaceA.id,
    )
    expect(created.status()).toBe(201)
    const environment = await created.json() as Environment

    try {
      const updated = await api(
        a.page,
        `/environments/${environment.id}`,
        "PATCH",
        { allowed_hosts: [" EXAMPLE.INVALID "] },
        workspaceA.id,
      )
      expect(updated.status()).toBe(200)
      expect((await updated.json()).allowed_hosts).toEqual(["example.invalid"])
    } finally {
      const removed = await api(a.page, `/environments/${environment.id}`, "DELETE", undefined, workspaceA.id)
      expect(removed.status()).toBe(204)
    }
    expect(await environments(a.page, workspaceA.id)).toEqual(before)
  })

  test("@prod concurrent refresh permits only one rotation", async () => {
    const { a, b, workspaceB, originalMembersB } = harness
    await addMember(b, workspaceB.id, a.userId)
    try {
      const issued = await exchange(a.page, workspaceB.id)
      expect(issued.status()).toBe(200)
      const pair = await issued.json()
      const attempts = await Promise.all([
        refresh(a.page, pair.refresh_token),
        refresh(a.page, pair.refresh_token),
      ])
      const statuses = attempts.map(response => response.status())
      expect(statuses.filter(status => status === 200)).toHaveLength(1)
      expect(statuses.filter(status => [401, 403].includes(status))).toHaveLength(1)
    } finally {
      await removeMember(b, workspaceB.id, a.userId).catch(() => undefined)
    }
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
  })

  test("@prod role downgrade immediately removes policy-write permission", async () => {
    const { a, b, workspaceB, originalMembersB } = harness
    const before = await policies(b.page, workspaceB.id)
    const ruleId = `${runPrefix}-role-policy`
    let created = false
    await addMember(b, workspaceB.id, a.userId)
    try {
      await setMemberRole(b, workspaceB.id, a.userId, "security")
      await policies(a.page, workspaceB.id)
      await setMemberRole(b, workspaceB.id, a.userId, "viewer")
      await policies(a.page, workspaceB.id)

      const denied = await api(
        a.page,
        "/guard/policies",
        "POST",
        { rule_id: ruleId, action: "block", match_pattern: "prod-e2e-never" },
        workspaceB.id,
      )
      expect(denied.status()).toBe(403)

      await setMemberRole(b, workspaceB.id, a.userId, "security")
      const allowed = await api(
        a.page,
        "/guard/policies",
        "POST",
        { rule_id: ruleId, action: "block", match_pattern: "prod-e2e-never" },
        workspaceB.id,
      )
      expect(allowed.status()).toBe(201)
      created = true
    } finally {
      if (created) await removePolicy(b.page, workspaceB.id, ruleId).catch(() => undefined)
      await removeMember(b, workspaceB.id, a.userId).catch(() => undefined)
    }
    expect(await policies(b.page, workspaceB.id)).toEqual(before)
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
  })

  test("@prod policy body cannot redirect a write into another workspace", async () => {
    const { a, b, workspaceA, workspaceB } = harness
    const before = await policies(b.page, workspaceB.id)
    const ruleId = `${runPrefix}-foreign-policy`
    const response = await api(
      a.page,
      "/guard/policies",
      "POST",
      { rule_id: ruleId, action: "block", workspace_id: workspaceB.id },
      workspaceA.id,
    )
    if (response.status() === 201) {
      await removePolicy(b.page, workspaceB.id, ruleId).catch(() => undefined)
    }
    expect([403, 404]).toContain(response.status())
    expect(await policies(b.page, workspaceB.id)).toEqual(before)
  })

  test("@prod API token is workspace-bound and deletion revokes it", async () => {
    const { a, workspaceA, workspaceB } = harness
    const before = await apiTokens(a.page, workspaceA.id)
    const created = await createApiToken(a.page, workspaceA.id, `${runPrefix}-api-revoke`)
    let removed = false
    try {
      expect(created.token.startsWith("cond_api_")).toBe(true)
      expect((await mcp(a.page, workspaceA.id, created.token)).status()).toBe(200)
      expect([401, 403]).toContain((await mcp(a.page, workspaceB.id, created.token)).status())
      await removeApiToken(a.page, workspaceA.id, created.id)
      removed = true
      expect((await mcp(a.page, workspaceA.id, created.token)).status()).toBe(401)
    } finally {
      if (!removed) await removeApiToken(a.page, workspaceA.id, created.id).catch(() => undefined)
    }
    expect(await apiTokens(a.page, workspaceA.id)).toEqual(before)
  })

  test("@prod API token deactivation and reactivation take effect immediately", async () => {
    const { a, workspaceA } = harness
    const before = await apiTokens(a.page, workspaceA.id)
    const created = await createApiToken(a.page, workspaceA.id, `${runPrefix}-api-lifecycle`)
    try {
      expect((await mcp(a.page, workspaceA.id, created.token)).status()).toBe(200)
      const deactivated = await api(
        a.page,
        `/workspaces/${workspaceA.id}/agent-identities/${created.id}`,
        "PATCH",
        { lifecycle_state: "deactivated" },
        workspaceA.id,
      )
      expect(deactivated.status()).toBe(200)
      expect((await mcp(a.page, workspaceA.id, created.token)).status()).toBe(401)

      const reactivated = await api(
        a.page,
        `/workspaces/${workspaceA.id}/agent-identities/${created.id}`,
        "PATCH",
        { lifecycle_state: "active" },
        workspaceA.id,
      )
      expect(reactivated.status()).toBe(200)
      expect((await mcp(a.page, workspaceA.id, created.token)).status()).toBe(200)
    } finally {
      await removeApiToken(a.page, workspaceA.id, created.id).catch(() => undefined)
    }
    expect(await apiTokens(a.page, workspaceA.id)).toEqual(before)
  })

  test("@prod membership changes produce tenant-scoped audit evidence", async () => {
    const { a, b, workspaceA, workspaceB, originalMembersB } = harness
    const beforeIds = new Set((await auditLog(b.page, workspaceB.id)).map(entry => entry.id))
    await addMember(b, workspaceB.id, a.userId)
    try {
      await setMemberRole(b, workspaceB.id, a.userId, "security")
      const newEntries = (await auditLog(b.page, workspaceB.id)).filter(entry => !beforeIds.has(entry.id))
      expect(newEntries).toContainEqual(expect.objectContaining({
        actor_id: b.userId,
        action: "member.role_changed",
        resource_id: a.userId,
      }))
      const foreign = await api(
        a.page,
        `/workspaces/${workspaceB.id}/audit-log?limit=1`,
        "GET",
        undefined,
        workspaceA.id,
      )
      expect([403, 404]).toContain(foreign.status())
    } finally {
      await removeMember(b, workspaceB.id, a.userId).catch(() => undefined)
    }
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
  })

  test("@prod membership can be safely restored after revocation", async () => {
    const { a, b, workspaceB, originalMembersB } = harness
    let present = false
    await addMember(b, workspaceB.id, a.userId)
    present = true
    try {
      expect((await exchange(a.page, workspaceB.id)).status()).toBe(200)
      await removeMember(b, workspaceB.id, a.userId)
      present = false
      expect((await exchange(a.page, workspaceB.id)).status()).toBe(403)

      await addMember(b, workspaceB.id, a.userId)
      present = true
      const restored = await exchange(a.page, workspaceB.id)
      expect(restored.status()).toBe(200)
      const pair = await restored.json()
      expect((await mcp(a.page, workspaceB.id, pair.access_token)).status()).toBe(200)
    } finally {
      if (present) await removeMember(b, workspaceB.id, a.userId).catch(() => undefined)
    }
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
  })

  test("@prod foreign member mutations and owner self-removal are denied", async () => {
    const { a, b, workspaceA, workspaceB, originalMembersB } = harness
    const foreignRole = await api(
      a.page,
      `/projects/${workspaceB.id}/members/${b.userId}`,
      "PATCH",
      { role: "viewer" },
      workspaceA.id,
    )
    expect([403, 404]).toContain(foreignRole.status())

    const foreignRemoval = await api(
      a.page,
      `/projects/${workspaceB.id}/members/${b.userId}`,
      "DELETE",
      undefined,
      workspaceA.id,
    )
    expect([403, 404]).toContain(foreignRemoval.status())

    const selfRemoval = await api(
      b.page,
      `/projects/${workspaceB.id}/members/${b.userId}`,
      "DELETE",
      undefined,
      workspaceB.id,
    )
    expect(selfRemoval.status()).toBe(400)
    expect(await members(b.page, workspaceB.id)).toEqual(originalMembersB)
  })
})
