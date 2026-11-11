"""Regression guard: every Guard audit writer goes through the chain helpers.

Static scan of ``app/``. A writer that inserts a ``GuardAuditEvent`` (ORM or raw
SQL) without ``chain_begin`` + ``chain_seal`` / ``chain_seal_values`` would leave
an unchained row in the workspace history, so this test fails for it.

Mutations of existing rows are allowlisted explicitly with the reason each one is
safe for the hash (see docs/audit-log-verification.md).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
MODELS_DIR = APP / "modules" / "guard" / "models"

# Raw SQL INSERT/UPDATE/DELETE against the table, by statement kind.
_SQL = {
    "INSERT": re.compile(r"INSERT\s+INTO\s+guard_audit_events\b", re.I),
    "UPDATE": re.compile(r"\bUPDATE\s+guard_audit_events\b", re.I),
    "DELETE": re.compile(r"DELETE\s+FROM\s+guard_audit_events\b", re.I),
}
_SEAL_NAMES = ("chain_seal", "chain_seal_values", "chain_seal_stored_row")

# (file relative to app/, kind) -> why it does not break the chain.
ALLOWED_MUTATIONS = {
    ("guard/audit.py", "UPDATE"):
        "finalize() seals the two-phase row (new ts/previous_hash/entry_hash in the same "
        "transaction); renew_lease() only touches lease_expires_at on an unsealed 'accepted' row",
    ("modules/guard/durable_audit_reconciler.py", "UPDATE"):
        "orphaning an expired unsealed row, sealed in the same transaction",
    ("modules/guard/routers/blocks.py", "UPDATE"):
        "writes share_token_hash, which hash_version 3 excludes from the hash",
}


# Inserts that are deliberately unsealed: the row is sealed later by the named function.
UNSEALED_INSERTS = {
    ("guard/audit.py", "insert_accepted"):
        "two-phase gateway row: its fields change at finalize(), which seals it (or the reconciler, "
        "if it never finalizes). entry_hash stays NULL until then, so the verifier skips it",
}


def _functions(tree: ast.AST):
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _innermost(tree: ast.AST, lineno: int):
    best = None
    for fn in _functions(tree):
        if fn.lineno <= lineno <= (fn.end_lineno or fn.lineno):
            if best is None or fn.lineno >= best.lineno:
                best = fn
    return best


def _scan():
    for path in sorted(APP.rglob("*.py")):
        if MODELS_DIR in path.parents:
            continue  # the ORM declaration itself
        source = path.read_text()
        if "guard_audit_events" not in source and "GuardAuditEvent" not in source:
            continue
        yield path, source, ast.parse(source)


def _calls_seal(source: str, tree: ast.AST, lineno: int) -> bool:
    fn = _innermost(tree, lineno)
    body = ast.get_source_segment(source, fn) if fn else source
    return any(re.search(rf"\b{name}\b", body or "") for name in _SEAL_NAMES) and bool(
        re.search(r"\bchain_begin\b", body or "") or re.search(r"\bchain_seal_stored_row\b", body or ""))


def test_every_guard_audit_insert_goes_through_the_chain_helpers():
    offenders = []
    for path, source, tree in _scan():
        rel = path.relative_to(APP).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if name == "GuardAuditEvent" and not _calls_seal(source, tree, node.lineno):
                    offenders.append(f"{rel}:{node.lineno} GuardAuditEvent(...) without chain_begin+chain_seal")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                fn = _innermost(tree, node.lineno)
                if (_SQL["INSERT"].search(node.value)
                        and (rel, getattr(fn, "name", "")) not in UNSEALED_INSERTS
                        and not _calls_seal(source, tree, node.lineno)):
                    offenders.append(f"{rel}:{node.lineno} raw INSERT without chain_begin+chain_seal_values")
    assert not offenders, "unchained Guard audit writers:\n" + "\n".join(offenders)


def test_no_unreviewed_update_or_delete_of_guard_audit_rows():
    offenders = []
    for path, _source, tree in _scan():
        rel = path.relative_to(APP).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for kind in ("UPDATE", "DELETE"):
                    if _SQL[kind].search(node.value) and (rel, kind) not in ALLOWED_MUTATIONS:
                        offenders.append(f"{rel}:{node.lineno} raw {kind} of guard_audit_events")
    assert not offenders, (
        "sealed audit rows are append-only; add the writer to ALLOWED_MUTATIONS with a reason "
        "only if the change cannot alter a hashed field:\n" + "\n".join(offenders))


def test_chained_updates_stay_sealed():
    """finalize() and the reconciler must re-seal; renew_lease() is the only unsealed UPDATE."""
    for rel, fn_name in (("guard/audit.py", "finalize"),
                         ("modules/guard/durable_audit_reconciler.py", "_orphan_and_seal")):
        source = (APP / rel).read_text()
        fn = next(n for n in _functions(ast.parse(source)) if n.name == fn_name)
        body = ast.get_source_segment(source, fn)
        assert "chain_begin" in body and "chain_seal_stored_row" in body, f"{rel}:{fn_name}"


def test_unsealed_insert_allowlist_is_current():
    """An allowlisted unsealed insert must still exist and still be the only one."""
    for (rel, fn_name) in UNSEALED_INSERTS:
        source = (APP / rel).read_text()
        fn = next(n for n in _functions(ast.parse(source)) if n.name == fn_name)
        assert _SQL["INSERT"].search(ast.get_source_segment(source, fn))
