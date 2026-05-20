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
    "output",
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
    type: Literal["tool", "brain", "logic", "approval", "output"]
    label: str | None = None
    description: str | None = None

    # — tool blocks —
    integration: str | None = None
    action: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    # — brain blocks —
    mode: Literal["single", "agentic"] | None = None
    runs_on: RunsOn | None = None

    # — logic blocks —
    condition: str | None = None

    # — approval blocks —
    channel: str | None = None
    slack_user: str | None = None
    message: str | None = None

    # — output blocks —
    output: OutputConfig | None = None

    # — routing — either a single string or a per-branch dict
    # e.g.  next: create_droplet
    # or    next: { pass: push_pr, fail: notify_failure }
    next: Union[str, dict[str, str]] | None = None

    model_config = ConfigDict(extra="forbid")

    # ----- per-type validation ---------------------------------------------
    @model_validator(mode="after")
    def _validate_by_type(self) -> "Block":
        t = self.type
        if t == "tool":
            if not self.integration or not self.action:
                raise ValueError("tool blocks require both `integration` and `action`")
        elif t == "brain":
            if self.mode and self.mode not in BRAIN_MODES:
                raise ValueError(f"brain mode must be one of {BRAIN_MODES}")
            if not self.description:
                raise ValueError("brain blocks require a `description`")
        elif t == "logic":
            if not self.condition:
                raise ValueError("logic blocks require a `condition`")
            if not isinstance(self.next, dict) or set(self.next.keys()) - {"pass", "fail"}:
                raise ValueError(
                    "logic blocks need `next: { pass: <block>, fail: <block> }`"
                )
        elif t == "approval":
            if not self.channel and not self.slack_user:
                raise ValueError(
                    "approval blocks require either `channel` or `slack_user`"
                )
        elif t == "output":
            if not self.output:
                raise ValueError("output blocks require an `output:` section")
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
    description: str | None = None

    params: dict[str, WorkflowParam] = Field(default_factory=dict)

    # YAML key is the event name, e.g. ``github.issue_labeled``. We use an
    # alias so authors can write ``on:`` even though ``on`` is a Python keyword.
    triggers: dict[str, Trigger] = Field(default_factory=dict, alias="on")

    blocks: dict[str, Block]
    cleanup: dict[str, CleanupBlock] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

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
