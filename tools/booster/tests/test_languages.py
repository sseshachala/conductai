"""One test per language: symbols extracted, same-file call edge resolves."""
from __future__ import annotations

from pathlib import Path

import pytest

from booster.indexer import SymbolIndexer
from booster.langs import MAX_FILE_BYTES, is_gated, iter_source_files
from booster.parsing import _is_test_file

# (file, source, expected {name: kind}, (caller, callee) edge)
CASES = {
    "go": ("svc/pay.go", """package svc

// Charge bills the card, retrying on rate limits.
func Charge(amount int) error { return retryCall(amount) }

func retryCall(n int) error { return nil }

type Ledger struct{}

func (l *Ledger) Post(x int) { Charge(x) }
""", {"Charge": "function", "retryCall": "function", "Ledger": "type", "Post": "method"},
        ("Post", "Charge")),
    "rust": ("src/pay.rs", """/// Charge bills the card.
fn charge(amount: i32) -> i32 { retry_call(amount) }
fn retry_call(n: i32) -> i32 { n }
struct Ledger;
trait Postable { fn post(&self); }
impl Ledger {
    fn post(&self) {
        self.helper();
        charge(1);
    }
    fn helper(&self) {}
}
enum State { Open }
""", {"charge": "function", "retry_call": "function", "Ledger": "struct",
      "Postable": "trait", "State": "enum"}, ("post", "charge")),
    "java": ("src/Pay.java", """public class Pay {
    public Pay() {}
    /** Charge bills the card. */
    int charge(int amount) { return retryCall(amount); }
    int retryCall(int n) { return n; }
}
interface Postable { void post(); }
""", {"Pay": "method", "charge": "method", "retryCall": "method", "Postable": "interface"},
        ("charge", "retryCall")),
    "c": ("src/pay.c", """struct ledger { int total; };
/* charge bills the card */
int charge(int amount) { return retry_call(amount); }
static int *retry_call(int n) { return 0; }
struct ledger *make(void);
""", {"ledger": "struct", "charge": "function", "retry_call": "function"}, ("charge", "retry_call")),
    "cpp": ("src/pay.cpp", """namespace billing {
class Ledger { public: void post(); };
int charge(int amount) { return retry_call(amount); }
}
void billing::Ledger::post() { charge(1); }
""", {"billing": "namespace", "Ledger": "class", "charge": "function", "post": "function"},
        ("post", "charge")),
    "bash": ("scripts/deploy.sh", """#!/usr/bin/env bash
# deploy pushes the release
deploy() {
  build_image "$1"
}
function build_image {
  docker build .
}
""", {"deploy": "function", "build_image": "function"}, ("deploy", "build_image")),
}


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


@pytest.mark.parametrize("lang", sorted(CASES))
def test_language_symbols_and_calls(tmp_path, lang):
    rel, src, want, (caller, callee) = CASES[lang]
    _write(tmp_path, rel, src)
    ix = SymbolIndexer(tmp_path)
    ix.index_all()
    got = {(s["name"], s["kind"]) for s in ix.get_symbols(rel)}
    assert set(want.items()) <= got, (lang, got)
    edges = ix.expand_calls(caller, direction="callees", file=rel)
    assert any(e["to_name"] == callee and e["to_id"] for e in edges), (lang, edges)


def test_language_doc_feeds_search(tmp_path):
    rel, src, *_ = CASES["go"]
    _write(tmp_path, rel, src)
    ix = SymbolIndexer(tmp_path)
    ix.index_all()
    # "bills" / "rate limits" only appear in the leading // comment.
    assert ix.search("bills card rate limits")[0]["name"] == "Charge"


def test_yaml_playbook_blocks(tmp_path):
    rel = "apps/api/playbooks/fix.yaml"
    _write(tmp_path, rel, """name: autopilot-fix
inputs:
  model:
    default: haiku
on:
  webhook:
    next: recall_context
blocks:
  recall_context:
    type: memory
    next: plan_fix
  plan_fix:
    type: brain
    mode: single
    max_turns: 1
steps:
  - name: checkout
    uses: actions/checkout
""")
    ix = SymbolIndexer(tmp_path)
    ix.index_all()
    got = {(s["name"], s["kind"]) for s in ix.get_symbols(rel)}
    assert {("name", "key"), ("blocks", "key"), ("inputs.model", "block"),
            ("blocks.recall_context", "block"), ("blocks.plan_fix", "block"),
            ("checkout", "item")} <= got
    names = {n for n, _ in got}
    assert "type" not in names and "blocks.plan_fix.mode" not in names  # no leaf keys
    plan = next(s for s in ix.get_symbols(rel) if s["name"] == "blocks.plan_fix")
    assert (plan["start_line"], plan["end_line"]) == (12, 15)
    assert ix.search("plan fix brain block")[0]["name"] == "blocks.plan_fix"


def test_yaml_deep_lists_not_indexed(tmp_path):
    _write(tmp_path, "k8s.yaml", """spec:
  template:
    spec:
      containers:
        - name: api
          env:
            - name: DATABASE_URL
""")
    ix = SymbolIndexer(tmp_path)
    ix.index_all()
    names = {s["name"] for s in ix.get_symbols("k8s.yaml")}
    assert "DATABASE_URL" not in names


def test_gate_skips_config_files():
    assert is_gated("a/b.go") and is_gated("x.rs") and is_gated("run.sh")
    assert not is_gated("playbook.yaml") and not is_gated("ci.yml")
    assert not is_gated("README.md")


def test_iter_source_files_prunes_and_caps(tmp_path):
    _write(tmp_path, "src/main.go", "package main\n")
    _write(tmp_path, "target/debug/gen.rs", "fn x() {}\n")
    _write(tmp_path, "vendor/lib/dep.go", "package dep\n")
    _write(tmp_path, "notes.md", "# hi\n")
    _write(tmp_path, "big.yaml", "k: " + "x" * (MAX_FILE_BYTES + 1) + "\n")
    got = sorted(str(p.relative_to(tmp_path)) for p in iter_source_files(tmp_path))
    assert got == ["src/main.go"]


@pytest.mark.parametrize("rel,want", [
    ("pkg/pay_test.go", True), ("src/PayTest.java", True), ("src/pay.go", False),
    ("src/Pay.java", False), ("tests/integration.rs", True),
])
def test_is_test_file_new_languages(rel, want):
    assert _is_test_file(rel) is want
