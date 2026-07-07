"""Tests for _compute_blast_radius."""
from conduct_cli.hooks.posttooluse import _compute_blast_radius


def test_bash_rm_rf_is_destructive():
    r = _compute_blast_radius("bash", {"command": "rm -rf apps/web/.next"}, "")
    assert r["tier"] == "destructive"


def test_bash_git_push_is_repo():
    r = _compute_blast_radius("bash", {"command": "git push origin main"}, "")
    assert r["tier"] == "repo"


def test_bash_curl_is_network():
    r = _compute_blast_radius("bash", {"command": "curl https://api.example.com"}, "")
    assert r["tier"] == "network"


def test_bash_local_counts_file_lines():
    output = "src/foo.py\nsrc/bar.py\nDone"
    r = _compute_blast_radius("bash", {"command": "ls"}, output)
    assert r["tier"] == "local"
    assert r["files"] == 2


def test_write_returns_local_with_symbols():
    r = _compute_blast_radius("write", {"content": "line1\nline2\nline3"}, "")
    assert r["files"] == 1
    assert r["symbols"] == 3
    assert r["tier"] == "local"


def test_read_returns_none():
    assert _compute_blast_radius("read", {}, "") is None


def test_grep_returns_none():
    assert _compute_blast_radius("grep", {}, "") is None


def test_multiedit_counts_edits():
    r = _compute_blast_radius("multiedit", {"edits": [{}, {}, {}]}, "")
    assert r["files"] == 3
