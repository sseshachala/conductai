"""Guard policy engine — pre-call rule evaluation for proxied LLM calls.

The single source of truth for \"should this LLM call be allowed?\"

Callers:
- HTTP proxy handler (app/modules/guard/routers/proxy.py) — external agents
- Lens LLM client (planned, #1218 Step 3) — in-process, dogfood

Extracted from proxy.py in #1218 Step 1a. Behavior is byte-identical to the
pre-refactor implementation; the regression harness under tests/regression/
locks that in.
"""
from __future__ import annotations

import re
import uuid

import structlog

from app.core.database import SessionLocal
from app.core.workspace_context import set_workspace_rls
from app.modules.guard.detectors.normalizer import normalize as _normalize_text
from app.modules.guard.policy_engine import (
    canonical_workspace_id as _canonical_workspace_id,
    compute_policy,
)

log = structlog.get_logger(__name__)


# ─── Constants (public — used by audit/proxy for consistent scoring) ──────────

SEVERITY_WEIGHTS = {"critical": 10, "high": 5, "medium": 3, "low": 1}
_ACTION_RANK = {"allow": 0, "audit": 1, "inject": 2, "warn": 3, "approval": 4, "block": 5}


def _defense_score(matched: list[dict]) -> int:
    return sum(SEVERITY_WEIGHTS.get((m.get("severity") or "medium").lower(), 3) for m in matched)


# ─── Prompt flattening (shared with audit-time prompt summarisation) ──────────

def flatten_prompt(body: dict) -> str:
    """Best-effort: join all user message contents for prompt-pattern matching.

    Anthropic + OpenAI share the messages[].content shape; content can be a
    string or a list of typed parts. Non-text parts are skipped.
    """
    out: list[str] = []
    for msg in body.get("messages") or []:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            out.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") in (None, "text", "input_text"):
                    text = part.get("text")
                    if text:
                        out.append(text)
    # OpenAI Responses API: input may be a plain string or a list of
    # input_message/input_text items. Instructions are part of the prompt too.
    instructions = body.get("instructions")
    if isinstance(instructions, str):
        out.append(instructions)
    response_input = body.get("input")
    if isinstance(response_input, str):
        out.append(response_input)
    elif isinstance(response_input, list):
        for item in response_input:
            if not isinstance(item, dict) or item.get("role", "user") != "user":
                continue
            content = item.get("content")
            if isinstance(content, str):
                out.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") in (None, "text", "input_text"):
                        text = part.get("text")
                        if text:
                            out.append(text)
    return "\n".join(out)


# ─── Content-source flattening (#2384, indirect prompt injection) ─────────────
#
# Rules opt in per source with ``match_content_source`` (string or list):
#   user              text the caller typed (what flatten_prompt returns; the default)
#   tool_result       content returned to the model by tools (role:"tool" /
#                     tool_result blocks / function_call_output items)
#   tool_description  tools[].description plus parameter descriptions
# Rules without the field only ever see ``user`` text, as before.

CONTENT_SOURCES = ("user", "tool_result", "tool_description")
_MAX_SOURCE_CHARS = 256_000   # bound regex work on attacker-sized tool output


def _text_parts(content) -> list[str]:
    """Text out of a string / list-of-parts content value (recursing into
    nested tool_result ``content`` lists)."""
    if isinstance(content, str):
        return [content] if content else []
    out: list[str] = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                if part:
                    out.append(part)
            elif isinstance(part, dict):
                if part.get("type") in (None, "text", "input_text", "output_text"):
                    text = part.get("text")
                    if isinstance(text, str) and text:
                        out.append(text)
                elif "content" in part and part.get("type") != "tool_use":
                    out.extend(_text_parts(part.get("content")))
    return out


def flatten_tool_results(body: dict) -> str:
    """Content returned to the model by tools, across OpenAI chat
    (``role:"tool"``/``"function"``), Anthropic (``tool_result`` blocks inside
    user turns) and OpenAI Responses (``function_call_output`` items)."""
    out: list[str] = []
    for msg in body.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") in ("tool", "function"):
            out.extend(_text_parts(msg.get("content")))
        elif isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    out.extend(_text_parts(part.get("content")))
    items = body.get("input")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("type") in ("function_call_output", "tool_result"):
                out.extend(_text_parts(item.get("output", item.get("content"))))
    return "\n".join(out)[:_MAX_SOURCE_CHARS]


def flatten_tool_descriptions(body: dict) -> str:
    """``tools[].description`` (OpenAI ``function.description`` / Anthropic
    ``description``) plus ``description`` strings inside parameter schemas,
    a known tool-poisoning carrier."""
    out: list[str] = []

    def _schema_descriptions(node, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "description" and isinstance(value, str) and value:
                    out.append(value)
                else:
                    _schema_descriptions(value, depth + 1)
        elif isinstance(node, list):
            for value in node:
                _schema_descriptions(value, depth + 1)

    for tool in body.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        desc = fn.get("description")
        if isinstance(desc, str) and desc:
            out.append(desc)
        for schema_key in ("parameters", "input_schema"):
            _schema_descriptions(fn.get(schema_key))
    return "\n".join(out)[:_MAX_SOURCE_CHARS]


def content_source_texts(body: dict, user_text: str) -> dict[str, str]:
    return {
        "user": user_text,
        "tool_result": flatten_tool_results(body),
        "tool_description": flatten_tool_descriptions(body),
    }


def rule_content_sources(rule: dict) -> list[str] | None:
    """Declared, recognised sources for a rule; None when the rule does not
    declare ``match_content_source`` (legacy user-text behaviour)."""
    declared = rule.get("match_content_source")
    if declared is None:
        return None
    if isinstance(declared, str):
        declared = [declared]
    if not isinstance(declared, list):
        return []
    return [s for s in declared if s in CONTENT_SOURCES]


def flatten_response(body: dict) -> str:
    """#1733 PR 4: extract model reply text for response-gate matching.

    Handles Anthropic (``content: [{type:'text', text:...}]``) and OpenAI
    (``choices: [{message:{content:...}}]``) shapes. Silent on unknown
    shapes — returns "" so the matcher sees an empty response and no rule
    fires accidentally.
    """
    out: list[str] = []
    # Anthropic Messages API
    content = body.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") in (None, "text"):
                text = part.get("text")
                if text:
                    out.append(text)
    elif isinstance(content, str):
        out.append(content)
    # OpenAI-compatible chat completions
    for choice in body.get("choices") or []:
        msg = choice.get("message") or {}
        c = msg.get("content")
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and part.get("type") in (None, "text"):
                    text = part.get("text")
                    if text:
                        out.append(text)
    # OpenAI Responses API: response.output[].content[].output_text.text.
    for item in body.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") in (None, "text", "output_text"):
                text = part.get("text")
                if text:
                    out.append(text)
    # Reviewer P1 #2 (2026-09-20, #2159 PR 2 follow-up) — fold tool_call
    # argument text into the response-gate's pattern surface. Without
    # this a response that contains ONLY a tool_call (assistant.content
    # is null; the payload lives in tool_calls[].function.arguments)
    # produced empty policy text and pattern rules like
    # {command: "DROP TABLE"} could never fire. Argument strings are
    # parsed as JSON and every string leaf is emitted; parse failures
    # fall back to the raw string so a broken payload still gets
    # scanned. Anthropic response shape (content:[{type:"tool_use"}])
    # gets the same treatment via the ``input`` block.
    _tool_arg_lines = _flatten_response_tool_args(body)
    if _tool_arg_lines:
        out.extend(_tool_arg_lines)
    return "\n".join(out)


def _flatten_response_tool_args(body: dict) -> list[str]:
    """Extract every string leaf from tool_call arguments / tool_use input.

    Returns a flat list of strings that the response-pattern matcher
    sees alongside the model's text content. Never raises — a malformed
    payload contributes whatever partial string values are extractable
    and the caller's pattern still gets a shot at them.
    """
    import json as _json

    def _walk_strings(node) -> list[str]:
        found: list[str] = []
        if isinstance(node, str):
            if node:
                found.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                found.extend(_walk_strings(v))
        elif isinstance(node, list):
            for v in node:
                found.extend(_walk_strings(v))
        return found

    lines: list[str] = []

    # OpenAI chat completions: choices[].message.tool_calls[].function.arguments
    for choice in body.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        msg = choice.get("message") or {}
        if not isinstance(msg, dict):
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function")
            if not isinstance(fn, dict):
                continue
            args = fn.get("arguments")
            if isinstance(args, str) and args:
                try:
                    parsed = _json.loads(args)
                except Exception:
                    # Parse failure — surface the raw text so pattern
                    # rules still see something. tools_validator would
                    # have blocked this pre-response upstream, but
                    # flatten runs on legacy shapes too.
                    lines.append(args)
                    continue
                lines.extend(_walk_strings(parsed))

    # Anthropic Messages: content:[{type:"tool_use", input:{...}}]
    for block in body.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            inp = block.get("input")
            lines.extend(_walk_strings(inp))

    return lines


# ─── Rule matching helpers ────────────────────────────────────────────────────

def _is_proxy_rule(rule: dict) -> bool:
    """True if the rule has at least one proxy-applicable matcher.
    match_pattern is proxy-applicable only when match_tool is absent
    (rules with match_tool are hook-event rules, not LLM-call rules).

    #2159 PR 2 (#2156) — match_tool_name_offered / _generated /
    _supplied are all proxy-applicable, matching on tool identity
    signals populated by the gateway.
    """
    if any(k in rule for k in (
        "match_provider", "match_model", "match_prompt",
        "match_tool_name_offered", "match_tool_name_generated",
        "match_tool_name_supplied",
    )):
        return True
    return "match_pattern" in rule and "match_tool" not in rule


def _rule_matches(
    rule: dict,
    provider: str,
    model: str,
    prompt_text: str,
    gate: str | None = "prompt",
    agent_risk_tier: str | None = None,
    tool_names_offered: list[str] | None = None,
    tool_names_generated: list[str] | None = None,
    tool_names_supplied: list[str] | None = None,
    source_texts: dict[str, str] | None = None,
    matched_source: list[str] | None = None,
) -> bool:
    """Proxy-side rule matcher. ``gate`` filters by declared rule gates —
    default ``"prompt"`` because every existing proxy caller today evaluates
    outbound prompts (pre-#1733 baseline). Pass ``gate=None`` to skip gate
    filtering — used by pack-authoring tests that assert rule matcher shape
    without gate semantics.

    ``agent_risk_tier`` is the caller identity's tier (populated by the PEP
    from AgentIdentity.risk_tier). When a rule sets ``match_agent_risk_tier``
    it only fires for callers whose tier matches exactly. Rules without this
    field are unaffected. A null tier never matches a rule that requires
    one — safe for legacy identities that pre-date the risk_tier column.
    """
    from app.modules.guard.enforcement import rule_matches_gate

    if gate is not None and not rule_matches_gate(rule, gate):
        return False
    required_tier = rule.get("match_agent_risk_tier")
    if required_tier is not None and required_tier != agent_risk_tier:
        return False
    p = rule.get("match_provider")
    if p is not None and p != provider:
        return False
    m = rule.get("match_model")
    if m and not re.search(m, model or "", re.IGNORECASE):
        return False
    pp = rule.get("match_prompt")
    pat = rule.get("match_pattern")
    # #2159 PR 2 (#2156) — tool-name selectors. Checked BEFORE the
    # prompt/pattern early-return so a rule keyed only on tool identity
    # still fires. Each is a regex; the rule matches only if ANY name
    # in the corresponding list matches. None means the caller PEP did
    # not populate this list; the rule cannot fire against unset data
    # (safe default — matches how match_agent_risk_tier handles a null
    # tier).
    for key, names in (
        ("match_tool_name_offered", tool_names_offered),
        ("match_tool_name_generated", tool_names_generated),
        ("match_tool_name_supplied", tool_names_supplied),
    ):
        pattern = rule.get(key)
        if pattern is None:
            continue
        if not names:
            return False
        if not any(re.search(pattern, n, re.IGNORECASE) for n in names):
            return False
    if not pp and not pat:
        return True

    # ``match_pattern_by_source`` lets a rule use a narrower pattern for tool
    # content than for user text: phrases like "you are now" are rare in a
    # prompt but routine in tool output ("You are now on branch main").
    by_source = rule.get("match_pattern_by_source")
    by_source = by_source if isinstance(by_source, dict) else {}

    def _text_matches(text: str, source: str = "user") -> bool:
        source_pat = by_source.get(source) or pat
        variants = _normalize_text(text or "")
        if pp and not any(re.search(pp, v.text, re.IGNORECASE) for v in variants):
            return False
        if source_pat and not any(re.search(source_pat, v.text, re.IGNORECASE) for v in variants):
            return False
        return True

    # #2384 — ``match_content_source`` opts a rule into tool_result /
    # tool_description text. Without it the rule only sees user text (legacy).
    sources = rule_content_sources(rule)
    if sources is None:
        return _text_matches(prompt_text)
    texts = source_texts if source_texts is not None else {"user": prompt_text}
    for source in sources:
        text = texts.get(source)
        if text and _text_matches(text, source):
            if matched_source is not None:
                matched_source.append(source)
            return True
    return False


# ─── Evaluate (public API) ────────────────────────────────────────────────────

def evaluate(
    workspace_id: str,
    provider: str,
    model: str,
    body: dict,
    gate: str = "prompt",
    agent_risk_tier: str | None = None,
    tool_names_offered: list[str] | None = None,
    tool_names_generated: list[str] | None = None,
    tool_names_supplied: list[str] | None = None,
) -> dict:
    """Pre-call Guard policy evaluation.

    Loads the workspace's compiled policy snapshot (from skill_packs via the
    existing engine) and applies any rule with proxy-applicable matchers:

      match_provider  exact string ('anthropic' | 'openai' | 'perplexity')
      match_model     regex against the model id
      match_prompt    regex against concatenated user messages

    First match wins; action is mapped to BLOCK / WARN / ALLOW. Rules written
    for hook events (match_tool + match_pattern) are silently skipped here —
    they don't apply to raw LLM calls.

    Fail-open on engine errors: returns ALLOW with rule_id='guard.engine_error'
    so the call still goes through and we don't lock customers out of LLMs if
    our cache is busted. The error is logged. If the workspace has
    deny_on_error set, returns BLOCK instead.
    """
    db = SessionLocal()
    try:
        policy_ws_id = _canonical_workspace_id(workspace_id)

        set_workspace_rls(db, policy_ws_id)
        try:
            rules = compute_policy(db, uuid.UUID(policy_ws_id), "proxy")
        except Exception as e:
            log.warning("guard.proxy.policy_load_failed", err=str(e))
            try:
                from app.modules.guard.observability import record_fail_open
                record_fail_open(db, workspace_id=policy_ws_id, surface="proxy", error=e)
            except Exception as _obs_err:
                # record_fail_open() is designed never to raise. If it does,
                # that itself is a bug in the observability module. Log at
                # WARN so we notice; do not re-raise (the outer path is
                # already in a fail-open branch and must not error out).
                log.warning("guard.observability.record_fail_open_failed", err=str(_obs_err))
            from app.modules.guard.models import GuardConfig as _GuardConfig
            cfg = db.query(_GuardConfig).filter(_GuardConfig.workspace_id == uuid.UUID(policy_ws_id)).first()
            deny = cfg.deny_on_error if cfg else True
            if deny:
                return {"action": "BLOCK", "rule_id": "guard.engine_error", "message": "Policy engine error — request blocked (fail-closed). Check Guard settings to change this behavior."}
            return {"action": "ALLOW", "rule_id": "guard.engine_error", "message": None}

        # #1733: response-gate feeds the model reply into the same matcher.
        # For prompt gate (default), same behavior as before.
        prompt_text = flatten_response(body) if gate == "response" else flatten_prompt(body)
        # #2384 — tool-result / tool-description text is only extracted when a
        # loaded rule opts in, so unrelated traffic pays nothing.
        source_texts = None
        if gate == "prompt" and any(
            r.get("match_content_source") is not None for r in rules
        ):
            source_texts = content_source_texts(body, prompt_text)
        matched: list[dict] = []
        winner_full: dict | None = None
        winner_source: str | None = None
        winner_rank = -1
        for r in rules:
            if not _is_proxy_rule(r):
                continue
            _hit_sources: list[str] = []
            if not _rule_matches(
                r, provider, model, prompt_text, gate=gate,
                agent_risk_tier=agent_risk_tier,
                tool_names_offered=tool_names_offered,
                tool_names_generated=tool_names_generated,
                tool_names_supplied=tool_names_supplied,
                source_texts=source_texts,
                matched_source=_hit_sources,
            ):
                continue
            rule_id = r.get("rule_id") or r.get("id")
            action = (r.get("action") or "warn").lower()
            _entry = {
                "rule_id": rule_id,
                "severity": (r.get("severity") or "medium").lower(),
                "action": action,
                "message": r.get("message") or r.get("description"),
            }
            if _hit_sources:
                _entry["content_source"] = _hit_sources[0]
            matched.append(_entry)
            rank = _ACTION_RANK.get(action, 0)
            if rank > winner_rank:
                winner_rank = rank
                winner_full = r
                winner_source = _hit_sources[0] if _hit_sources else None

        matched.sort(key=lambda m: (-SEVERITY_WEIGHTS.get(m["severity"], 3), m["rule_id"] or ""))
        score = _defense_score(matched)

        if winner_full is None:
            return {
                "action": "ALLOW",
                "rule_id": None,
                "message": None,
                "inject_guidance": False,
                "guidance": None,
                "matched_rules": matched,
                "defense_score": score,
            }

        w_action = (winner_full.get("action") or "warn").upper()
        inject_guidance = bool(winner_full.get("inject_guidance"))
        guidance = (winner_full.get("guidance") or winner_full.get("message") or winner_full.get("description")) if inject_guidance else None
        mapped = {"BLOCK": "BLOCK", "WARN": "WARN", "APPROVAL": "APPROVAL"}.get(w_action, "ALLOW")
        return {
            "action": mapped,
            "rule_id": winner_full.get("rule_id") or winner_full.get("id"),
            "message": winner_full.get("message") or winner_full.get("description"),
            "inject_guidance": inject_guidance,
            "guidance": guidance,
            "rule": winner_full,
            "content_source": winner_source,
            "matched_rules": matched,
            "defense_score": score,
        }
    finally:
        db.close()


# ─── Composable engine — #1225 Phase 3 ────────────────────────────────────────

def evaluate_composed(ctx, sources=None):
    """Run policy sources in order. Short-circuit on first BLOCK. Merge others."""
    from app.guard.policy_types import PolicyAction, merge_decisions
    from app.guard.sources import DEFAULT_SOURCES

    if sources is None:
        sources = DEFAULT_SOURCES

    collected = []
    for source in sources:
        decision = source.evaluate(ctx)
        collected.append(decision)
        if decision.action in (PolicyAction.BLOCK, PolicyAction.APPROVAL):
            return decision  # short-circuit — later sources not called

    return merge_decisions(collected)
