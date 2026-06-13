"""
Pydantic models for the Delegator workflow DSL.

Design goals
============
1. **Clean for humans.** Authors hand-write these. No verbose envelopes.
2. **Extensible.** Per-block ``params`` and per-trigger config are open dicts,
   so a new integration can ship without a schema migration.
3. **Strict where it matters.** Block types and routing structure are
   enumerated so typos fail loudly at load time, not silently at run time.
4. **Stable shape.** The loader emits the same {nodes, edges} graph the
   executor has always consumed; the runtime is unchanged.

A worked example lives in ``apps/api/playbooks/ai_ready.yaml``.
"""
from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enumerated block types — kept in one place so the executor, loader, and
# canvas all agree on the supported set.
# ---------------------------------------------------------------------------
SUPPORTED_BLOCK_TYPES = {
    "tool",
    "brain",
    "logic",
    "approval",
    "memory",
    "output",
    "guard",
    "mcp",
    # `trigger` and `cleanup` are special: triggers live under top-level
    # ``on:`` and cleanups under top-level ``cleanup:`` — they do not appear
    # as values of ``blocks:``.
}

BRAIN_MODES = {"single", "agentic"}
OUTPUT_CHANNELS = {"slack", "email", "both"}


class WorkflowValidationError(ValueError):
    """Raised by the loader when a YAML document is structurally invalid."""


# ---------------------------------------------------------------------------
# Workflow parameters — declared once at the top of a workflow and referenced
# inside blocks via ``{{params.<name>}}``.
# ---------------------------------------------------------------------------
class WorkflowParam(BaseModel):
    """A typed input the user supplies at run time (or via webhook payload)."""

    type: Literal["string", "number", "boolean"] = "string"
    required: bool = False
    default: Any | None = None
    description: str | None = None

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Brain block remote-host config — declarative SSH target.
# The SSH private key is NEVER inlined. We name the integration handle
# (``credentials_from``) and the runtime pulls the key from encrypted creds.
# ---------------------------------------------------------------------------
class RunsOn(BaseModel):
    """Where a Brain block executes its tool calls."""

    ip: str = Field(description="Host or {{ref}} resolving to one")
    credentials_from: str = Field(
        default="digitalocean",
        description="Integration handle whose credentials include ssh_private_key",
    )
    username: str | None = None
    port: int | None = None

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Output block — supports Slack, Email, or both, with channel/recipient set
# at the block level rather than nested under a generic config.
# ---------------------------------------------------------------------------
class SlackOutput(BaseModel):
    channel: str
    approval: bool = False  # when True, sends Approve/Reject buttons with the message
    model_config = ConfigDict(extra="allow")  # blocks/threading config later


class EmailOutput(BaseModel):
    to: str
    from_address: str | None = None
    model_config = ConfigDict(extra="allow")


class OutputConfig(BaseModel):
    """One block per workflow can fan out to multiple channels."""

    via: Literal["slack", "email", "both"] = "slack"
    slack: SlackOutput | None = None
    email: EmailOutput | None = None

    @model_validator(mode="after")
    def _channels_present(self) -> "OutputConfig":
        if self.via in ("slack", "both") and not self.slack:
            raise ValueError("via=slack/both requires a `slack:` section")
        if self.via in ("email", "both") and not self.email:
            raise ValueError("via=email/both requires an `email:` section")
        return self


# ---------------------------------------------------------------------------
# Block — the workhorse model. Most fields are conditional on `type`; we keep
# them all at the top level rather than splitting per-type models so users
# don't have to context-switch between subclasses while authoring YAML.
# ---------------------------------------------------------------------------
class Block(BaseModel):
    type: Literal["tool", "brain", "logic", "approval", "memory", "output", "mcp", "sandbox", "guard", "for_each"]
    label: str | None = None
    description: str | None = None

    # — tool blocks —
    integration: str | None = None
    action: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] | None = None  # alias for params on tool blocks (#565)

    # — mcp blocks —
    credential_key: str | None = None
    tool_name: str | None = None

    # — brain blocks —
    mode: Literal["single", "agentic"] | None = None
    model: str | None = None  # Claude model ID, e.g. "claude-haiku-4-5-20251001"
    runs_on: RunsOn | None = None
    custom_instructions: str | None = None  # user-editable zone, appended to description at runtime
    prompt_file: str | None = None  # path relative to playbook dir, e.g. prompts/fetch_issue.txt
    system: str | None = None   # brain block system prompt (alternative to description) (#565)
    prompt: str | None = None   # brain block user prompt (#565)
    allowed_tools: list[str] | None = None  # tool scope restriction for brain blocks (#565)

    # — logic blocks —
    condition: str | None = None

    # — approval blocks —
    via: Literal["slack", "email", "both"] | None = None  # default: slack if channel/slack_user set
    channel: str | None = None
    slack_user: str | None = None
    approval_email: str | None = None  # email address to send approve/reject link
    message: str | None = None

    # — memory blocks —
    scope: Literal["repo", "workspace"] | None = None
    key: str | None = None
    limit: int | None = None
    summary: str | None = None

    # — output blocks —
    output: OutputConfig | None = None
    channels: list[str] | None = None   # shorthand output channels (#565)
    template: str | None = None         # shorthand output template (#565)

    # — iteration / loop (#565) —
    for_each: str | None = None   # iteration expression, e.g. "{{ items.output }}"
    item_var: str | None = None   # loop variable name (default "item")

    # — sandbox routing (brain blocks) —
    # "auto" = executor decides proxy vs sandbox based on plan_fix.complexity
    sandbox: str | None = None

    # — per-block turn budget override for agentic brain blocks —
    max_turns: int | None = None  # overrides the run-level __max_turns for this block only

    # — retry (#565) —
    retry: dict[str, Any] | None = None  # retry config (typed properly in #564, dict for now)

    # — routing — either a single string or a per-branch dict
    # e.g.  next: create_droplet
    # or    next: { pass: push_pr, fail: notify_failure }
    next: Union[str, dict[str, str]] | None = None

    model_config = ConfigDict(extra="ignore")  # ignore unknown keys e.g. `credentials` in YAML

    # ----- per-type validation ---------------------------------------------
    @model_validator(mode="after")
    def _validate_by_type(self) -> "Block":
        t = self.type
        if t == "tool":
            # If action uses slash-format (e.g. "github/create_issue"), derive
            # integration from it so authors don't have to repeat themselves.
            if self.action and "/" in self.action and self.integration is None:
                parts = self.action.split("/", 1)
                self.integration = parts[0]
                self.action = parts[1]
            if not self.integration or not self.action:
                raise ValueError("tool blocks require both `integration` and `action`")
        elif t == "brain":
            if self.mode and self.mode not in BRAIN_MODES:
                raise ValueError(f"brain mode must be one of {BRAIN_MODES}")
            if not self.description and not self.prompt_file and not self.system and not self.prompt:
                raise ValueError(
                    "brain blocks require a `description`, `prompt_file`, `system`, or `prompt`"
                )
        elif t == "logic":
            if not self.condition:
                raise ValueError("logic blocks require a `condition`")
            if not isinstance(self.next, dict) or set(self.next.keys()) - {"pass", "fail"}:
                raise ValueError(
                    "logic blocks need `next: { pass: <block>, fail: <block> }`"
                )
        elif t == "approval":
            via = self.via or "slack"
            has_slack = bool(self.channel or self.slack_user)
            has_email = bool(self.approval_email)
            if via in ("slack", "both") and not has_slack:
                raise ValueError("approval blocks with via=slack/both require `channel` or `slack_user`")
            if via in ("email", "both") and not has_email:
                raise ValueError("approval blocks with via=email/both require `approval_email`")
            if not has_slack and not has_email:
                raise ValueError("approval blocks require at least one of: `channel`, `slack_user`, or `approval_email`")
        elif t == "memory":
            if not self.action or self.action not in ("read", "write"):
                raise ValueError("memory blocks require `action: read` or `action: write`")
            if self.action == "write" and not self.summary:
                raise ValueError("memory write blocks require a `summary:` template")
        elif t == "output":
            if not self.output and not (self.channels and self.template):
                raise ValueError(
                    "output blocks require an `output:` section, or `channels` + `template`"
                )
        elif t == "mcp":
            if not self.credential_key:
                raise ValueError("mcp blocks require `credential_key`")
            if not self.tool_name:
                raise ValueError("mcp blocks require `tool_name`")
        return self


# ---------------------------------------------------------------------------
# Trigger — the top-level ``on:`` section. We keep it open-ended (extra
# fields allowed) so each trigger type can carry its own filters without a
# schema change. The runtime resolves the trigger to a synthetic block at
# DAG entry time.
# ---------------------------------------------------------------------------
class Trigger(BaseModel):
    """One concrete trigger. Keyed in YAML by its event name (e.g. github.issue_labeled)."""

    integration: str | None = None
    next: str | None = Field(
        default=None,
        description="Entry block id. Defaults to the first key under blocks: if omitted.",
    )

    model_config = ConfigDict(extra="allow")  # event-specific filter fields


# ---------------------------------------------------------------------------
# Cleanup block — identical structure to a regular block but lives in its
# own top-level section so cleanups always run regardless of routing.
# ---------------------------------------------------------------------------
class CleanupBlock(Block):
    """A block that always executes at the end of a run (success OR failure)."""

    # Cleanups don't participate in `next` routing.
    next: None = None

    @model_validator(mode="after")
    def _no_next(self) -> "CleanupBlock":
        if self.next is not None:
            raise ValueError("cleanup blocks cannot specify `next`")
        return self


# ---------------------------------------------------------------------------
# Workflow — the root document.
# ---------------------------------------------------------------------------
class Workflow(BaseModel):
    id: str | None = None           # workflow UUID — included when exported from canvas
    workspace_id: str | None = None  # workspace UUID — included when exported from canvas
    name: str
    version: int = 1
    schema_version: str | None = None  # opt-in JSON Schema validation (#565)
    description: str | None = None

    params: dict[str, WorkflowParam] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)  # install-time config — declared here so extra="forbid" doesn't reject it

    # YAML key is the event name, e.g. ``github.issue_labeled``. We use an
    # alias so authors can write ``on:`` even though ``on`` is a Python keyword.
    triggers: dict[str, Trigger] = Field(default_factory=dict, alias="on")

    blocks: dict[str, Block]
    cleanup: dict[str, CleanupBlock] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    # ----- structural validation -------------------------------------------
    @field_validator("name")
    @classmethod
    def _name_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("workflow `name` must be non-empty")
        return v

    @model_validator(mode="after")
    def _routing_is_consistent(self) -> "Workflow":
        # Every `next:` target must exist as a block id (or in cleanup, which
        # would be a misuse — cleanups are unreachable from the main graph).
        known_ids = set(self.blocks.keys())
        for block_id, block in self.blocks.items():
            nxt = block.next
            if nxt is None:
                continue
            if isinstance(nxt, str):
                targets = [nxt]
            else:
                targets = list(nxt.values())
            for t in targets:
                if t == "end":
                    continue  # "end" is a reserved terminal sentinel — means stop here
                if t not in known_ids:
                    raise ValueError(
                        f"block '{block_id}' routes to unknown block '{t}'"
                    )

        # Trigger `next` (if set) must also exist; if unset, the runtime
        # picks the first block in insertion order.
        for ev, trig in self.triggers.items():
            if trig.next is not None and trig.next not in known_ids:
                raise ValueError(
                    f"trigger '{ev}' routes to unknown block '{trig.next}'"
                )
        return self

    # ----- helpers ---------------------------------------------------------
    def entry_block_id(self) -> str | None:
        """Return the id of the first block executed after the trigger fires."""
        for trig in self.triggers.values():
            if trig.next:
                return trig.next
        # Fall back to the first authored block (dicts in Python 3.7+ are ordered).
        return next(iter(self.blocks.keys()), None)
