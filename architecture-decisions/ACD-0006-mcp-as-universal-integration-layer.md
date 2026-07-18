# ACD-0006 — MCP as Universal Integration Layer

**Status:** Accepted  
**Date:** July 18, 2026  
**Deciders:** Sudhendra Seshachala  
**Issue:** #946

---

## Context

Conduct workflows call external services — GitHub, Slack, Linear, customer internal tools — through hand-written REST API wrappers in the tool engine. Every new integration requires writing, testing, and maintaining a custom wrapper. When a vendor changes their API, the wrapper breaks.

This creates three compounding problems:

1. **Integration tax** — every new service = weeks of wrapper work before a workflow can use it
2. **Duplication** — the same `POST /issues` call is written 6 times across 6 playbooks
3. **Blind spot** — customers with internal tools (Salesforce, proprietary deployment systems) cannot connect them to Conduct without waiting for us to write a wrapper

The Model Context Protocol (MCP) solves all three. MCP is an open standard for exposing service capabilities as typed tools that any MCP client can discover and call. Official MCP servers exist for GitHub, Slack, Git, and Linear. Any vendor can publish an MCP server. Customers can bring their own.

---

## Decision

**MCP is the default integration layer for all Conduct workflow integrations.**

- No new REST API wrappers will be written
- Existing REST wrappers are deprecated and replaced incrementally as MCP servers are wired in
- New integrations start by finding or building an MCP server — never by writing a REST wrapper
- Customers can connect their own MCP servers; Conduct automatically exposes those tools to workflows

**Three categories of integration going forward:**

```
1. Official MCP server exists  →  connect, zero code (GitHub, Slack, Git, Linear)
2. No MCP server yet           →  build a thin MCP server once, reusable everywhere
3. Customer internal tools     →  customer brings MCP server, Conduct connects automatically
```

**Engine change:** The brain block acts as an MCP client. At session start it connects to the MCP servers declared in the workflow's `mcp_servers:` block, fetches their tool manifests, and exposes those tools to the LLM alongside built-in BRAIN_TOOLS. Tool calls are namespaced: `github::create_pr`, `slack::post_message`.

**Credential model is unchanged:** Users still provide `GITHUB_TOKEN`, `SLACK_BOT_TOKEN` etc. as environment variables. The runtime injects them into the MCP server process at session start — same vault, same flow as E2B sandbox credential injection.

**Guard governance is unchanged:** All MCP tool calls pass through the Guard policy engine before execution. Agent rules gain MCP-aware matching (`match_mcp_server`, `match_tool`) alongside existing shell/filesystem rules. The proxy layer is unaffected — it intercepts LLM requests, not tool calls.

---

## Consequences

**Positive:**
- New integrations: hours (connect MCP server) not weeks (write REST wrapper)
- Customer internal tools become Conduct integrations automatically — zero code on our side
- Structured typed inputs replace shell string parsing — no injection surface, reliable LLM tool use
- Audit trail becomes structured: `github::create_pr → pr_number=847` not `run_shell "gh pr create ..."`
- 13 duplicate REST patterns in playbooks collapse to single canonical MCP tool calls (~20% YAML reduction)
- LLM hallucinations on tool calls decrease — typed schemas give better signal than raw shell strings

**Negative:**
- MCP server must be running and reachable at workflow execution time
- Community MCP servers vary in quality — need vetting before production use
- Migration of 13 existing playbooks is required (estimated ~2-3 days)

**Mitigations:**
- Official MCP servers (GitHub, Slack, Git) are maintained by the vendors — reliability matches their APIs
- MCP server health check at workflow start, fail-fast before execution begins
- Incremental migration — `type: tool` and `type: mcp` blocks coexist during transition, no flag day

---

## Alternatives Considered

**Keep REST wrappers, add MCP as optional:** Rejected — two integration paths means double maintenance. The point is to eliminate the REST wrapper path entirely.

**Build a proprietary integration abstraction:** Rejected — MCP is the emerging standard. Building a proprietary layer creates a migration problem later and closes off the ecosystem of existing MCP servers.

**GraphQL federation instead of MCP:** Rejected — MCP is purpose-built for AI agent tool use. GraphQL requires schema stitching and does not have the LLM tool-calling semantics that MCP provides natively.
