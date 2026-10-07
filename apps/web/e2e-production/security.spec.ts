// Production canaries: tenant isolation, credential lifecycle and membership.
import { randomUUID } from "node:crypto"
import { expect, test } from "@playwright/test"
import { expectMcpInvocation } from "../e2e-security/support/mcp"
import {
  type Identity,
  type Environment,
  apiBase,
  api,
  members,
  identities,
  removeIdentity,
  exchange,
  environments,
  addMember,
  removeMember,
  refresh,
  mcp,
  setMemberRole,
  apiTokens,
  createApiToken,
  removeApiToken,
  policies,
  removePolicy,
  auditLog,
  useProductionHarness,
} from "./security-support"

test.describe("bounded production security canaries", () => {
  const harness = useProductionHarness()
  const runPrefix = `prod-e2e-${randomUUID().slice(0, 8)}`

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

  test("@prod owner token lists and invokes MCP tools in its workspace", async () => {
    const { a, workspaceA } = harness
    const issued = await exchange(a.page, workspaceA.id)
    expect(issued.status()).toBe(200)
    const pair = await issued.json()
    expect(typeof pair.access_token === "string" && pair.access_token.startsWith("cond_agt_")).toBe(true)

    const response = await mcp(a.page, workspaceA.id, pair.access_token)
    expect(response.status()).toBe(200)
    expect(Array.isArray((await response.json()).result?.tools)).toBe(true)
    await expectMcpInvocation(a.page, `${apiBase}/mcp?workspace_id=${workspaceA.id}`, pair.access_token)
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
