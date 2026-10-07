// Security journeys: @prod-canary tenant isolation and credential lifecycle canaries.
import { randomBytes } from "node:crypto"
import { test, expect, type BrowserContext } from "@playwright/test"
import {
  type Environment,
  type Identity,
  prefix,
  base,
  account,
  login,
  api,
  workspace,
  projects,
  members,
  environments,
  identities,
  exchange,
  expectUsableToken,
  guardEvent,
  registerJourneyHooks,
} from "./support/journeys"

registerJourneyHooks()

test('@prod-canary account owns a distinct disposable workspace', async ({ browser }) => {
  const owner = await account('cown')
  const session = await login(browser, owner)
  try {
    const ws = await workspace(session.page, 'canary-owned')
    expect(ws.owner_id).toBe(owner.id)
    expect((await projects(session.page)).filter(project => project.id === ws.id)).toEqual([ws])
  } finally { await session.context.close() }
})

test('@prod-canary anonymous forged forwarding headers do not authenticate', async ({ request }) => {
  const response = await request.get('/api/projects', { headers: {
    'X-Workspace-Id': crypto.randomUUID(),
    'X-Forwarded-For': '127.0.0.1',
    'X-Real-IP': '127.0.0.1',
    'X-Forwarded-Proto': 'https',
  } })
  expect(response.status()).toBe(401)
})

test('@prod-canary owner token lists MCP tools only for its workspace', async ({ browser }) => {
  const owner = await account('cmcp')
  const session = await login(browser, owner)
  try {
    const ws = await workspace(session.page, 'canary-mcp')
    await expectUsableToken(session.page, ws.id)
  } finally { await session.context.close() }
})

test('@prod-canary foreign and unknown workspaces cannot issue credentials', async ({ browser }) => {
  const ownerA = await account('cia')
  const ownerB = await account('cib')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, ownerA); contexts.push(a.context)
    const b = await login(browser, ownerB); contexts.push(b.context)
    const wa = await workspace(a.page, 'canary-issue-a')
    const wb = await workspace(b.page, 'canary-issue-b')
    const identitiesA = await identities(a.page, wa.id)
    const identitiesB = await identities(b.page, wb.id)
    const membersB = await members(b.page, wb.id)

    expect((await exchange(a.page, wb.id)).status()).toBe(403)
    expect((await exchange(a.page, crypto.randomUUID())).status()).toBe(403)
    expect(await identities(a.page, wa.id)).toEqual(identitiesA)
    expect(await identities(b.page, wb.id)).toEqual(identitiesB)
    expect(await members(b.page, wb.id)).toEqual(membersB)
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary foreign resource paths reject conflicting workspace context', async ({ browser }) => {
  const ownerA = await account('cpa')
  const ownerB = await account('cpb')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, ownerA); contexts.push(a.context)
    const b = await login(browser, ownerB); contexts.push(b.context)
    const wa = await workspace(a.page, 'canary-path-a')
    const wb = await workspace(b.page, 'canary-path-b')
    const projectMembers = await api(a.page, `/projects/${wb.id}/members`, 'GET', undefined, wa.id)
    const identityList = await api(a.page, `/workspaces/${wb.id}/agent-identities`, 'GET', undefined, wa.id)
    expect([403, 404]).toContain(projectMembers.status())
    expect([403, 404]).toContain(identityList.status())
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary environment CRUD remains isolated to its workspace', async ({ browser }) => {
  const ownerA = await account('cea')
  const ownerB = await account('ceb')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, ownerA); contexts.push(a.context)
    const b = await login(browser, ownerB); contexts.push(b.context)
    const wa = await workspace(a.page, 'canary-env-a')
    const wb = await workspace(b.page, 'canary-env-b')
    const before = await environments(b.page, wb.id)
    const created = await api(b.page, '/environments', 'POST', { name: `${prefix}-canary-env` }, wb.id)
    expect(created.status()).toBe(201)
    const environment = await created.json() as Environment
    try {
      expect((await environments(b.page, wb.id)).some(row => row.id === environment.id)).toBe(true)
      expect((await environments(a.page, wa.id)).some(row => row.id === environment.id)).toBe(false)
      const foreignUpdate = await api(a.page, `/environments/${environment.id}`, 'PATCH', {
        allowed_hosts: ['example.invalid'],
      }, wa.id)
      expect(foreignUpdate.status()).toBe(404)
    } finally {
      expect((await api(b.page, `/environments/${environment.id}`, 'DELETE', undefined, wb.id)).status()).toBe(204)
    }
    expect(await environments(b.page, wb.id)).toEqual(before)
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary identity creation rejects an environment from another workspace', async ({ browser }) => {
  const ownerA = await account('cra')
  const ownerB = await account('crb')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, ownerA); contexts.push(a.context)
    const b = await login(browser, ownerB); contexts.push(b.context)
    const wa = await workspace(a.page, 'canary-ref-a')
    const wb = await workspace(b.page, 'canary-ref-b')
    const before = await identities(a.page, wa.id)
    const created = await api(b.page, '/environments', 'POST', { name: `${prefix}-foreign-env` }, wb.id)
    expect(created.status()).toBe(201)
    const environment = await created.json() as Environment
    try {
      const rejected = await api(a.page, `/workspaces/${wa.id}/agent-identities`, 'POST', {
        name: `${prefix}-must-not-exist`, environment_id: environment.id,
      }, wa.id)
      expect(rejected.status()).toBe(404)
      expect(await identities(a.page, wa.id)).toEqual(before)
    } finally {
      expect((await api(b.page, `/environments/${environment.id}`, 'DELETE', undefined, wb.id)).status()).toBe(204)
    }
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary run-token lookup rejects an identity from another workspace', async ({ browser }) => {
  const ownerA = await account('cta')
  const ownerB = await account('ctb')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, ownerA); contexts.push(a.context)
    const b = await login(browser, ownerB); contexts.push(b.context)
    const wa = await workspace(a.page, 'canary-token-a')
    const wb = await workspace(b.page, 'canary-token-b')
    const before = await identities(b.page, wb.id)
    const created = await api(b.page, `/workspaces/${wb.id}/agent-identities`, 'POST', {
      name: `${prefix}-foreign-identity`,
    }, wb.id)
    expect(created.status()).toBe(201)
    const identity = await created.json() as Identity
    try {
      const rejected = await api(
        a.page,
        `/workspaces/${wa.id}/agent-identities/${identity.id}/run-tokens`,
        'GET',
        undefined,
        wa.id,
      )
      expect(rejected.status()).toBe(404)
    } finally {
      expect((await api(
        b.page,
        `/workspaces/${wb.id}/agent-identities/${identity.id}`,
        'DELETE',
        undefined,
        wb.id,
      )).status()).toBe(204)
    }
    expect(await identities(b.page, wb.id)).toEqual(before)
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary refresh tokens rotate and reject replay', async ({ browser }) => {
  const owner = await account('rpa')
  const member = await account('rpb')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, owner); contexts.push(a.context)
    const m = await login(browser, member); contexts.push(m.context)
    const ws = await workspace(a.page, 'canary-replay')
    expect((await api(a.page, `/projects/${ws.id}/members`, 'POST', {
      clerk_user_id: member.id, role: 'developer',
    }, ws.id)).status()).toBe(201)
    try {
      const issued = await exchange(m.page, ws.id)
      expect(issued.status()).toBe(200)
      const pair = await issued.json()
      const rotated = await m.page.request.post(`${base}/api/oauth/token`, { form: {
        grant_type: 'refresh_token', refresh_token: pair.refresh_token,
      } })
      expect(rotated.status()).toBe(200)
      const rotatedPair = await rotated.json()
      expect(rotatedPair.refresh_token).not.toBe(pair.refresh_token)
      const replay = await m.page.request.post(`${base}/api/oauth/token`, { form: {
        grant_type: 'refresh_token', refresh_token: pair.refresh_token,
      } })
      expect([401, 403]).toContain(replay.status())
    } finally {
      await api(a.page, `/projects/${ws.id}/members/${member.id}`, 'DELETE', undefined, ws.id)
    }
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary member removal revokes existing access, refresh, and issuance', async ({ browser }) => {
  const owner = await account('rva')
  const member = await account('rvb')
  const contexts: BrowserContext[] = []
  try {
    const a = await login(browser, owner); contexts.push(a.context)
    const m = await login(browser, member); contexts.push(m.context)
    const ws = await workspace(a.page, 'canary-revoke')
    expect((await api(a.page, `/projects/${ws.id}/members`, 'POST', {
      clerk_user_id: member.id, role: 'developer',
    }, ws.id)).status()).toBe(201)
    const issued = await exchange(m.page, ws.id)
    expect(issued.status()).toBe(200)
    const pair = await issued.json()
    expect((await m.page.request.post(`${base}/api/guard/mcp?workspace_id=${ws.id}`, {
      headers: { Authorization: `Bearer ${pair.access_token}` },
      data: { jsonrpc: '2.0', id: 1, method: 'tools/list', params: {} },
    })).status()).toBe(200)

    expect((await api(a.page, `/projects/${ws.id}/members/${member.id}`, 'DELETE', undefined, ws.id)).status()).toBe(204)
    const oldAccess = await m.page.request.post(`${base}/api/guard/mcp?workspace_id=${ws.id}`, {
      headers: { Authorization: `Bearer ${pair.access_token}` },
      data: { jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} },
    })
    const oldRefresh = await m.page.request.post(`${base}/api/oauth/token`, { form: {
      grant_type: 'refresh_token', refresh_token: pair.refresh_token,
    } })
    expect([401, 403]).toContain(oldAccess.status())
    expect([401, 403]).toContain(oldRefresh.status())
    expect((await exchange(m.page, ws.id)).status()).toBe(403)
    expect((await members(a.page, ws.id)).some(row => row.clerk_user_id === member.id)).toBe(false)
  } finally { await Promise.all(contexts.map(context => context.close())) }
})

test('@prod-canary Codex Flight Recorder persists correlated pre/post events', async ({ browser }) => {
  const owner = await account('frc')
  const session = await login(browser, owner)
  try {
    const ws = await workspace(session.page, 'canary-flight-recorder')
    expect((await api(session.page, '/guard/config', 'GET', undefined, ws.id)).status()).toBe(200)
    const issued = await exchange(session.page, ws.id)
    expect(issued.status()).toBe(200)
    const { access_token: accessToken } = await issued.json() as { access_token: string }
    const hookSessionId = `canary-${randomBytes(12).toString('hex')}`
    const common = {
      workspace_id: ws.id,
      ai_tool: 'codex-desktop',
      tool_call: 'read',
      decision: 'allowed',
      hook_session_id: hookSessionId,
    }
    const created = await guardEvent(session.page, accessToken, common)
    expect(created.status()).toBe(201)
    const preEvent = await created.json() as { id: string }
    const updated = await session.page.request.post(`${base}/api/guard/events/usage`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        workspace_id: ws.id, hook_session_id: hookSessionId, tool_name: 'read',
        ai_tool: 'codex-desktop', tokens_input: 7, tokens_output: 3, duration_ms: 5,
        execution_status: 'success', result_summary: 'canary complete',
      },
    })
    expect(updated.status()).toBe(200)
    expect(await updated.json()).toEqual({ updated: true })

    const listed = await session.page.request.get(`${base}/api/guard/events?workspace_id=${ws.id}&limit=50`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    expect(listed.status()).toBe(200)
    const rows = await listed.json() as Array<Record<string, unknown>>
    const pair = rows.filter(row => row.hook_session_id === hookSessionId)
    expect(pair).toHaveLength(1)
    expect(pair[0].session_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)
    expect(pair[0]).toMatchObject({ id: preEvent.id, ai_tool: 'codex-desktop', tokens_before: 7, tokens_after: 3, execution_status: 'success' })
  } finally { await session.context.close() }
})
