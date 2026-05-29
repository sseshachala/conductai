"""
Conduct Eval Harness
====================

Quality scoring system for the 18 pre-built playbooks.

Modes
-----
Structural (default, offline, ~0ms per playbook):
  Validates DSL, block topology, output contracts, fixture coverage.
  Safe to run in CI — no LLM calls, no external API calls.

Live (optional, slow, ~$0.01–$0.10 per playbook):
  Actually executes the playbook with mocked integrations.
  Scores real LLM output quality. Requires ANTHROPIC_API_KEY.

Quick start
-----------
  from eval.runner import run_all
  report = run_all()
  print(report.summary())

CLI
---
  python -m eval.runner
  python -m eval.runner --live          # enable live LLM execution
  python -m eval.runner --playbook pr_reviewer  # single playbook
"""
from eval.runner import run_all, run_one
from eval.report import EvalReport

__all__ = ["run_all", "run_one", "EvalReport"]
