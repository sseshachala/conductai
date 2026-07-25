# Standard: Authentication and Access Control

**When to use this:** Any change that adds, modifies, or removes an API endpoint, route, or access check.

---

## The rule

Every API endpoint must authenticate the caller before doing any work.

No exceptions by default. If an endpoint must be public, document the reason explicitly and add it to an allowlist — not as a comment in the code, but as a named entry your CI gate checks.

---

## The pattern

Use your framework's dependency injection for auth. This makes auth mechanical and auditable:

```python
# FastAPI example
@router.get("/resource")
def get_resource(
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("resource.read")),
    db: Session = Depends(get_db),
):
    ...
```

```typescript
// Express example
router.get('/resource', authenticate, requirePermission('resource.read'), async (req, res) => {
  ...
})
```

**Use permission names, not role names.**
Hardcoding `require_role("admin")` couples your auth logic to your current role structure. Hardcoding `require_permission("resource.manage")` lets your role structure change without touching endpoints.

---

## The allowlist pattern

Every team has endpoints that are intentionally public — health checks, webhooks with their own signature validation, OAuth discovery. These are fine. The problem is undocumented public endpoints.

Build a CI gate that:
1. Scans every route definition in your codebase
2. Checks that it has an auth dependency
3. Fails if it finds one that doesn't — unless it's in an explicit allowlist

Reference implementation (Python/FastAPI): `scripts/check_auth_coverage.py` in the Team OS repo.

Your allowlist entry should say *why* it's public:

```python
ALLOWLIST = {
    # Health check — must be publicly reachable by load balancer
    "routers/health.py::health",
    # Webhook — auth via X-Hub-Signature-256 header, not Bearer
    "routers/github_webhook.py::github_webhook",
    # OAuth discovery — must be public by RFC 8414
    "routers/oauth.py::oauth_metadata",
}
```

---

## What to check in review

- [ ] New endpoint has an auth dependency in its signature
- [ ] The dependency uses permission names, not hardcoded role strings
- [ ] If it has no auth dependency, it's in the allowlist with a documented reason
- [ ] The CI gate (`check_auth_coverage.py` or equivalent) passes

---

## Common mistakes

**Trusting an upstream caller**
"This endpoint is only called by our own service, so it doesn't need auth." Upstream callers get compromised. Verify identity at the resource, every time.

**Auth in the body, not the signature**
If auth is in the request body (an API key in a JSON field), it's invisible to your CI gate and to any middleware. Use headers or framework dependencies.

**Shared secrets instead of scoped permissions**
A single `API_KEY` that grants access to everything is not auth — it's a master key. When it leaks (and it will), the blast radius is everything. Scope permissions to the minimum required for each endpoint.

---

## When Layer 2 helps

A `check_auth_coverage.py` script catches missing auth at PR time. Conduct AI Guard catches it at runtime — every request is checked against your policy before it reaches your endpoint, with a timestamped audit entry whether it was allowed or blocked.

`conductai.ai` — enforcement beyond the CI gate
