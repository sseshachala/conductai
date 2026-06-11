"""
Memory block executor.

Read/write agent memory with vector similarity search.
Extracted from app.runtime.executor.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


def _execute_memory(
    block: dict,
    state: dict,
    db,
    run_id: str,
    workspace_id: str,
    playbook_slug: str,
    credentials: dict | None = None,
) -> dict:
    """
    Read or write agent memory with vector similarity search.

    read:  queries agent_memory for the most similar past summaries, returns them
           as `entries` list so the brain block can use prior context.
    write: embeds the resolved summary and inserts a new row.
    """
    try:
        return _execute_memory_inner(block, state, db, run_id, workspace_id, playbook_slug, credentials)
    except Exception as e:
        log.warning("memory.block_failed", error=str(e), run_id=run_id)
        try:
            db.rollback()
        except Exception:
            pass
        action = (block.get("data", {}).get("config", {}) or {}).get("action", "read")
        if action == "write":
            return {"written": False, "note": f"memory error: {e}"}
        return {"entries": [], "note": f"memory error: {e}"}


def _execute_memory_inner(
    block: dict,
    state: dict,
    db,
    run_id: str,
    workspace_id: str,
    playbook_slug: str,
    credentials: dict | None = None,
) -> dict:
    from app.models.agent_memory import AgentMemory
    from app.runtime.embedding_client import create_embedding_client
    from app.runtime.executor import _resolve_refs

    data = block["data"]
    config = data.get("config", {})
    action = config.get("action", "read")
    scope = config.get("scope", "repo")
    key = _resolve_refs(config.get("key", ""), state)
    creds = credentials or {}
    # Flat env vars are stored under the "env_vars" handle with lowercased keys
    env_vars = creds.get("env_vars") or {}
    client = create_embedding_client(
        openai_api_key=(
            creds.get("openai", {}).get("api_key")
            or env_vars.get("openai_api_key")
            or env_vars.get("OPENAI_API_KEY")
        ),
        voyage_api_key=(
            creds.get("voyage", {}).get("api_key")
            or env_vars.get("voyage_api_key")
            or env_vars.get("VOYAGE_API_KEY")
        ),
    )

    if action == "read":
        limit = int(config.get("limit", 5))
        if not key:
            return {"entries": [], "note": "No key resolved"}

        if client:
            # Guard: column is vector(1536); Voyage is 512d and not yet supported natively.
            if client.dimensions != 1536:
                log.warning("memory.dimension_mismatch", client_dims=client.dimensions, column_dims=1536)
                client = None

        if client:
            query_vec = client.embed(key)
            # Native vector column — no ::vector cast needed; HNSW index kicks in automatically.
            rows = db.execute(
                __import__("sqlalchemy").text("""
                    SELECT summary, created_at,
                           (embedding <=> CAST(:vec AS vector)) AS distance
                    FROM agent_memory
                    WHERE workspace_id = :ws
                      AND playbook_slug = :slug
                      AND scope = :scope
                      AND key = :key
                      AND embedding IS NOT NULL
                    ORDER BY distance ASC
                    LIMIT :lim
                """),
                {
                    "vec": str(query_vec),
                    "ws": workspace_id,
                    "slug": playbook_slug,
                    "scope": scope,
                    "key": key,
                    "lim": limit,
                },
            ).fetchall()
        else:
            # No embedding provider (or dimension mismatch) — fall back to recency.
            rows = db.query(AgentMemory).filter(
                AgentMemory.workspace_id == workspace_id,
                AgentMemory.playbook_slug == playbook_slug,
                AgentMemory.scope == scope,
                AgentMemory.key == key,
            ).order_by(AgentMemory.created_at.desc()).limit(limit).all()

        entries = [{"summary": r.summary, "at": str(r.created_at)} for r in rows]
        return {"entries": entries, "count": len(entries), "scope": scope, "key": key}

    elif action == "write":
        summary_tpl = config.get("summary", "")
        summary = _resolve_refs(summary_tpl, state).strip()
        if not summary:
            return {"written": False, "note": "Empty summary — nothing written"}

        # Guard dimension mismatch same as read path.
        if client and client.dimensions != 1536:
            log.warning("memory.dimension_mismatch", client_dims=client.dimensions, column_dims=1536)
            client = None

        embedding_vec: list[float] | None = None
        if client:
            try:
                embedding_vec = client.embed(summary)
            except Exception as e:
                log.warning("memory.embed_failed", error=str(e))

        row = AgentMemory(
            workspace_id=workspace_id,
            playbook_slug=playbook_slug,
            scope=scope,
            key=key,
            summary=summary,
            embedding=embedding_vec,
            run_id=run_id if run_id else None,
        )
        db.add(row)
        db.commit()
        return {"written": True, "scope": scope, "key": key, "chars": len(summary)}

    return {"skipped": True, "note": f"Unknown memory action: {action}"}
