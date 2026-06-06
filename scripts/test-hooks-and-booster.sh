#!/usr/bin/env bash
# test-hooks-and-booster.sh — smoke-tests PreCompact/SessionStart hooks + Agent Booster RRF
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0; FAIL=0

# Python that has booster's deps (numpy, tree-sitter, etc.)
BPYTHON="${BOOSTER_PYTHON:-/opt/homebrew/opt/python@3.11/bin/python3.11}"
if ! "$BPYTHON" -c "import numpy" &>/dev/null; then
  BPYTHON="$(which python3.11 2>/dev/null || which python3 2>/dev/null || echo python3)"
fi

green() { printf "  \033[32m✓\033[0m %s\n" "$*"; }
red()   { printf "  \033[31m✗\033[0m %s\n" "$*"; }

check() {
  local label="$1"; shift
  if eval "$@" &>/dev/null 2>&1; then
    green "$label"; PASS=$((PASS+1))
  else
    red   "$label"; FAIL=$((FAIL+1))
  fi
}

echo ""
echo "═══════════════════════════════════════════════"
echo "  Conduct · Hook + Booster test suite"
echo "═══════════════════════════════════════════════"

# ── 1. PreCompact hook ───────────────────────────────────────────────────
echo ""
echo "▸ PreCompact hook"

check "hook exits 0" \
  "bash -c \"python3 '$ROOT/.claude/hooks/guard-precompact.py' </dev/null\""

check "snapshot written" \
  "test -f '$HOME/.conductguard/session_snapshot.json'"

check "snapshot has git_branch" \
  "python3 -c \"import json,pathlib; d=json.loads(pathlib.Path('$HOME/.conductguard/session_snapshot.json').read_text()); assert d['tier1'].get('git_branch')\""

check "snapshot has recent_commits" \
  "python3 -c \"import json,pathlib; d=json.loads(pathlib.Path('$HOME/.conductguard/session_snapshot.json').read_text()); assert d['tier1'].get('recent_commits')\""

check "no leftover .tmp file" \
  "! test -f '$HOME/.conductguard/session_snapshot.tmp'"

# ── 2. SessionStart hook ─────────────────────────────────────────────────
echo ""
echo "▸ SessionStart hook"

check "hook exits 0" \
  "echo '{}' | python3 '$ROOT/.claude/hooks/guard-session-start.py'"

check "prints 'Session resumed'" \
  "echo '{}' | python3 '$ROOT/.claude/hooks/guard-session-start.py' | grep -q 'Session resumed'"

check "stale snapshot → no output" ""$BPYTHON" - <<'PYEOF'
import json, pathlib, subprocess
p = pathlib.Path('$HOME/.conductguard/session_snapshot.json')
d = json.loads(p.read_text())
orig = d['compacted_at']
d['compacted_at'] = '2020-01-01T00:00:00+00:00'
p.write_text(json.dumps(d))
out = subprocess.run(['python3', '$ROOT/.claude/hooks/guard-session-start.py'],
                     input='{}', capture_output=True, text=True).stdout.strip()
d['compacted_at'] = orig
p.write_text(json.dumps(d))
assert out == '', f'expected empty, got: {out!r}'
PYEOF"

check "fresh snapshot → output again" \
  "echo '{}' | python3 '$ROOT/.claude/hooks/guard-session-start.py' | grep -q 'Session resumed'"

# ── 3. Agent Booster pytest suite ────────────────────────────────────────
echo ""
echo "▸ Agent Booster — existing test suite"

check "pytest passes" \
  "cd '$ROOT/tools/booster' && '$BPYTHON' -m pytest tests/ -q --tb=short"

# ── 4. RRF unit tests ────────────────────────────────────────────────────
echo ""
echo "▸ Agent Booster — RRF fusion"

check "rrf_search returns correct symbol" ""$BPYTHON" - <<'PYEOF'
import tempfile, pathlib, sys
sys.path.insert(0, '$ROOT/tools/booster')
from booster.indexer import SymbolIndexer
with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    (root / '.booster').mkdir()
    (root / 'auth.py').write_text('def authenticate_user(token):\n    pass\ndef validate_token(t):\n    pass\n')
    ix = SymbolIndexer(root); ix.index_all()
    results = ix.rrf_search('authenticate user')
    assert results and any(r['name'] == 'authenticate_user' for r in results)
PYEOF"

check "rrf_search_file works per-file" ""$BPYTHON" - <<'PYEOF'
import tempfile, pathlib, sys
sys.path.insert(0, '$ROOT/tools/booster')
from booster.indexer import SymbolIndexer
with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    (root / '.booster').mkdir()
    (root / 'utils.py').write_text('def process(data):\n    pass\ndef load(path):\n    pass\n')
    ix = SymbolIndexer(root); ix.index_all()
    results = ix.rrf_search_file('utils.py', 'process data')
    assert results
PYEOF"

check "rrf returns >= keyword-only count" ""$BPYTHON" - <<'PYEOF'
import tempfile, pathlib, sys
sys.path.insert(0, '$ROOT/tools/booster')
from booster.indexer import SymbolIndexer
with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    (root / '.booster').mkdir()
    (root / 'api.py').write_text(
        'def authenticate_user(token): pass\n'
        'def create_session(user): pass\n'
        'def revoke_token(t): pass\n'
        'def refresh_token(t): pass\n'
    )
    ix = SymbolIndexer(root); ix.index_all()
    kw  = ix.search('authenticate', limit=10)
    rrf = ix.rrf_search('authenticate', limit=10)
    assert len(rrf) >= len(kw), f'rrf={len(rrf)} < kw={len(kw)}'
PYEOF"

# ── 5. 5KB gate ──────────────────────────────────────────────────────────
echo ""
echo "▸ Agent Booster — 5 KB smart_read gate"

check "gate caps output or adds truncation notice" ""$BPYTHON" - <<'PYEOF'
import tempfile, pathlib, sys
sys.path.insert(0, '$ROOT/tools/booster')
from booster.indexer import SymbolIndexer
from booster.retriever import smart_read, _MAX_OUTPUT_BYTES
with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    (root / '.booster').mkdir()
    body = '\n'.join(f'    x_{i} = {i}' for i in range(300))
    src  = '\n\n'.join(f'def fn_{i}(inp):\n{body}\n    return inp' for i in range(6))
    f    = root / 'big.py'
    f.write_text(src)
    ix = SymbolIndexer(root); ix.index_all()
    result = smart_read(f, 'process input', ix)
    size   = len(result.encode())
    assert size <= _MAX_OUTPUT_BYTES or '[Truncated:' in result, \
        f'{size} bytes, no truncation notice'
PYEOF"

check "_MAX_OUTPUT_BYTES is 5000" ""$BPYTHON" - <<'PYEOF'
import sys; sys.path.insert(0, '$ROOT/tools/booster')
from booster.retriever import _MAX_OUTPUT_BYTES
assert _MAX_OUTPUT_BYTES == 5_000
PYEOF"

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════"
TOTAL=$((PASS+FAIL))
if [ "$FAIL" -eq 0 ]; then
  printf "  \033[32mAll %d tests passed\033[0m\n" "$TOTAL"
else
  printf "  \033[31m%d/%d passed · %d failed\033[0m\n" "$PASS" "$TOTAL" "$FAIL"
  exit 1
fi
echo "═══════════════════════════════════════════════"
echo ""
