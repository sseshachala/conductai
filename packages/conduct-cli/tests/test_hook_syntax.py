"""Validate that all hook template files are syntactically valid Python.

This test exists to catch the class of bug where escape sequences in embedded
string literals break generated hook files. Since templates are now real .py
files, py_compile catches any issue immediately.
"""
import py_compile
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "conduct_cli"

def test_hook_template_syntax():
    py_compile.compile(str(TEMPLATES_DIR / "hook_template.py"), doraise=True)

def test_precompact_template_syntax():
    py_compile.compile(str(TEMPLATES_DIR / "hook_precompact_template.py"), doraise=True)

def test_session_start_template_syntax():
    py_compile.compile(str(TEMPLATES_DIR / "hook_session_start_template.py"), doraise=True)
