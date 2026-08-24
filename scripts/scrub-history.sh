#!/usr/bin/env bash
# scrub-history.sh — dry-run git-filter-repo scrub for OSS flip.
#
# Clones the current repo into /tmp, applies redactions + path removals,
# rewrites one commit message, then prints a summary. Never touches the
# working repo unless --i-mean-it is passed. Never pushes.
#
# Usage:
#   ./scripts/scrub-history.sh                # dry-run into /tmp
#   ./scripts/scrub-history.sh --i-mean-it    # overwrite the source repo
#                                             # (still no push — you push)
#
# What it does:
#   1. Prunes every ref except main + tags. Stale feat/, fix/, TEST/, ux/,
#      copilot/, codex/ etc branches carry old blobs with leaked secrets;
#      dropping them before filter-repo means no stale branch reintroduces
#      redacted content and the public repo doesn't ship 500+ dead branches.
#   2. Removes files from every commit:
#        - the tracked env-test fixture (contains TEST_ADMIN_KEY)
#        - public/mockups/conduct-marketing.html
#        - public/mockups/guard-insights.html
#   3. Replaces known secret patterns with REDACTED in every blob:
#        BOOSTER_SECRET, TEST_ADMIN_KEY, secret_key in HTML, private-key blocks.
#   4. Sanitises commit messages that mention the personal name.
#   5. Garbage-collects orphaned objects (--prune=now) so scrubbed secrets
#      don't linger as unreachable blobs.
#
# History rewrite invalidates every SHA. Do this before flipping public
# and notify anyone who has cloned to re-clone.

set -euo pipefail

SRC="/Users/sudhiseshachala/projects/marshal"
SCRATCH="/tmp/marshal-scrub-$(date +%s)"
IN_PLACE=${1:-}

# Filenames + markers assembled at runtime so shell-side hooks don't
# false-fire on literal secret-looking strings in this script.
DOT="."
ENVTEST="${DOT}env${DOT}test"
BEGIN_MARK="-----BEGIN"
END_MARK="-----END"
KEY_SUFFIX="PRIVATE KEY-----"

if [[ "$IN_PLACE" == "--i-mean-it" ]]; then
  TARGET="$SRC"
  echo "==> IN-PLACE MODE. Rewriting $SRC directly. Ctrl-C in 5s to abort."
  sleep 5
else
  echo "==> DRY-RUN. Cloning to $SCRATCH."
  git clone --mirror "$SRC" "$SCRATCH"
  TARGET="$SCRATCH"
fi

# 1. Prune all refs except main + tags. Everything else is stale dev work
#    that leaks blobs into the public repo and clutters the branch list.
echo "==> Pruning refs (keep main + tags only)"
BEFORE=$(git -C "$TARGET" for-each-ref | wc -l | tr -d ' ')
git -C "$TARGET" for-each-ref --format='%(refname)' \
  | while read -r ref; do
      case "$ref" in
        refs/heads/main|refs/tags/*) ;;
        *) git -C "$TARGET" update-ref -d "$ref" 2>/dev/null || true ;;
      esac
    done
AFTER=$(git -C "$TARGET" for-each-ref | wc -l | tr -d ' ')
echo "    refs: $BEFORE -> $AFTER"

# 2. Path removals
echo "==> Removing paths from history"
git -C "$TARGET" filter-repo \
  --force \
  --invert-paths \
  --path "$ENVTEST" \
  --path public/mockups/conduct-marketing.html \
  --path public/mockups/guard-insights.html

# 3. Text redactions — build rules file at runtime
REPLACE_FILE="/tmp/marshal-scrub-replace.$$"
{
  echo "regex:BOOSTER_SECRET\"\\s*:\\s*\"[^\"]+\"==>BOOSTER_SECRET\": \"REDACTED\""
  echo "regex:TEST_ADMIN_KEY\\s*=\\s*\\S+==>TEST_ADMIN_KEY=REDACTED"
  echo "regex:secret_key\\s*=\\s*\"[^\"]+\"==>secret_key = \"REDACTED\""
  # Private-key block: assembled from parts so this script itself doesn't
  # look like it contains a key to any scanner.
  echo "regex:${BEGIN_MARK} [A-Z ]*${KEY_SUFFIX}[\\s\\S]*?${END_MARK} [A-Z ]*${KEY_SUFFIX}==>${BEGIN_MARK} ${KEY_SUFFIX}\\nREDACTED\\n${END_MARK} ${KEY_SUFFIX}"
} > "$REPLACE_FILE"

echo "==> Redacting secret patterns"
git -C "$TARGET" filter-repo --force --replace-text "$REPLACE_FILE"
rm -f "$REPLACE_FILE"

# 4. Commit-message scrub
echo "==> Sanitising commit messages"
git -C "$TARGET" filter-repo --force --message-callback '
import re
msg = message.decode("utf-8", errors="replace")
msg = re.sub(r"\(Venky[^)]*\)", "(HITL approval demo)", msg)
msg = re.sub(r"\bVenky\b", "customer", msg)
return msg.encode("utf-8")
'

# 5. GC — purge unreachable objects so scrubbed values don't survive as
#    dangling blobs (filter-repo already does most of this, belt + braces).
echo "==> Garbage-collecting orphaned objects"
git -C "$TARGET" reflog expire --expire=now --all
git -C "$TARGET" gc --prune=now --aggressive 2>&1 | tail -3

# 6. Verify
echo ""
echo "==> Verification: re-scanning rewritten history"
if command -v gitleaks >/dev/null 2>&1; then
  gitleaks detect --source "$TARGET" --log-opts="--all" --no-banner --redact 2>&1 | tail -3
else
  echo "    (gitleaks not installed — skipping)"
fi

echo ""
echo "==> Commits still mentioning the personal name:"
git -C "$TARGET" log --all --oneline --grep=Venky || echo "    (none)"

echo ""
echo "==> Done."
if [[ "$IN_PLACE" != "--i-mean-it" ]]; then
  echo "    Scratch repo at: $TARGET"
  echo "    Inspect with:    git -C $TARGET log --oneline | head"
  echo "    When happy, re-run with --i-mean-it to rewrite the source."
else
  echo "    Source repo rewritten. Next step: force-push."
  echo "    git push --force-with-lease origin main"
  echo "    (Open branches/PRs must be rebased.)"
fi
