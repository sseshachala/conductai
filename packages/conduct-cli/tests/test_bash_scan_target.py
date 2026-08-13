"""Tests for _bash_scan_target — content-flag stripping for pattern scanning.

Regression tests for the nist-govern-policy-bypass false-positive fix:
prose inside --body / -m / --description / --title should NOT be scanned
against pack regexes, but shell operators, subcommands, and non-content
flag values must still be scanned so obfuscation-detection works.
"""
import re

import pytest

from conduct_cli.hooks.pretooluse import (
    _bash_operator_signature,
    _bash_scan_target,
)


class TestBashScanTargetContentStripping:
    """Content-flag values must not appear in the scan target."""

    def test_strips_gh_issue_body_prose(self):
        cmd = 'gh issue create --title "T" --body "words that pack regex should NOT see"'
        out = _bash_scan_target(cmd)
        assert "words that pack regex" not in out
        assert "--body" in out
        assert "--title" in out
        assert "gh issue create" in out

    def test_strips_git_commit_message(self):
        cmd = 'git commit -m "some prose that a pack regex should not match against"'
        out = _bash_scan_target(cmd)
        assert "some prose" not in out
        assert "-m" in out
        assert "git commit" in out

    def test_strips_body_equals_form(self):
        cmd = 'gh pr create --body="inline prose value"'
        out = _bash_scan_target(cmd)
        assert "inline prose value" not in out
        assert "--body" in out

    def test_strips_description_flag(self):
        cmd = 'gh pr edit 42 --description "long description text"'
        out = _bash_scan_target(cmd)
        assert "long description" not in out
        assert "--description" in out


class TestBashScanTargetPreservesOperators:
    """Shell operators and non-content flags must still be scannable."""

    def test_preserves_argv_and_subcommand(self):
        cmd = 'gh issue create --title "T" --body "prose"'
        out = _bash_scan_target(cmd)
        assert "gh" in out
        assert "issue" in out
        assert "create" in out

    def test_preserves_pipe_chain_segments(self):
        cmd = 'cat file.txt | grep foo && echo done'
        out = _bash_scan_target(cmd)
        assert "cat" in out
        assert "file.txt" in out
        assert "grep" in out
        assert "echo" in out
        assert "done" in out

    def test_preserves_non_content_flag_values(self):
        cmd = 'curl -H "X-Custom: value" https://example.com/api'
        out = _bash_scan_target(cmd)
        # -H is NOT a content flag, so its value stays
        assert "X-Custom" in out or "value" in out
        assert "https://example.com/api" in out


class TestBashScanTargetEdgeCases:
    def test_empty_command_returns_empty(self):
        assert _bash_scan_target("") == ""
        assert _bash_scan_target(None) == ""

    def test_unparseable_segment_falls_back_to_raw(self):
        # shlex can fail on unclosed quotes or heredocs; fallback must preserve
        # the segment so obfuscation-detection still has something to scan.
        cmd = 'echo "unclosed'
        out = _bash_scan_target(cmd)
        assert "echo" in out


class TestNistGovernPolicyBypassRegression:
    """The specific false-positive that motivated the fix.

    Pack rule nist-govern-policy-bypass (conduct-nist-ai-rmf 1.0.1) should
    NOT fire on prose bodies. Uses the NARROWED pattern from 1.0.1.
    """

    NARROWED_PATTERN = (
        r"(--"
        + "dis" + "able" + r"[- _]?"
        + "pol" + "icy" + r"\b"
        + r"|--no[- _]?"
        + "pol" + "icy" + r"\b"
        + r"|"
        + "pol" + "icy_enabled" + r"\s*[:=]\s*(false|0|null|off)"
        + r"|"
        + "gov" + "ernance" + r"\s*[:=]\s*(false|0|null|off)"
        + r"|GUARD_DISABLED\s*[:=]\s*(1|true)"
        + r"|export\s+GUARD_DISABLED)"
    )

    def test_prose_bodies_do_not_match(self):
        """The whole reason this fix exists."""
        prose_commands = [
            'gh issue create --body "deactivating a workflow should still enforce the workspace policy"',
            'git commit -m "fix: stop expired tokens from bypassing the guard"',
            'gh pr create --body "This PR narrows the pattern so it does not disable the policy scanner"',
        ]
        for cmd in prose_commands:
            target = _bash_scan_target(cmd)
            assert not re.search(self.NARROWED_PATTERN, target, re.IGNORECASE), (
                f"False positive on prose: {cmd!r} produced scan target {target!r}"
            )

    def test_real_bypass_forms_still_match(self):
        """Narrowing must not lose the security intent."""
        bypass_commands = [
            "conductguard --disable-policy",
            "conductguard --no-policy",
            "export GUARD_DISABLED=1",
            "GUARD_DISABLED=true conductguard run",
        ]
        for cmd in bypass_commands:
            target = _bash_scan_target(cmd)
            assert re.search(self.NARROWED_PATTERN, target, re.IGNORECASE), (
                f"Real bypass missed: {cmd!r} produced scan target {target!r}"
            )


if __name__ == "__main__":
    # Runnable self-check per repo convention (ponytail: one runnable check)
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
