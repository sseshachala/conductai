"""
Unit tests for eval/online_scorer.py — no DB, no Redis, no LLM calls.

Covers:
  - anonymize_state(): PII scrubbing, repo hashing, email redaction
  - _mechanical_score(): all four criteria, edge cases
  - _grade(): correct letter for every pct band
  - _count_tokens(): sums across block outputs
  - score_run_online(): idempotency, candidate creation, no-slug skip
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

from eval.online_scorer import (
    anonymize_state,
    _mechanical_score,
    _grade,
    _count_tokens,
    _hash,
    score_run_online,
)

# Import all models so SQLAlchemy mapper relationships resolve before tests run
import app.models.environment  # noqa: F401
import app.models.workspace    # noqa: F401
import app.models.run          # noqa: F401
import app.models.run_online_score  # noqa: F401


# ── anonymize_state ───────────────────────────────────────────────────────────

class TestAnonymizeState:
    def test_email_in_string_value_is_redacted(self):
        state = {"message": "deployed by alice@example.com today"}
        result = anonymize_state(state)
        assert "[redacted]" in result["message"]
        assert "alice@example.com" not in result["message"]

    def test_email_in_nested_dict_is_redacted(self):
        state = {"commit": {"message": "fix by dev@corp.io", "id": "abc123"}}
        result = anonymize_state(state)
        assert "[redacted]" in result["commit"]["message"]
        assert result["commit"]["id"] == "abc123"

    def test_author_field_is_hashed(self):
        state = {"author": "john.doe"}
        result = anonymize_state(state)
        assert result["author"].startswith("anon-")
        assert "john.doe" not in result["author"]

    def test_author_dict_is_redacted(self):
        state = {"author": {"login": "johndoe", "id": 42}}
        result = anonymize_state(state)
        assert result["author"]["_redacted"] is True
        assert "johndoe" not in str(result["author"])

    def test_assignee_list_is_length_preserved(self):
        state = {"requested_reviewers": ["alice", "bob", "charlie"]}
        result = anonymize_state(state)
        assert result["requested_reviewers"] == ["[redacted]", "[redacted]", "[redacted]"]

    def test_repository_full_name_is_hashed(self):
        state = {"repository": {"full_name": "acme/my-repo", "number": 42}}
        result = anonymize_state(state)
        assert result["repository"]["full_name"].startswith("anon-")
        assert "acme" not in result["repository"]["full_name"]

    def test_repository_clone_url_is_hashed(self):
        state = {"repository": {"clone_url": "https://github.com/acme/repo.git"}}
        result = anonymize_state(state)
        assert result["repository"]["clone_url"].startswith("anon-")

    def test_non_pii_fields_are_preserved(self):
        state = {
            "pr_number": 142,
            "label": "bug",
            "token_count": 1500,
            "status": "succeeded",
        }
        result = anonymize_state(state)
        assert result["pr_number"] == 142
        assert result["label"] == "bug"
        assert result["token_count"] == 1500
        assert result["status"] == "succeeded"

    def test_hash_is_deterministic(self):
        assert _hash("same-input") == _hash("same-input")

    def test_different_inputs_produce_different_hashes(self):
        assert _hash("acme/repo-a") != _hash("acme/repo-b")

    def test_empty_state_returns_empty(self):
        assert anonymize_state({}) == {}

    def test_nested_pii_in_list(self):
        state = {"commits": [{"author": "jane@corp.com", "id": "abc"}]}
        result = anonymize_state(state)
        assert "jane@corp.com" not in str(result)

    def test_none_author_field(self):
        state = {"author": None}
        result = anonymize_state(state)
        assert result["author"] == "[redacted]"

    def test_empty_string_author_is_redacted(self):
        state = {"author": ""}
        result = anonymize_state(state)
        # Empty string hits the falsy branch → "[redacted]"
        assert result["author"] == "[redacted]"


# ── _mechanical_score ─────────────────────────────────────────────────────────

class TestMechanicalScore:
    def test_perfect_run_scores_40(self):
        score, max_ = _mechanical_score(
            run_status="succeeded",
            outcome={"type": "pr_opened", "artifact_url": "https://github.com/pr/1"},
            state={},
            token_count=1000,
        )
        assert score == 40
        assert max_ == 40

    def test_failed_run_loses_succeeded_points(self):
        score, _ = _mechanical_score(
            run_status="failed",
            outcome=None,
            state={},
            token_count=1000,
        )
        assert score == 5  # only token_budget passes

    def test_succeeded_no_outcome_scores_20(self):
        score, _ = _mechanical_score(
            run_status="succeeded",
            outcome={},
            state={},
            token_count=1000,
        )
        assert score == 20  # succeeded(15) + token_budget(5)

    def test_outcome_type_without_artifact_scores_correctly(self):
        score, _ = _mechanical_score(
            run_status="succeeded",
            outcome={"type": "pr_opened"},
            state={},
            token_count=1000,
        )
        assert score == 30  # succeeded(15) + outcome_detected(10) + token_budget(5)

    def test_token_budget_fails_above_50k(self):
        score, _ = _mechanical_score(
            run_status="succeeded",
            outcome={"type": "pr_opened", "artifact_url": "https://x.com"},
            state={},
            token_count=50_001,
        )
        assert score == 35  # no token_budget(5)

    def test_token_budget_passes_at_exactly_49999(self):
        score, _ = _mechanical_score(
            run_status="succeeded",
            outcome={"type": "pr_opened", "artifact_url": "https://x.com"},
            state={},
            token_count=49_999,
        )
        assert score == 40

    def test_none_outcome_scores_no_outcome_points(self):
        score, _ = _mechanical_score(
            run_status="succeeded",
            outcome=None,
            state={},
            token_count=100,
        )
        assert score == 20  # succeeded(15) + token_budget(5), no outcome points

    def test_max_is_always_40(self):
        _, max_ = _mechanical_score("failed", None, {}, 999_999)
        assert max_ == 40


# ── _grade ────────────────────────────────────────────────────────────────────

class TestGrade:
    @pytest.mark.parametrize("pct,expected", [
        (100.0, "A"),
        (90.0,  "A"),
        (89.9,  "B"),
        (75.0,  "B"),
        (74.9,  "C"),
        (60.0,  "C"),
        (59.9,  "D"),
        (40.0,  "D"),
        (39.9,  "F"),
        (0.0,   "F"),
    ])
    def test_grade_boundaries(self, pct, expected):
        assert _grade(pct) == expected


# ── _count_tokens ─────────────────────────────────────────────────────────────

class TestCountTokens:
    def test_sums_input_and_output_tokens(self):
        state = {
            "brain_1": {"input_tokens": 500, "output_tokens": 200},
            "brain_2": {"input_tokens": 300, "output_tokens": 100},
        }
        assert _count_tokens(state) == 1100

    def test_total_tokens_field_also_counted(self):
        state = {"brain_1": {"total_tokens": 800}}
        assert _count_tokens(state) == 800

    def test_non_dict_values_skipped(self):
        state = {"status": "succeeded", "brain_1": {"input_tokens": 100, "output_tokens": 50}}
        assert _count_tokens(state) == 150

    def test_empty_state_returns_zero(self):
        assert _count_tokens({}) == 0

    def test_missing_token_fields_treated_as_zero(self):
        state = {"brain_1": {"grade": "A"}}
        assert _count_tokens(state) == 0


# ── score_run_online ──────────────────────────────────────────────────────────

class TestScoreRunOnline:
    def _make_db(self, run=None, existing_score=None):
        """Build a mock DB session with configurable query returns."""
        db = MagicMock()
        query = db.query.return_value
        filter_by = query.filter_by.return_value

        # First call: check for existing score (idempotency)
        # Second call: fetch the run
        filter_by.first.side_effect = [existing_score, None]  # no candidate yet
        db.query.return_value.filter_by.return_value.first.side_effect = [
            existing_score,  # RunOnlineScore idempotency check
            run,             # Run lookup
            None,            # RunFixtureCandidate idempotency check
        ]
        return db

    def _make_run(self, status="succeeded", outcome=None, state=None, wv_id=None):
        run = MagicMock()
        run.id = uuid.uuid4()
        run.workflow_version_id = wv_id or uuid.uuid4()
        run.status = status
        run.outcome = outcome or {"type": "pr_opened", "artifact_url": "https://github.com/pr/1"}
        run.state = state or {"brain_1": {"input_tokens": 100, "output_tokens": 50}}
        return run

    def test_skips_if_already_scored(self):
        db = MagicMock()
        existing = MagicMock()
        db.query.return_value.filter_by.return_value.first.return_value = existing

        score_run_online("run-id", db, judge=False)

        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_skips_if_run_not_found(self):
        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.side_effect = [None, None]

        with patch("eval.online_scorer._resolve_slug", return_value="pr_reviewer"):
            score_run_online(str(uuid.uuid4()), db, judge=False)

        db.commit.assert_not_called()

    def test_skips_if_no_slug(self):
        run = self._make_run()
        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.side_effect = [None, run]

        with patch("eval.online_scorer._resolve_slug", return_value=None), \
             patch("eval.online_scorer._resolve_workflow_id", return_value=None):
            score_run_online(str(run.id), db, judge=False)

        db.commit.assert_not_called()

    def test_successful_run_writes_score_row(self):
        run = self._make_run(status="succeeded")
        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.side_effect = [
            None, run, None
        ]

        with patch("eval.online_scorer._resolve_slug", return_value="pr_reviewer"), \
             patch("eval.online_scorer._resolve_workflow_id", return_value=str(uuid.uuid4())):
            score_run_online(str(run.id), db, judge=False)

        db.add.assert_called()
        db.commit.assert_called_once()

        added = db.add.call_args_list[0][0][0]
        assert added.slug == "pr_reviewer"
        assert added.grade in ("A", "B", "C", "D", "F")
        assert added.judge_used is False

    def test_low_scoring_run_creates_candidate(self):
        """A failed run with no outcome scores low → creates fixture candidate."""
        run = self._make_run(status="failed", outcome={}, state={})
        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.side_effect = [
            None, run, None
        ]

        with patch("eval.online_scorer._resolve_slug", return_value="pr_reviewer"), \
             patch("eval.online_scorer._resolve_workflow_id", return_value=str(uuid.uuid4())):
            score_run_online(str(run.id), db, judge=False)

        # Two rows added: RunOnlineScore + RunFixtureCandidate
        assert db.add.call_count == 2
        candidate = db.add.call_args_list[1][0][0]
        assert candidate.status == "pending"
        assert candidate.slug == "pr_reviewer"

    def test_grade_a_run_does_not_create_candidate(self):
        """A perfect run should not produce a fixture candidate."""
        run = self._make_run(
            status="succeeded",
            outcome={"type": "pr_opened", "artifact_url": "https://github.com/pr/1"},
            state={"brain_1": {"input_tokens": 100, "output_tokens": 50}},
        )
        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.side_effect = [
            None, run, None
        ]

        with patch("eval.online_scorer._resolve_slug", return_value="pr_reviewer"), \
             patch("eval.online_scorer._resolve_workflow_id", return_value=str(uuid.uuid4())):
            score_run_online(str(run.id), db, judge=False)

        # Only one row added: RunOnlineScore — no candidate for grade A/B
        assert db.add.call_count == 1

    def test_judge_flag_is_recorded(self):
        run = self._make_run(status="succeeded")
        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.side_effect = [
            None, run, None
        ]

        mock_judge_result = MagicMock()
        mock_judge_result.failed = False
        mock_judge_result.to_criteria.return_value = [
            MagicMock(points_earned=8),
            MagicMock(points_earned=7),
            MagicMock(points_earned=9),
        ]

        with patch("eval.online_scorer._resolve_slug", return_value="pr_reviewer"), \
             patch("eval.online_scorer._resolve_workflow_id", return_value=str(uuid.uuid4())), \
             patch("eval.online_scorer.judge_output", return_value=mock_judge_result, create=True), \
             patch("eval.online_scorer.extract_brain_output", return_value="some brain text", create=True):

            from eval import judge as _judge_mod
            with patch.dict("sys.modules", {"eval.judge": MagicMock(
                judge_output=lambda *a, **kw: mock_judge_result,
                extract_brain_output=lambda s: "brain text",
            )}):
                score_run_online(str(run.id), db, judge=True)

        added = db.add.call_args_list[0][0][0]
        assert added.judge_used is True

    def test_judge_failure_falls_back_to_mechanical_only(self):
        """If judge raises, scoring continues with mechanical only."""
        run = self._make_run(status="succeeded")
        db = MagicMock()
        db.query.return_value.filter_by.return_value.first.side_effect = [
            None, run, None
        ]

        with patch("eval.online_scorer._resolve_slug", return_value="pr_reviewer"), \
             patch("eval.online_scorer._resolve_workflow_id", return_value=str(uuid.uuid4())), \
             patch.dict("sys.modules", {"eval.judge": MagicMock(
                 judge_output=MagicMock(side_effect=RuntimeError("API down")),
                 extract_brain_output=MagicMock(return_value="brain text"),
             )}):
                score_run_online(str(run.id), db, judge=True)

        db.commit.assert_called_once()
        added = db.add.call_args_list[0][0][0]
        assert added.judge_used is False
        assert added.judge_score == 0
