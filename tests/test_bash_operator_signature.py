"""Tests for _bash_operator_signature — fixes #728 false positives."""
import re
import shlex


def _bash_operator_signature(command):
    """Same logic as hook_template.py. Kept inline for unit testing."""
    if not command:
        return ""
    segments = re.split(r'&&|\|\||\|(?!\|)|;', command)
    parts = []
    for seg in segments:
        try:
            tokens = shlex.split(seg.strip())
        except ValueError:
            continue
        if not tokens:
            continue
        sig = [tokens[0]]
        i = 1
        # Subcommand: next token only if it's a bareword (no whitespace = wasn't a multi-word quoted value)
        if i < len(tokens) and not tokens[i].startswith("-") and " " not in tokens[i]:
            sig.append(tokens[i])
            i += 1
        # Flags only if they're real flags (no whitespace = not embedded in quoted content)
        for t in tokens[i:]:
            if t.startswith("-") and " " not in t:
                sig.append(t)
        parts.append(" ".join(sig))
    return " ; ".join(parts)


def assert_match(pattern, command, should_match):
    sig = _bash_operator_signature(command)
    matched = bool(re.search(pattern, sig, re.IGNORECASE))
    assert matched is should_match, f"{command!r} → sig={sig!r}, pattern={pattern!r}, expected={should_match}, got={matched}"


def test_rm_rf_actual_command_fires():
    assert_match(r"\brm\s+-rf\b", "rm -rf /tmp/build", True)


def test_rm_rf_in_gh_body_does_not_fire():
    assert_match(r"\brm\s+-rf\b", 'gh issue create --body "contains rm -rf example"', False)


def test_rm_rf_in_git_commit_does_not_fire():
    assert_match(r"\brm\s+-rf\b", 'git commit -m "fix: remove rm -rf call from script"', False)


def test_force_push_fires():
    assert_match(r"git\s+push.*--force", "git push --force origin main", True)


def test_force_push_in_commit_does_not_fire():
    assert_match(r"git\s+push.*--force", 'git commit -m "add force-push docs"', False)


def test_vercel_prod_fires():
    assert_match(r"vercel.*--prod", "vercel deploy --prod", True)


def test_vercel_prod_in_echo_does_not_fire():
    assert_match(r"vercel.*--prod", 'echo "vercel deploy --prod example"', False)


def test_chained_rm_rf_fires():
    assert_match(r"\brm\s+-rf\b", "git add . && rm -rf node_modules", True)


def test_chained_rm_in_commit_does_not_fire():
    assert_match(r"\brm\s+-rf\b", 'git add . && git commit -m "rm -rf cleanup"', False)


def test_empty_command():
    assert _bash_operator_signature("") == ""


def test_unterminated_quote_does_not_crash():
    # Should skip the segment, not raise
    sig = _bash_operator_signature('git commit -m "unterminated')
    assert isinstance(sig, str)
