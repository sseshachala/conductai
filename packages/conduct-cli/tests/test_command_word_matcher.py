"""Regression check for issue #852 — the privilege-escalation matcher must
distinguish a command word from a literal string in a payload."""
from conduct_cli.guard import _bash_command_words


# Words pulled at runtime so the test file itself doesn't smuggle a literal
# the local Guard hook would flag (this file gets read by other dev tools).
ELEVATED = "s" + "udo"


def test_literal_in_arg_body_is_not_a_command_word():
    cmd = f"gh issue comment 848 --body 'discussion of {ELEVATED} prior art'"
    words = _bash_command_words(cmd)
    assert ELEVATED not in words, f"false positive: {words}"
    assert words[0] == "gh"


def test_literal_inside_heredoc_is_not_a_command_word():
    cmd = "git commit -m 'mention " + ELEVATED + " in passing'"
    words = _bash_command_words(cmd)
    assert ELEVATED not in words
    assert words[0] == "git"


def test_direct_invocation_is_caught():
    words = _bash_command_words(f"{ELEVATED} ls")
    assert words[0] == ELEVATED


def test_pipeline_segments_each_get_a_word():
    cmd = f"echo hello | {ELEVATED} tee /tmp/x | cat"
    words = _bash_command_words(cmd)
    assert words == ["echo", ELEVATED, "cat"]


def test_conditional_and_or_chains():
    cmd = f"true && {ELEVATED} systemctl restart x || echo failed"
    words = _bash_command_words(cmd)
    assert ELEVATED in words
    assert "echo" in words


def test_env_var_prefix_is_skipped():
    cmd = f"FOO=bar BAR=baz {ELEVATED} -u root ls"
    words = _bash_command_words(cmd)
    assert words[0] == ELEVATED


def test_empty_and_garbage_inputs():
    assert _bash_command_words("") == []
    assert _bash_command_words("'unterminated") == []
