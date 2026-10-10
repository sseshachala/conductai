"""Search-quality eval: recall@5, recall@10, MRR over eval/queries.jsonl.

    python eval/run_eval.py --root <repo-checkout> [--index]

--index builds the symbol index + embeddings first (slow on a big repo).
Uses whichever `booster` package is importable, so the same script scores
old and new code (point PYTHONPATH at the version under test).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from booster.indexer import SymbolIndexer

QUERIES = Path(__file__).with_name("queries.jsonl")


def _rank(results: list[dict], want: dict) -> int | None:
    for i, r in enumerate(results, start=1):
        if r["file"] == want["file"] and r["name"] == want["name"]:
            return i
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--index", action="store_true")
    args = ap.parse_args()

    ix = SymbolIndexer(args.root.resolve())
    if args.index:
        ix.index_all(embed=True, force=True)

    queries = [json.loads(line) for line in QUERIES.read_text().splitlines() if line.strip()]
    methods = {"keyword": ix.search, "vector": ix.vector_search, "rrf": ix.rrf_search}
    print(f"{'method':8} {'R@5':>6} {'R@10':>6} {'MRR':>6}")
    for label, fn in methods.items():
        ranks = [_rank(fn(q["q"], limit=10), q) for q in queries]
        r5 = sum(1 for r in ranks if r and r <= 5) / len(ranks)
        r10 = sum(1 for r in ranks if r) / len(ranks)
        mrr = sum(1 / r for r in ranks if r) / len(ranks)
        print(f"{label:8} {r5:6.2f} {r10:6.2f} {mrr:6.2f}")
        missed = [q["name"] for q, r in zip(queries, ranks) if not r]
        if missed:
            print(f"  missed@10: {', '.join(missed)}")


if __name__ == "__main__":
    main()
