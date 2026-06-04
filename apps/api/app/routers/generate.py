"""
POST /workflows/generate  — natural language → Conduct-compliant YAML + graph

API key resolved from the workspace's credential vault (env_vars handle),
same pattern as the executor. Falls back to settings.anthropic_api_key.
"""
import re
import structlog
import yaml as _yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id
from app.core.config import settings
from app.core.crypto import decrypt
from app.core.database import get_db
from app.dsl.loader import load_workflow_yaml, yaml_to_graph
from app.models.integration import Integration
from app.runtime.llm_client import AnthropicClient, LLMTextBlock

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/workflows", tags=["generate"])

_SYSTEM_PROMPT = """You are an expert at writing Conduct playbook YAML files.
Conduct is a YAML-based agent automation platform. Given a plain-English description,
output ONLY valid Conduct YAML — no prose, no markdown fences, no explanation.

## YAML structure

name: <short slug, snake_case>
description: <one sentence>
trigger:
  type: <webhook|schedule|manual>
  # webhook needs: event: push|pull_request|issues|issue_comment
  # schedule needs: cron: "0 9 * * 1"

blocks:
  - id: <snake_case_id>
    type: <trigger|brain|tool|logic|memory|approval|output|mcp>
    label: <Human readable label>
    description: <for brain blocks this is the system prompt>

## Block types

brain — LLM reasoning step
  description: <system prompt>
  mode: single | agentic   (agentic = can use tools)
  model: claude-haiku-4-5-20251001 | claude-sonnet-4-6 | claude-opus-4-7

mcp — MCP server call (PREFERRED over tool when provider has MCP support)
  config:
    provider: vercel | linear | railway | jira | github | slack | custom
    server_url: <MCP server URL>
    credential_key: <env var name e.g. VERCEL_TOKEN>
    tool_name: <MCP tool name>
    transport: http | sse | auto

tool — direct API action (use only when no MCP available)
  integration: github | slack | linear | jira | vercel | railway
  action: <action name>
  params: {key: "{{ref}}" or literal}

logic — conditional branch
  condition: "{{block_id.field}} == 'value'"
  next: {pass: <block_id>, fail: <block_id>}

memory — read/write context
  action: read | write
  key: <key>
  scope: repo | workspace

approval — pause for human
  via: slack | email | both
  channel: <slack channel>
  message: <message>

output — send notification
  integration: slack | email | github
  action: post_message | send_email | post_comment
  params: {channel: "#channel", message: "{{ref}}"}

## Rules
- Use {{block_id.field}} to reference previous outputs
- Every block except last needs: next: <next_block_id>
- Logic blocks use: next: {pass: id, fail: id}
- Prefer mcp over tool for Vercel, Linear, Railway, Jira, GitHub, Slack
- End with a comment: # requires: ENV_VAR1, ENV_VAR2

Output ONLY the YAML. No markdown. No explanation."""


class GenerateRequest(BaseModel):
    prompt: str
    environment_id: str | None = None


class GenerateResponse(BaseModel):
    yaml: str
    graph: dict
    name: str
    required_credentials: list[str]


def _strip_fences(text: str) -> str:
    text = re.sub(r"^```ya?ml\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


def _extract_credentials(raw_yaml: str) -> list[str]:
    match = re.search(r"#\s*requires:\s*(.+)", raw_yaml)
    if not match:
        return []
    return [c.strip() for c in match.group(1).split(",") if c.strip()]


def _resolve_anthropic_key(workspace_id: str, environment_id: str | None, db: Session) -> str | None:
    """Resolve ANTHROPIC_API_KEY from the workspace credential vault, same as executor."""
    from app.models.environment import Environment as _Env

    env_ids: list[str] = []
    if environment_id:
        env_ids.append(environment_id)
    # Always include Default environment as fallback
    default_env = db.query(_Env).filter(
        _Env.workspace_id == workspace_id,
        _Env.name == "Default",
    ).first()
    if default_env and str(default_env.id) not in env_ids:
        env_ids.append(str(default_env.id))

    for eid in env_ids:
        rows = db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.environment_id == eid,
            Integration.handle == "env_vars",
        ).all()
        for row in rows:
            if not row.encrypted_credentials:
                continue
            env_vars = decrypt(row.encrypted_credentials) or {}
            key = env_vars.get("ANTHROPIC_API_KEY") or env_vars.get("anthropic_api_key")
            if key:
                return key

    return None


@router.post("/generate", response_model=GenerateResponse)
async def generate_workflow(
    body: GenerateRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    api_key = (
        _resolve_anthropic_key(workspace_id, body.environment_id, db)
        or settings.anthropic_api_key
    )
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not found — add it in Settings → Environments",
        )

    try:
        llm = AnthropicClient(api_key=api_key)
        response = llm.create(
            model="claude-sonnet-4-6",
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": body.prompt}],
            max_tokens=4096,
        )
        raw = next(
            (b.text for b in response.content if isinstance(b, LLMTextBlock)),
            "",
        ).strip()
    except Exception as exc:
        log.error("generate.llm_error", error=str(exc))
        raise HTTPException(status_code=502, detail=f"Generation failed: {exc}")

    raw = _strip_fences(raw)

    try:
        parsed = _yaml.safe_load(raw)
        name = parsed.get("name", "generated-agent")
        dsl = load_workflow_yaml(raw)
        graph = yaml_to_graph(dsl)
    except Exception as exc:
        log.error("generate.parse_error", error=str(exc), yaml=raw[:500])
        raise HTTPException(status_code=422, detail=f"Generated YAML invalid: {exc}")

    return GenerateResponse(
        yaml=raw,
        graph=graph,
        name=name,
        required_credentials=_extract_credentials(raw),
    )
