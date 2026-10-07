// Production canaries: Gateway fixture/inference paths and Flight Recorder.
import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { publishedCatalogModels, restorationPlan } from "./gateway-fixture"
import {
  type GuardEvent,
  apiBase,
  api,
  exchange,
  canonicalGatewayProfile,
  gatewayToken,
  guardEvents,
  waitForGuardEvent,
  expectNoCredentialMaterial,
  useProductionHarness,
} from "./security-support"

test.describe("bounded production security canaries", () => {
  const harness = useProductionHarness()
  const runPrefix = `prod-e2e-${randomUUID().slice(0, 8)}`

  test("@prod-gateway-fixture published profiles are ready", async () => {
    const { a, b, workspaceA, workspaceB } = harness
    if (process.env.PROD_E2E_RESTORE_GATEWAY_FIXTURES === "1") {
      const plans = []
      const errors: string[] = []
      for (const [session, workspace, provider] of [[a, workspaceA, "anthropic"], [b, workspaceB, "openai"]] as const) {
        const read = async (path: string) => {
          const response = await api(session.page, path, "GET", undefined, workspace.id)
          expect(response.status(), "Fixture metadata read must succeed").toBe(200)
          return response.json()
        }
        try {
          plans.push({ session, workspace, plan: await restorationPlan(read, workspace.id, provider, process.env[`PROD_E2E_FIXTURE_${provider.toUpperCase()}_MODEL`]) })
        } catch (error) {
          errors.push(error instanceof Error ? error.message : "Fixture metadata validation failed")
        }
      }
      expect(errors, errors.join("\n")).toEqual([])
      // Validate both plans before making either persistent change.
      for (const { session, workspace, plan } of plans) {
        if (!plan) continue
        const base = `/workspaces/${workspace.id}/gateway-profiles-v2`
        const created = await api(session.page, base, "POST", plan, workspace.id)
        expect(created.status(), "Create dedicated canary draft").toBe(201)
        const { id } = await created.json() as { id: string }
        const published = await api(session.page, `${base}/${id}/publish`, "POST", {}, workspace.id)
        expect(published.ok(), "Publish dedicated canary fixture; failed draft is retained for inspection").toBe(true)
        console.log("Dedicated Gateway fixture published")
      }
    }
    const errors: string[] = []
    for (const [session, workspace, provider] of [[a, workspaceA, "anthropic"], [b, workspaceB, "openai"]] as const) {
      try {
        await canonicalGatewayProfile(session.page, workspace.id, provider)
      } catch (error) {
        errors.push(error instanceof Error ? error.message : "Gateway fixture check failed")
        if (process.env.PROD_E2E_GATEWAY_PREFLIGHT === "1") {
          const response = await api(session.page, "/credentials", "GET", undefined, workspace.id)
          if (response.ok()) {
            const credentials = await response.json() as { service: string; fields: string[] }[]
            errors.push(`${provider} credential metadata: ${credentials.filter(c => c.service === provider && c.fields.includes("api_key")).length} matching API-key records. Values were not requested.`)
          } else {
            errors.push(`${provider} credential metadata unavailable (HTTP ${response.status()}).`)
          }
        }
      }
    }
    expect(errors, errors.join("\n")).toEqual([])
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

  test("@prod-gateway Claude model discovery exposes only published v2 routing IDs", async () => {
    const { a, workspaceA } = harness
    const expectedModels = await publishedCatalogModels(async path => {
      const response = await api(a.page, path, "GET", undefined, workspaceA.id)
      expect(response.status()).toBe(200)
      return response.json()
    }, workspaceA.id)
    expect(expectedModels.length).toBeGreaterThan(0)
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
    expect(body.data.map(model => model.id)).toEqual(expectedModels)
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
    const model = profile.model
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
    expect(event.routing_meta).toMatchObject({ operation: "anthropic_count_tokens", billable: false })
    expect(event.routing_meta).toMatchObject({ gateway_version: "v2", revision_id: profile.revisionId })
    expect(event.cost_usd_after).toBeNull()
    expectNoCredentialMaterial(event)
  })

  test("@prod-gateway Claude non-streaming inference records attributed billable activity", async () => {
    const { a, workspaceA } = harness
    const profile = await canonicalGatewayProfile(a.page, workspaceA.id, "anthropic")
    const model = profile.model
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
      source: "gateway",
      provider: "anthropic",
      model,
      decision: "allowed",
    })
    expect(event.routing_meta?.billable).not.toBe(false)
    expect(event.routing_meta).toMatchObject({ gateway_version: "v2", revision_id: profile.revisionId })
    expect(event.tokens_before).toBeGreaterThan(0)
    expect(event.tokens_after).toBeGreaterThan(0)
    expect(typeof event.cost_usd_after).toBe("number")
    expectNoCredentialMaterial(event)
  })

  test("@prod-gateway Claude streaming inference emits content and closes cleanly", async () => {
    const { a, workspaceA } = harness
    const profile = await canonicalGatewayProfile(a.page, workspaceA.id, "anthropic")
    const model = profile.model
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
    expect(event.routing_meta).toMatchObject({ gateway_version: "v2", revision_id: profile.revisionId })
    expectNoCredentialMaterial(event)
  })

  test("@prod-gateway OpenAI Responses inference remains functional after transport refactor", async () => {
    const { b, workspaceB } = harness
    const profile = await canonicalGatewayProfile(b.page, workspaceB.id, "openai")
    const model = profile.model
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
      source: "gateway",
      provider: "openai",
      model,
      decision: "allowed",
    })
    expect(event.routing_meta).toMatchObject({ gateway_version: "v2", revision_id: profile.revisionId })
    expectNoCredentialMaterial(event)
  })

  test("@prod-flight-recorder independent logins preserve access and refresh", async () => {
    const { a, workspaceA } = harness
    const firstResponse = await exchange(a.page, workspaceA.id)
    expect(firstResponse.status()).toBe(200)
    const first = await firstResponse.json()
    const probe = (token: string) => a.page.request.get(`${apiBase}/guard/events?workspace_id=${workspaceA.id}&limit=1`, {
      headers: { authorization: `Bearer ${token}` },
    })
    expect((await probe(first.access_token)).status()).toBe(200)
    const second = await gatewayToken(a.page, workspaceA.id)
    expect((await probe(second)).status()).toBe(200)
    expect((await probe(first.access_token)).status()).toBe(200)
    const refresh = await a.page.request.post(`${apiBase}/auth/refresh`, {
      data: { refresh_token: first.refresh_token },
    })
    expect(refresh.status()).toBe(200)
    const rotated = await refresh.json()
    expect((await probe(rotated.agent_token)).status()).toBe(200)
    expect((await probe(first.access_token)).status()).toBe(401)
    expect((await probe(second)).status()).toBe(200)
    const replay = await a.page.request.post(`${apiBase}/auth/refresh`, {
      data: { refresh_token: first.refresh_token },
    })
    expect(replay.status()).toBe(401)
  })

  test("@prod-flight-recorder new Codex event renders on live logs page", async () => {
    const { a, workspaceA } = harness
    const token = await gatewayToken(a.page, workspaceA.id)
    const streamStatuses: number[] = []
    a.page.on('response', response => {
      if (new URL(response.url()).pathname.endsWith('/guard/events/stream')) streamStatuses.push(response.status())
    })
    await a.page.goto('/logs/guard')
    const goLive = a.page.getByRole('button', { name: 'Resume realtime stream', exact: true })
    await expect(goLive).toBeVisible()
    await goLive.click()
    await expect(a.page.getByRole('button', { name: 'Pause realtime stream', exact: true })).toBeVisible()
    const marker = `${runPrefix}-live-${randomUUID().slice(0, 8)}`
    const since = new Date(Date.now() - 1000).toISOString()
    const created = await a.page.request.post(`${apiBase}/guard/events`, {
      headers: { authorization: `Bearer ${token}` },
      data: {
        workspace_id: workspaceA.id, ai_tool: 'codex-desktop', tool_call: marker,
        input_summary: 'Synthetic Flight Recorder display check', decision: 'allowed',
        hook_session_id: marker,
      },
    })
    expect(created.status()).toBe(201)
    const event = await waitForGuardEvent(a.page, workspaceA.id, since, row => row.hook_session_id === marker)
    expect(event.ai_tool).toBe('codex-desktop')
    try {
      await expect(a.page.getByText(marker, { exact: true }).first()).toBeVisible({ timeout: 15_000 })
    } finally {
      console.log('Flight Recorder SSE HTTP statuses:', JSON.stringify(streamStatuses))
    }
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
})
