"""
POST /workflows/generate  — natural language → Conduct-compliant YAML + graph

API key resolved from the workspace's credential vault (env_vars handle),
same pattern as the executor. Falls back to settings.anthropic_api_key.
"""
import pathlib
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
from app.dsl.loader import yaml_to_graph
from app.models.integration import Integration
from app.runtime.llm_client import AnthropicClient, LLMTextBlock

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/workflows", tags=["generate"])

_PROMPTS_DIR = pathlib.Path(__file__).parent.parent.parent / "prompts"
_SYSTEM_PROMPT = (_PROMPTS_DIR / "generate_workflow.txt").read_text(encoding="utf-8")


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
    from app.core.credentials import get_all_credentials
    store = get_all_credentials(db, workspace_id, environment_id=environment_id)
    return (
        (store.get("anthropic") or {}).get("api_key")
        or (store.get("env_vars") or {}).get("ANTHROPIC_API_KEY")
        or (store.get("env_vars") or {}).get("anthropic_api_key")
    )


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

    # If Claude produced invalid YAML (e.g. bare colons in strings), ask it to fix once
    try:
        _yaml.safe_load(raw)
    except _yaml.YAMLError:
        log.warning("generate.yaml_syntax_error_retrying")
        try:
            fix_response = llm.create(
                model="claude-sonnet-4-6",
                system="You are a YAML expert. Fix the YAML syntax errors in the user's input. "
                       "Use block scalars (|) for any string values containing colons, newlines, or special characters. "
                       "Output ONLY the corrected YAML, no explanation.",
                messages=[{"role": "user", "content": raw}],
                max_tokens=4096,
            )
            raw = _strip_fences(next(
                (b.text for b in fix_response.content if isinstance(b, LLMTextBlock)), raw
            ).strip())
        except Exception:
            pass  # fall through to validation which will surface the error

    try:
        parsed = _yaml.safe_load(raw)
        name = parsed.get("name", "generated-agent")

        # Claude naturally emits blocks as a list; DSL expects a dict keyed by block id.
        # Also normalize common generation quirks:
        #   - skip type=trigger (belongs in trigger section, not blocks)
        #   - mcp: hoist config.credential_key / config.tool_name to block level
        if isinstance(parsed.get("blocks"), list):
            blocks_dict = {}
            for i, block in enumerate(parsed["blocks"]):
                block = dict(block)
                block_id = block.pop("id", f"block_{i}")
                if block.get("type") == "trigger":
                    continue
                if block.get("type") == "mcp":
                    cfg = block.get("config") or {}
                    if not block.get("credential_key") and cfg.get("credential_key"):
                        block["credential_key"] = cfg["credential_key"]
                    if not block.get("tool_name") and cfg.get("tool_name"):
                        block["tool_name"] = cfg["tool_name"]
                    # hoist provider (server UUID from mcp_servers) set by canvas MCP block
                    if not block.get("provider") and cfg.get("provider"):
                        block["provider"] = cfg["provider"]
                blocks_dict[block_id] = block
            parsed["blocks"] = blocks_dict

        from app.dsl.schema import Workflow as _Workflow
        dsl = _Workflow.model_validate(parsed)
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
