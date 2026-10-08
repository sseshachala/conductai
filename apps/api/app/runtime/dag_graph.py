"""DAG runner graph utilities and per-block retry (split from dag_runner.py; re-exported there)."""
from __future__ import annotations

import json
import time
from collections import defaultdict, deque

import structlog

from app.runtime.exceptions import ApprovalRequired, ClarificationRequired
from app.runtime.llm_client import LLMUpstreamError

log = structlog.get_logger("app.runtime.dag_runner")


# ── graph utilities ───────────────────────────────────────────────────────────

def _topological_sort(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Kahn's algorithm — returns nodes in execution order."""
    id_to_node = {n["id"]: n for n in nodes}
    in_degree: dict[str, int] = defaultdict(int)
    adjacency: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        adjacency[src].append(tgt)
        in_degree[tgt] += 1

    queue = deque(n["id"] for n in nodes if in_degree[n["id"]] == 0)
    order: list[dict] = []

    while queue:
        nid = queue.popleft()
        order.append(id_to_node[nid])
        for neighbor in adjacency[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(nodes):
        cycle_ids = [n["id"] for n in nodes if n["id"] not in {o["id"] for o in order}]
        raise RuntimeError(f"Workflow contains a cycle involving blocks: {cycle_ids}")
    return order


def _find_skipped_blocks(nodes: list[dict], edges: list[dict], logic_routes: dict[str, str]) -> set[str]:
    """
    Given resolved logic block routes {block_id: 'pass'|'fail'}, return the set
    of block IDs that are unreachable via live edges.

    Uses forward reachability: start from entry blocks (no incoming edges),
    follow only live edges (excluding non-taken logic branches), and mark
    everything not reached as skipped.

    This correctly handles convergent paths where a block is both the
    non-taken target of a logic block AND reachable via a live edge from
    another block (e.g. record_outcome after create_tracking_issue).
    """
    if not logic_routes:
        return set()

    all_node_ids = {n["id"] for n in nodes}

    # Build set of dead (source, target) pairs — non-taken logic branch edges
    dead_edges: set[tuple[str, str]] = set()
    for edge in edges:
        src = edge.get("source", "")
        if src in logic_routes:
            handle = edge.get("sourceHandle") or "pass"
            if handle != logic_routes[src]:
                dead_edges.add((src, edge["target"]))

    # Entry blocks: no incoming edges at all
    has_incoming = {e["target"] for e in edges}
    reachable: set[str] = all_node_ids - has_incoming

    # Forward BFS following only live edges
    changed = True
    while changed:
        changed = False
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if (src, tgt) in dead_edges:
                continue
            if src in reachable and tgt not in reachable:
                reachable.add(tgt)
                changed = True

    return all_node_ids - reachable


# ── retry wrapper ─────────────────────────────────────────────────────────────

def _with_retry(execute_fn, retry_cfg: dict, *args, **kwargs):
    """
    Wrap execute_fn with per-block retry logic.

    retry_cfg keys:
      max      — int, total attempts (default 1 = no retry)
      backoff  — "fixed" | "exponential"  (default "fixed")
      on       — list of error categories to retry:
                 "tool_error" | "timeout" | "llm_parse_error"
                 (default ["tool_error", "timeout"])
    """
    max_attempts = int(retry_cfg.get("max", 1)) if isinstance(retry_cfg, dict) else int(getattr(retry_cfg, "max", 1))
    backoff = retry_cfg.get("backoff", "fixed") if isinstance(retry_cfg, dict) else getattr(retry_cfg, "backoff", "fixed")
    _on_raw = retry_cfg.get("on", ["tool_error", "timeout"]) if isinstance(retry_cfg, dict) else getattr(retry_cfg, "on", ["tool_error", "timeout"])
    on_categories = set(_on_raw)

    # Hard floor — must have at least one attempt
    max_attempts = max(1, max_attempts)

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return execute_fn(*args, **kwargs)
        except (ApprovalRequired, ClarificationRequired, PermissionError) as e:
            # These are flow-control pauses or governance blocks — never retry
            raise
        except RuntimeError as e:
            # Guard blocks and turn/cost budget exhaustion are not retryable
            raise
        except LLMUpstreamError:
            # Adapter already ran its own retry ladder (up to 3 attempts with
            # backoff). Retrying at the block level would multiply calls (3×N)
            # and emit false-terminal llm_upstream_blocked events per outer
            # attempt. If it failed 3× at the adapter, the upstream is down —
            # block-level retry buys nothing except cost + noise.
            raise
        except TimeoutError as e:
            if "timeout" not in on_categories:
                raise
            last_exc = e
        except (json.JSONDecodeError, ValueError) as e:
            if "llm_parse_error" not in on_categories:
                raise
            last_exc = e
        except Exception as e:
            if "tool_error" not in on_categories:
                raise
            last_exc = e

        # Not on the last attempt — sleep before retry
        if attempt < max_attempts - 1:
            if backoff == "exponential":
                time.sleep(2 ** attempt)
            else:
                time.sleep(2)

    raise last_exc  # type: ignore[misc]

