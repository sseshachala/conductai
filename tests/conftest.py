"""Ensure local src/ takes precedence over any installed conduct_cli package."""
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# Force-reload conduct_cli.guard from local src if installed version was cached
import importlib
for mod in list(sys.modules):
    if mod.startswith("conduct_cli"):
        del sys.modules[mod]
