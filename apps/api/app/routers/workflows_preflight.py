"""Preflight turn-estimation helpers for workflows (split from workflows.py).

Used by the preflight endpoint, test_trigger, runs.create_run and the
inbound webhook path to size max_turns before a run starts.
"""
from sqlalchemy.orm import Session


def _resolve_preflight_key(workspace_id: str | None, db: Session | None) -> str | None:
    """Resolve ANTHROPIC_API_KEY from workspace vault, fall back to server key."""
    from app.core.config import settings
    if workspace_id and db:
        try:
            from app.core.credentials import get_all_credentials
            store = get_all_credentials(db, workspace_id)
            key = (
                (store.get("anthropic") or {}).get("api_key")
                or (store.get("env_vars") or {}).get("ANTHROPIC_API_KEY")
                or (store.get("env_vars") or {}).get("anthropic_api_key")
            )
            if key:
                return key
        except Exception:
            pass
    return settings.anthropic_api_key


def _task_type_floor(description: str) -> int:
    """
    Static floor based on task keywords in brain block description.
    Avoids assigning 20 turns to an inherently complex task when there's no history.
    """
    desc = description.lower()
    if any(k in desc for k in ("implement", "fix", "refactor", "rewrite", "clone", "fork", "patch", "migrate")):
        return 50
    if any(k in desc for k in ("create", "write", "build", "generate", "add feature", "develop")):
        return 40
    if any(k in desc for k in ("review", "analyze", "audit", "test", "check", "investigate")):
        return 30
    return 20


def _historical_floor(workflow_id: str | None, db: Session | None) -> int:
    """
    Query the last 10 completed runs of this workflow.
    Returns p75 of actual_turns * 1.2, with doubling if the last run was exhausted.
    Falls back to 0 (no opinion) if no history exists.
    """
    if not workflow_id or not db:
        return 0
    try:
        from app.models.run import Run as _Run
        from app.models.workflow_version import WorkflowVersion as _WV
        rows = (
            db.query(_Run.actual_turns, _Run.budget_exhausted)
            .join(_WV, _Run.workflow_version_id == _WV.id)
            .filter(
                _WV.workflow_id == workflow_id,
                _Run.actual_turns.isnot(None),
                _Run.status.in_(["succeeded", "failed"]),
            )
            .order_by(_Run.created_at.desc())
            .limit(10)
            .all()
        )
        if not rows:
            return 0

        turns_list = sorted(r.actual_turns for r in rows)
        p75_idx = int(len(turns_list) * 0.75)
        p75 = turns_list[min(p75_idx, len(turns_list) - 1)]
        estimate = int(p75 * 1.2)

        # If the most recent run hit the wall, double it
        if rows[0].budget_exhausted:
            estimate = max(estimate, rows[0].actual_turns * 2)

        return max(estimate, 20)
    except Exception:
        return 0


def _estimate_turns_for_graph(
    graph: dict,
    issue_title: str = "",
    issue_body: str = "",
    min_turns: int = 0,
    workspace_id: str | None = None,
    db: Session | None = None,
    workflow_id: str | None = None,
) -> dict:
    """
    Core turn-budget estimation logic — shared between the preflight HTTP endpoint
    and server-side webhook queueing.

    Priority (highest wins):
      1. Historical p75 * 1.2  (or 2× if last run exhausted)
      2. Haiku LLM estimate per brain block
      3. Task-type floor from description keywords
      4. min_turns from YAML / workflow settings
    """
    import json, re

    nodes = graph.get("nodes", [])
    brain_blocks = [
        n for n in nodes
        if n.get("data", {}).get("type") == "brain"
        and n.get("data", {}).get("isAgentic", False)
    ]

    if not brain_blocks:
        return {"suggested_max_turns": 20, "blocks": [], "total_files": []}

    # Signal 1: history (most accurate for repeat runs)
    history_floor = _historical_floor(workflow_id, db)

    api_key = _resolve_preflight_key(workspace_id, db)
    from app.runtime.llm_client import client_for
    client = client_for("anthropic", api_key)
    block_estimates = []
    all_files: list[str] = []

    for block in brain_blocks:
        data = block.get("data", {})
        label = data.get("label", block.get("id", "?"))
        description = data.get("description", "")

        # Signal 3: task-type floor from description
        kw_floor = _task_type_floor(description)

        prompt = (
            f"You are estimating work for an AI coding agent.\n\n"
            f"Issue title: {issue_title}\n"
            f"Issue body: {issue_body}\n\n"
            f"Brain block task:\n{description}\n\n"
            f"Estimate: how many tool calls (shell commands, file reads, file writes, "
            f"git operations) will this block need to complete this task? "
            f"Be generous — it is better to over-estimate than under-estimate.\n"
            f"Respond with JSON only, no explanation:\n"
            f'{{ "files": ["path/to/file", ...], "estimated_turns": <number>, "reasoning": "<one line>" }}'
        )

        try:
            from app.runtime.llm_client import LLMTextBlock
            resp = client.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                system="",
                messages=[{"role": "user", "content": prompt}],
            )
            first = resp.content[0] if resp.content else None
            text = first.text.strip() if isinstance(first, LLMTextBlock) else ""
            m = re.search(r"\{.*\}", text, re.DOTALL)
            parsed = json.loads(m.group()) if m else {}
            est = int(parsed.get("estimated_turns", kw_floor))
            files = parsed.get("files", [])
            reasoning = parsed.get("reasoning", "")
        except Exception:
            est, files, reasoning = kw_floor, [], ""

        # Take the max of LLM estimate and keyword floor
        est = max(est, kw_floor)

        # Per-block max_turns cap overrides the estimate
        block_max_turns = data.get("max_turns")
        if block_max_turns is not None:
            est = min(est, int(block_max_turns))

        block_estimates.append({
            "block_id": block.get("id"),
            "label": label,
            "estimated_turns": est,
            "files": files,
            "reasoning": reasoning,
        })
        all_files.extend(files)

    llm_total = sum(b["estimated_turns"] for b in block_estimates)
    suggested = max(llm_total + 5, history_floor, min_turns, 20)

    return {
        "suggested_max_turns": suggested,
        "blocks": block_estimates,
        "total_files": list(dict.fromkeys(all_files)),
    }
