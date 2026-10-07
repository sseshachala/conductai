"""Run the bundled paxel analyser.

paxel writes stats.json / report.md / profile.html next to itself, so it is
copied into a scratch dir and run there; callers read the outputs from that dir.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BUNDLED = Path(__file__).parent / "paxel.py"


def available() -> bool:
    return BUNDLED.exists()


def run_paxel(tmpdir: str | Path, timeout: int = 120) -> subprocess.CompletedProcess:
    """Copy paxel into ``tmpdir`` and run it there; outputs land in ``tmpdir``."""
    tmpdir = Path(tmpdir)
    script = tmpdir / "paxel.py"
    shutil.copy(BUNDLED, script)
    return subprocess.run(
        [sys.executable, str(script), "--no-open"],
        cwd=str(tmpdir), capture_output=True, text=True, timeout=timeout,
    )
