"""Shared, secret-free contract for Guard projection queue messages."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any
from uuid import UUID

PROJECTION_QUEUE_KEY = "marshal:projections:queue"
PROJECTION_PROCESSING_KEY = "marshal:projections:processing"
PROJECTION_PROCESSING_TIMES_KEY = "marshal:projections:processing:times"
PROJECTION_DEAD_LETTER_KEY = "marshal:projections:dead-letter"


class ProjectionSourceKind(str, Enum):
    AUDIT_EVENT = "audit_event"
    RULE = "rule"
    DISCOVERED_AGENT = "discovered_agent"
    AUDIT_SUMMARY = "audit_summary"


class ProjectionIntentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    RETRY = "retry"
    COMPLETED = "completed"
    DEAD_LETTER = "dead_letter"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    MISSING = "missing"


@dataclass(frozen=True)
class ProjectionMessage:
    """The complete payload allowed on the projection queue."""

    intent_id: UUID
    workspace_id: UUID
    source_kind: ProjectionSourceKind
    source_id: str
    source_version: str

    def __post_init__(self) -> None:
        try:
            intent_id = UUID(str(self.intent_id))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("intent_id must be a valid UUID") from exc
        try:
            workspace_id = UUID(str(self.workspace_id))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("workspace_id must be a valid UUID") from exc
        try:
            source_kind = ProjectionSourceKind(self.source_kind)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "source_kind must be a valid projection source kind"
            ) from exc

        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must be a non-empty string")
        if not isinstance(self.source_version, str) or not self.source_version.strip():
            raise ValueError("source_version must be a non-empty string")

        object.__setattr__(self, "intent_id", intent_id)
        object.__setattr__(self, "workspace_id", workspace_id)
        object.__setattr__(self, "source_kind", source_kind)

    def to_dict(self) -> dict[str, str]:
        payload = asdict(self)
        return {
            "intent_id": str(payload["intent_id"]),
            "workspace_id": str(payload["workspace_id"]),
            "source_kind": self.source_kind.value,
            "source_id": self.source_id,
            "source_version": self.source_version,
        }

    def to_json(self) -> str:
        """Serialize to deterministic compact JSON for Redis."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str | bytes | bytearray) -> ProjectionMessage:
        try:
            payload: Any = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("projection message must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise TypeError("projection message must be a JSON object")

        expected = {
            "intent_id",
            "workspace_id",
            "source_kind",
            "source_id",
            "source_version",
        }
        if set(payload) != expected:
            raise ValueError(
                "projection message contains missing or unsupported fields"
            )
        return cls(**payload)
