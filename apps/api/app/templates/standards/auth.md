# Standard: Auth and Access Control

Every API endpoint must authenticate the caller before doing any work.

## The rule
No exceptions by default. Public endpoints go in an explicit, CI-checked allowlist
with a documented reason.

## The pattern
Use your framework's dependency injection for auth:

```python
# FastAPI
@router.get("/resource")
def get_resource(
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("resource.read")),
    db: Session = Depends(get_db),
):
    ...
```

Use permission names, not role names. Hardcoding `require_role("admin")` couples
endpoints to your current role structure. Permissions decouple them.

## The allowlist pattern
Build a CI gate that scans every route and fails on undocumented public endpoints.
Each allowlist entry must say why it's public:

```python
ALLOWLIST = {
    "routers/health.py::health",          # Load balancer health check
    "routers/github_webhook.py::webhook", # Auth via X-Hub-Signature-256
    "routers/oauth.py::metadata",         # Public by RFC 8414
}
```

## What to check in review
- [ ] New endpoint has an auth dependency
- [ ] Uses permission names, not role strings
- [ ] If no auth: in the allowlist with a reason
- [ ] CI gate passes

<!-- Layer 0: Team OS · conductai.ai/team-os -->
