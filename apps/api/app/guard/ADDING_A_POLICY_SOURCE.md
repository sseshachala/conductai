# Adding a policy source

Composable policy engine — #1225. Every gate on an LLM call runs through a
`PolicySource`. Composer runs sources in order, short-circuits on first BLOCK
or APPROVAL, merges non-blocking decisions.

## Minimal source

```python
# app/guard/sources.py (or a new file — one class per concern)
from app.guard.policy_types import PolicyAction, PolicyContext, PolicyDecision


class MyPolicySource:
    @property
    def name(self) -> str:
        return "my_policy"

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        if self._violates(ctx.body):
            return PolicyDecision(
                action=PolicyAction.BLOCK,
                source=self.name,
                reason="Human-friendly explanation",
                rule_id="my_policy.example",
                extras={"error_type": "guard_my_policy"},
            )
        return PolicyDecision(action=PolicyAction.ALLOW, source=self.name)

    def _violates(self, body: dict) -> bool:
        return False
```

## Register

```python
# app/guard/sources.py — append to DEFAULT_SOURCES
DEFAULT_SOURCES = (
    RulePolicySource(),
    SpendCapPolicySource(),
    ThroughputCapPolicySource(),
    MyPolicySource(),
)
```

Every call through `evaluate_composed(ctx)` now runs your source. `_proxy()`
untouched.

## Custom error envelope (optional)

Add a branch in `_proxy_helpers.render_block` dispatching on `decision.source`:

```python
if source == "my_policy":
    background.add_task(
        record_audit_fn, workspace_id, clerk_user_id, ai_tool, provider, model,
        "my_policy_hit", None, duration_ms,
        body=body, response_bytes=None,
        prompt_summary=prompt_summary, user_email=user_email,
    )
    return JSONResponse(
        status_code=422,
        content={"error": {
            "type": "guard_my_policy",
            "message": decision.reason,
        }},
    )
```

Or skip — fallback returns 403 with `decision.reason`.

## Testing

Constructor DI for hermetic tests:

```python
def test_my_policy_blocks():
    fake_checker = lambda body: True
    source = MyPolicySource(checker=fake_checker)
    ctx = PolicyContext(
        workspace_id="ws-1", provider="openai", model="gpt-4o-mini",
        body={"messages": [{"role": "user", "content": "x"}]},
    )
    d = source.evaluate(ctx)
    assert d.action == PolicyAction.BLOCK
```

## Ordering

`DEFAULT_SOURCES` tuple order. Cheap first, expensive last:

1. Content regex (no I/O)
2. DB read
3. Redis / external HTTP
4. LLM classifier

Composer short-circuits on BLOCK/APPROVAL — ordering saves downstream work.

## Example — DLP source (SSN detection)

```python
import re
from app.guard.policy_types import PolicyAction, PolicyContext, PolicyDecision

_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


class DlpPolicySource:
    @property
    def name(self) -> str:
        return "dlp"

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        text = " ".join(
            msg.get("content", "")
            for msg in ctx.body.get("messages", [])
            if isinstance(msg.get("content"), str)
        )
        if _SSN.search(text):
            return PolicyDecision(
                action=PolicyAction.BLOCK,
                source=self.name,
                reason="SSN detected in prompt",
                rule_id="dlp.ssn",
                extras={"error_type": "guard_dlp_violation"},
            )
        return PolicyDecision(action=PolicyAction.ALLOW, source=self.name)
```

Add to `DEFAULT_SOURCES`. Done.
