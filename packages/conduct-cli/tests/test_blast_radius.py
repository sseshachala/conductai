"""Tests for _compute_blast_radius."""
from unittest.mock import patch
from conduct_cli.hooks.posttooluse import _compute_blast_radius


def _no_git(fn):
    """Patch _git_context to return (None, None) so tests don't shell out."""
    from functools import wraps
    @wraps(fn)
    def wrapper(*a, **kw):
        with patch("conduct_cli.hooks.posttooluse._git_context", return_value=(None, None)):
            return fn(*a, **kw)
    return wrapper


@_no_git
def test_bash_rm_rf_is_destructive():
    r = _compute_blast_radius("bash", {"command": "rm -rf apps/web/.next"}, "")
    assert r["tier"] == "destructive"


@_no_git
def test_bash_git_push_is_repo():
    r = _compute_blast_radius("bash", {"command": "git push origin main"}, "")
    assert r["tier"] == "repo"


@_no_git
def test_bash_curl_is_network():
    r = _compute_blast_radius("bash", {"command": "curl https://api.example.com"}, "")
    assert r["tier"] == "network"


@_no_git
def test_bash_local_counts_file_lines():
    output = "src/foo.py\nsrc/bar.py\nDone"
    r = _compute_blast_radius("bash", {"command": "ls"}, output)
    assert r["tier"] == "local"
    assert r["files"] == 2
    assert "src/foo.py" in r["file_paths"]


@_no_git
def test_write_returns_local_with_symbols():
    r = _compute_blast_radius("write", {"content": "line1\nline2\nline3", "file_path": "src/foo.py"}, "")
    assert r["files"] == 1
    assert r["symbols"] == 3
    assert r["tier"] == "local"
    assert r["file_paths"] == ["src/foo.py"]


@_no_git
def test_read_returns_none():
    assert _compute_blast_radius("read", {}, "") is None


@_no_git
def test_grep_returns_none():
    assert _compute_blast_radius("grep", {}, "") is None


@_no_git
def test_multiedit_counts_edits():
    edits = [{"file_path": "a.py"}, {"file_path": "b.py"}, {"file_path": "c.py"}]
    r = _compute_blast_radius("multiedit", {"edits": edits}, "")
    assert r["files"] == 3
    assert r["file_paths"] == ["a.py", "b.py", "c.py"]


def test_blast_radius_includes_repo_and_branch():
    with patch("conduct_cli.hooks.posttooluse._git_context", return_value=("https://github.com/org/repo.git", "main")):
        r = _compute_blast_radius("write", {"content": "x", "file_path": "f.py"}, "")
    assert r["repo"] == "https://github.com/org/repo.git"
    assert r["branch"] == "main"


def test_blast_radius_handles_no_git():
    with patch("conduct_cli.hooks.posttooluse._git_context", return_value=(None, None)):
        r = _compute_blast_radius("write", {"content": "x"}, "")
    assert r["repo"] is None
    assert r["branch"] is None
