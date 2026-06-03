"""
POST /workflows/generate  — natural language → Conduct-compliant YAML + graph
"""
import os
import re
import structlog
import yaml as _yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_workspace_id
from app.dsl.loader import load_workflow_yaml, yaml_to_graph
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


@router.post("/generate", response_model=GenerateResponse)
async def generate_workflow(
    body: GenerateRequest,
    workspace_id: str = Depends(get_workspace_id),
):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI generation not configured — set ANTHROPIC_API_KEY")

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
