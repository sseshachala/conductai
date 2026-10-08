"""ConductGuard — policy endpoints.

GET    /guard/policies                — list custom + active pack rules
POST   /guard/policies                — create a custom rule
PATCH  /guard/policies/{rule_id}      — edit a rule (custom row OR pack override)
DELETE /guard/policies/{rule_id}      — delete a custom rule (pack rules can't be deleted)
POST   /guard/policies/generate       — LLM-generate a rule from a description
GET    /guard/policies/sync           — daemon sync, returns the active ruleset
POST   /guard/policies/reinstall-base — re-install the conduct-base pack
POST   /guard/policies/lint           — lint a ruleset

Endpoints live in ``policies_read``, ``policies_write`` and
``policies_lint``; schemas in ``policies_schemas``; shared helpers in
``policies_helpers``. This module aggregates the routers in the original
registration order and re-exports the moved names.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.modules.guard.routers.policies_schemas import (  # noqa: F401 — re-exports
    EnforcementCoverageOut, LintIssue, LintRequest, LintResponse, PackCoverageMatrixOut,
    PackSurfaceCounts, PolicyCreate, PolicyGenerateOut, PolicyGenerateRequest, PolicyOut,
    PolicyPatch, PolicySyncOut, PolicySyncRule,
)
from app.modules.guard.routers.policies_helpers import (  # noqa: F401 — re-exports
    _GENERATE_SYSTEM, _GENERATE_SYSTEM_FILE, _PROMPTS_DIR, _VALID_ACTIONS,
    _audit_exception_transitions, _bg_project_rule, _custom_to_out, _find_pack_rule,
    _get_anthropic_key, _org_ws_subquery, _pack_rule_to_out, _resolve_workspace_pack,
    _upsert_override, _validate_exception_metadata, _write_audit, _ws_uuid,
)
from app.modules.guard.routers.policies_read import (  # noqa: F401 — re-exports
    generate_policy, get_enforcement_coverage, get_pack_coverage_matrix, list_policies,
    sync_policies,
)
from app.modules.guard.routers.policies_write import (  # noqa: F401 — re-exports
    create_policy, delete_policy, patch_policy, reinstall_base,
)
from app.modules.guard.routers.policies_lint import (  # noqa: F401 — re-exports
    _MATCH_FIELDS, _VALID_FAIL_MODES, _lint_rules, lint_policy,
)
from app.modules.guard.routers import policies_lint as _policies_lint
from app.modules.guard.routers import policies_read as _policies_read
from app.modules.guard.routers import policies_write as _policies_write

router = APIRouter()
router.include_router(_policies_read.router)
router.include_router(_policies_write.router)
router.include_router(_policies_lint.router)
