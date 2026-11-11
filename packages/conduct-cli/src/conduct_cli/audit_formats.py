"""Output formats for ``conduct audit feed``: native JSON, OCSF, Elastic ECS, CEF.

Each formatter turns one feed event (the dict served by ``get_audit_feed``)
into one output line. They are tolerant by design: a missing field is skipped,
and any field the formatter does not map (for example ``hash_version`` or
checkpoint fields added to the chain later) is carried through untouched in the
format's extension point, so hash-chain data is never dropped.

Mapping choices (see docs/reference/siem-feed.md):

* OCSF 1.3: class ``API Activity`` (6003, category Application Activity). Every
  event is an agent tool call plus Guard's decision on it, including the many
  allowed calls, so an activity class fits; ``Detection Finding`` would turn
  every allow into a finding. Blocks/warnings carry ``action_id`` /
  ``disposition_id`` and a higher ``severity_id`` so detections can key on them.
  Hash-chain fields live in ``unmapped``.
* ECS 8.11: ``event.*`` / ``user.*`` / ``rule.*`` plus a custom ``conduct.*``
  namespace (chain fields under ``conduct.chain``).
* CEF 0: ``CEF:0|Conduct|Guard|<version>|<signature>|<name>|<severity>|<ext>``
  with chain fields in ``cs4``/``cs5``/``cn1`` and extra fields as
  ``conduct<FieldName>`` keys.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

FORMATS = ("json", "ocsf", "ecs", "cef")
PRODUCT_VERSION = "1"
OCSF_VERSION = "1.3.0"

_CHAIN_FIELDS = ("previous_hash", "entry_hash", "chain_position")


def _decision(event):
    d = str(event.get("decision") or "").strip().lower()
    if d in ("allow", "allowed", "audited", "permit", "permitted"):
        return "allowed"
    if d in ("block", "blocked", "deny", "denied"):
        return "blocked"
    if d in ("warn", "warned", "warning"):
        return "warned"
    if "approval" in d.replace("-", "_").replace(" ", "_") or d.startswith("approv"):
        return "approval"
    return d or "unknown"


def _epoch_ms(ts):
    """ISO-8601 to epoch milliseconds, or None when absent or unparseable."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _compact(obj):
    """Drop None and empty-string values (recursively) so lines stay small."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            v = _compact(v)
            if v is None or v == "" or v == {}:
                continue
            out[k] = v
        return out
    return obj


def _dump(obj):
    return json.dumps(obj, separators=(",", ":"), default=str)


def _unmapped(event, mapped):
    """Everything not mapped, hash-chain fields always included when present."""
    out = {}
    for k, v in event.items():
        if k in mapped:
            continue
        if v is None and k not in _CHAIN_FIELDS:
            continue
        out[k] = v
    for k in _CHAIN_FIELDS:
        if k in event:
            out[k] = event[k]
    return out


# ── native ───────────────────────────────────────────────────────────────────

def format_json(event):
    return _dump(event)


# ── OCSF: API Activity (6003) ────────────────────────────────────────────────

_OCSF_SEVERITY = {"allowed": 1, "warned": 3, "approval": 3, "blocked": 4}
# action_id: 1 Allowed, 2 Denied, 99 Other. disposition_id: 1 Allowed, 2 Blocked, 19 Alert, 99 Other
_OCSF_ACTION = {"allowed": (1, "Allowed", 1, "Allowed"),
                "warned": (1, "Allowed", 19, "Alert"),
                "blocked": (2, "Denied", 2, "Blocked"),
                "approval": (99, "Other", 99, "Other")}


def format_ocsf(event):
    d = _decision(event)
    action_id, action, disp_id, disp = _OCSF_ACTION.get(d, (0, "Unknown", 0, "Unknown"))
    activity_id = 99  # Other: a tool call is not a CRUD verb
    user = _compact({"uid": event.get("clerk_user_id"), "email_addr": event.get("user_email")})
    actor = _compact({
        "user": user or None,
        "session": {"uid": event.get("session_id")} if event.get("session_id") else None,
        "app_name": event.get("ai_tool"),
    })
    rec = {
        "class_uid": 6003, "class_name": "API Activity",
        "category_uid": 6, "category_name": "Application Activity",
        "activity_id": activity_id, "activity_name": "Tool Call",
        "type_uid": 6003 * 100 + activity_id, "type_name": "API Activity: Other",
        "time": _epoch_ms(event.get("ts")),
        "severity_id": _OCSF_SEVERITY.get(d, 0),
        "status_id": 2 if d == "blocked" else 1,
        "action_id": action_id, "action": action,
        "disposition_id": disp_id, "disposition": disp,
        "message": event.get("rule_message") or event.get("input_summary"),
        "metadata": {
            "version": OCSF_VERSION, "uid": event.get("id"), "sequence": event.get("chain_position"),
            "product": {"name": "Guard", "vendor_name": "Conduct"},
            "log_name": "audit", "tenant_uid": event.get("workspace_id"),
        },
        "actor": actor,
        "api": {"operation": event.get("tool_call") or "unknown",
                "service": {"name": event.get("ai_tool") or "unknown"}},
        "src_endpoint": {"name": event.get("ai_tool") or "unknown"},
    }
    rec = _compact(rec)
    # Not compacted: previous_hash is "" on the first row of a chain and must survive.
    rec["unmapped"] = _unmapped(event, {"id", "ts", "workspace_id", "ai_tool", "tool_call", "rule_message",
                                        "user_email", "clerk_user_id", "session_id"})
    return _dump(rec)


# ── Elastic ECS ──────────────────────────────────────────────────────────────

_ECS_LEVEL = {"allowed": "info", "warned": "warning", "approval": "warning", "blocked": "error"}
_ECS_TYPE = {"allowed": ["allowed"], "blocked": ["denied"], "warned": ["info"], "approval": ["info"]}
_ECS_MAPPED = {"id", "ts", "workspace_id", "ai_tool", "tool_call", "decision", "rule_id", "rule_message",
               "input_summary", "user_email", "clerk_user_id", "session_id", "duration_ms", "previous_hash",
               "entry_hash", "chain_position", "source", "model", "provider"}


def format_ecs(event):
    d = _decision(event)
    conduct = {
        "decision": event.get("decision"), "ai_tool": event.get("ai_tool"),
        "tool_call": event.get("tool_call"), "source": event.get("source"),
        "workspace_id": event.get("workspace_id"), "session_id": event.get("session_id"),
        "model": event.get("model"), "provider": event.get("provider"),
        "chain": {"previous_hash": event.get("previous_hash") if "previous_hash" in event else None,
                  "entry_hash": event.get("entry_hash"), "position": event.get("chain_position")},
    }
    extra = _unmapped(event, _ECS_MAPPED)
    for k in _CHAIN_FIELDS:
        extra.pop(k, None)
    conduct["extra"] = extra
    rec = {
        "@timestamp": event.get("ts"),
        "ecs": {"version": "8.11.0"},
        "event": {
            "id": event.get("id"), "kind": "event",
            "category": ["intrusion_detection"] if d in ("blocked", "warned") else ["process"],
            "type": _ECS_TYPE.get(d, ["info"]),
            "action": event.get("tool_call"),
            "outcome": "failure" if d == "blocked" else "success",
            "module": "conduct", "dataset": "conduct.guard.audit", "provider": "guard",
            "sequence": event.get("chain_position"), "hash": event.get("entry_hash"),
            "duration": event.get("duration_ms") * 1_000_000 if isinstance(event.get("duration_ms"), (int, float)) else None,
        },
        "message": event.get("rule_message") or event.get("input_summary"),
        "log": {"level": _ECS_LEVEL.get(d, "info")},
        "user": {"id": event.get("clerk_user_id"), "email": event.get("user_email")},
        "rule": {"id": event.get("rule_id"), "description": event.get("rule_message")},
        "organization": {"id": event.get("workspace_id")},
        "service": {"name": event.get("ai_tool")},
        "conduct": conduct,
    }
    # previous_hash is "" on the first row; _compact would drop it, so restore it.
    out = _compact(rec)
    if "previous_hash" in event:
        out.setdefault("conduct", {}).setdefault("chain", {})["previous_hash"] = event["previous_hash"]
    return _dump(out)


# ── CEF ──────────────────────────────────────────────────────────────────────

_CEF_SEVERITY = {"allowed": 1, "warned": 5, "approval": 6, "blocked": 8}
_CEF_MAPPED = {"id", "ts", "workspace_id", "ai_tool", "tool_call", "decision", "rule_id", "rule_message",
               "input_summary", "user_email", "clerk_user_id", "session_id", "previous_hash", "entry_hash",
               "chain_position", "duration_ms"}


def _hdr(value):
    return str(value if value is not None else "").replace("\\", "\\\\").replace("|", "\\|") \
        .replace("\n", " ").replace("\r", " ")


def _ext(value):
    if isinstance(value, (dict, list)):
        value = _dump(value)
    return str(value).replace("\\", "\\\\").replace("=", "\\=").replace("\n", "\\n").replace("\r", "\\r")


def _camel(name):
    return "".join(p[:1].upper() + p[1:] for p in str(name).replace("-", "_").split("_") if p)


def format_cef(event):
    d = _decision(event)
    tool = event.get("tool_call") or "unknown"
    pairs = [
        ("rt", _epoch_ms(event.get("ts"))),
        ("externalId", event.get("id")),
        ("act", d),
        ("outcome", "failure" if d == "blocked" else "success"),
        ("app", event.get("ai_tool")),
        ("suser", event.get("user_email")),
        ("suid", event.get("clerk_user_id")),
        ("msg", event.get("rule_message") or event.get("input_summary")),
        ("cs1Label", "ruleId"), ("cs1", event.get("rule_id")),
        ("cs2Label", "toolCall"), ("cs2", tool),
        ("cs3Label", "workspaceId"), ("cs3", event.get("workspace_id")),
        ("cs4Label", "entryHash"), ("cs4", event.get("entry_hash")),
        ("cs5Label", "previousHash"), ("cs5", event.get("previous_hash") if "previous_hash" in event else None),
        ("cs6Label", "sessionId"), ("cs6", event.get("session_id")),
        ("cn1Label", "chainPosition"), ("cn1", event.get("chain_position")),
        ("cn2Label", "durationMs"), ("cn2", event.get("duration_ms")),
    ]
    for k in sorted(event):
        if k not in _CEF_MAPPED and event[k] is not None:
            pairs.append(("conduct" + _camel(k), event[k]))
    ext = " ".join("%s=%s" % (k, _ext(v)) for k, v in pairs if v is not None and (v != "" or k == "cs5"))
    return "CEF:0|Conduct|Guard|%s|guard.%s|%s|%d|%s" % (
        PRODUCT_VERSION, _hdr(d), _hdr("%s %s" % (tool, d)), _CEF_SEVERITY.get(d, 3), ext)


FORMATTERS = {"json": format_json, "ocsf": format_ocsf, "ecs": format_ecs, "cef": format_cef}
