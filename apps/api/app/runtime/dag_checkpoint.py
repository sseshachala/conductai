"""DAG runner state checkpointing (split from dag_runner.py; re-exported there)."""
from __future__ import annotations

import uuid
from datetime import timezone

import structlog

from app.core.config import settings

log = structlog.get_logger("app.runtime.dag_runner")


_STATE_CHECKPOINT_TTL = 604800  # 7 days — Redis LLM-cache TTL (unchanged)

# Module-level Redis connection pool — used as optional read cache only.
import redis as _redis_mod
import json as _json_mod
_redis_pool = _redis_mod.ConnectionPool.from_url(settings.redis_url, decode_responses=True)


def _redis_client() -> "_redis_mod.Redis":
    return _redis_mod.Redis(connection_pool=_redis_pool)


# ── state checkpointing ───────────────────────────────────────────────────────

def _checkpoint_state(
    run_id: str | None,
    state: dict,
    db=None,
    block_id: str | None = None,
    attempt_id: str | None = None,
    partial: bool = False,
    resume_from_turn: int = 0,
) -> None:
    """Atomic DB upsert for per-block checkpoint.

    Writes to run_block_states via INSERT ... ON CONFLICT DO UPDATE so the
    operation is a single round-trip with no crash window between completion
    and persistence.

    Also updates runs.last_heartbeat_time so the reaper does not kill
    long-running agentic blocks mid-execution.

    Redis write is best-effort: used only as a warm read cache on resume.
    A Redis failure never raises — the DB row is the source of truth.
    """
    if not run_id or not db or not block_id:
        return

    from datetime import datetime as _dt
    _completed_at = None if partial else _dt.now(timezone.utc).isoformat()

    try:
        import sqlalchemy as _sa

        # Build the upsert using raw SQL for portability with both sync and
        # greenlet-threaded SQLAlchemy sessions used in the worker.
        _upsert_sql = _sa.text("""
            INSERT INTO run_block_states
                (run_id, block_id, attempt_id, output, partial, resume_from_turn, completed_at, created_at)
            VALUES
                (:run_id, :block_id, :attempt_id, CAST(:output AS jsonb), :partial, :resume_from_turn, CAST(:completed_at AS timestamptz), now())
            ON CONFLICT (run_id, block_id) DO UPDATE SET
                attempt_id       = EXCLUDED.attempt_id,
                output           = EXCLUDED.output,
                partial          = EXCLUDED.partial,
                resume_from_turn = EXCLUDED.resume_from_turn,
                completed_at     = EXCLUDED.completed_at
        """)

        # For partial checkpoints preserve last known output so a mid-block
        # crash doesn't wipe what the block has produced so far.
        _output_json = _json_mod.dumps(
            state.get(block_id, {}),
            default=str,
        )

        db.execute(_upsert_sql, {
            "run_id":           str(run_id),
            "block_id":         block_id,
            "attempt_id":       str(attempt_id or uuid.uuid4()),
            "output":           _output_json,
            "partial":          partial,
            "resume_from_turn": resume_from_turn,
            "completed_at":     _completed_at,
        })
        db.commit()

    except Exception as _e:
        log.warning("dag.checkpoint_failed", run_id=run_id, block_id=block_id, error=str(_e))
        try:
            db.rollback()
        except Exception:
            pass
        return

    # Heartbeat — separate transaction so a lock contention on runs table
    # never rolls back the already-committed run_block_states upsert.
    try:
        import sqlalchemy as _sa
        db.execute(
            _sa.text("UPDATE runs SET last_heartbeat_time = now() WHERE id = :run_id"),
            {"run_id": str(run_id)},
        )
        db.commit()
    except Exception as _he:
        log.warning("dag.heartbeat_failed", run_id=run_id, error=str(_he))
        try:
            db.rollback()
        except Exception:
            pass

    # Best-effort Redis write — warm cache only, never the source of truth
    try:
        _redis_client().setex(
            f"run_state:{run_id}",
            _STATE_CHECKPOINT_TTL,
            _json_mod.dumps(state, default=str),
        )
    except Exception:
        pass  # Redis failure is non-fatal


def _load_checkpoint(run_id: str | None, db=None) -> tuple[dict, list]:
    """Load per-block checkpoint rows from DB.

    Returns (completed_outputs, block_state_rows) where:
    - completed_outputs: {block_id: output_dict} for rows with partial=False
    - block_state_rows: all RunBlockState rows for this run (both partial and complete)

    Falls back to Redis if db is None or query fails (legacy runs keep working).
    """
    if not run_id:
        return {}, []

    if db is not None:
        try:
            import sqlalchemy as _sa
            rows = db.execute(
                _sa.text("SELECT block_id, attempt_id, output, partial, resume_from_turn FROM run_block_states WHERE run_id = :run_id"),
                {"run_id": str(run_id)},
            ).fetchall()

            completed_outputs: dict = {}
            row_objects: list = []

            for row in rows:
                # Wrap raw Row into a simple namespace for attribute access
                class _Row:
                    pass
                r = _Row()
                r.block_id        = row[0]
                r.attempt_id      = str(row[1])
                r.output          = row[2] if isinstance(row[2], dict) else (_json_mod.loads(row[2]) if row[2] else {})
                r.partial         = row[3]
                r.resume_from_turn = row[4]
                row_objects.append(r)
                if not r.partial:
                    completed_outputs[r.block_id] = r.output

            return completed_outputs, row_objects
        except Exception as _e:
            log.warning("dag.load_checkpoint_failed", run_id=run_id, error=str(_e))

    # Redis fallback — for legacy runs that have no DB rows yet
    try:
        raw = _redis_client().get(f"run_state:{run_id}")
        if raw:
            legacy_state = _json_mod.loads(raw)
            return legacy_state, []
    except Exception:
        pass

    return {}, []

