"""Guard engine — policy evaluation, audit sink, provider router.

Three-module decomposition per #1218:
- policy.py    — evaluate(request) → Decision (rules + budgets)
- audit.py     — wrap(stream, decision, workspace_id) → Stream (hash chain)
- router.py    — upstream(request) → Stream (provider fanout)

Each module owns a single responsibility. HTTP proxy handler and Lens
in-process caller both compose the same three modules via gateway.py.
"""
