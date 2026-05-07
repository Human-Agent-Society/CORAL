"""Tests for core types."""

from coral.types import (
    BUDGET_CLASS_GRADER_ERROR,
    BUDGET_CLASS_REAL,
    BUDGET_CLASS_TUNE,
    Attempt,
    Score,
    ScoreBundle,
    Task,
    get_budget_class,
)


def test_task_roundtrip():
    task = Task(id="t1", name="Test", description="A test task", metadata={"key": "val"})
    data = task.to_dict()
    restored = Task.from_dict(data)
    assert restored.id == "t1"
    assert restored.name == "Test"
    assert restored.metadata == {"key": "val"}


def test_score_bundle_aggregation():
    bundle = ScoreBundle(
        scores={
            "a": Score(value=0.8, name="a"),
            "b": Score(value=0.6, name="b"),
        }
    )
    agg = bundle.compute_aggregated()
    assert abs(agg - 0.7) < 1e-6


def test_attempt_roundtrip():
    attempt = Attempt(
        commit_hash="abc123",
        agent_id="agent-1",
        title="Test approach",
        score=0.85,
        status="improved",
        parent_hash="def456",
        timestamp="2026-03-11T10:00:00Z",
        feedback="Good improvement",
    )
    data = attempt.to_dict()
    restored = Attempt.from_dict(data)
    assert restored.commit_hash == "abc123"
    assert restored.score == 0.85
    assert restored.feedback == "Good improvement"
    assert restored.shared_state_hash is None
    assert restored.parent_shared_state_hash is None
    assert "shared_state_hash" not in data  # omitted when None
    assert "parent_shared_state_hash" not in data


def test_attempt_shared_state_hash_roundtrip():
    parent_ssh = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    attempt = Attempt(
        commit_hash="abc123",
        agent_id="agent-1",
        title="Test",
        score=0.5,
        status="improved",
        parent_hash=None,
        timestamp="2026-03-11T10:00:00Z",
        shared_state_hash="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        parent_shared_state_hash=parent_ssh,
    )
    data = attempt.to_dict()
    assert data["shared_state_hash"] == "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    assert data["parent_shared_state_hash"] == parent_ssh
    restored = Attempt.from_dict(data)
    assert restored.shared_state_hash == "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    assert restored.parent_shared_state_hash == parent_ssh


def test_attempt_from_dict_without_shared_state_hash():
    """Backward compat: JSON without shared state fields loads as None."""
    data = {
        "commit_hash": "abc123",
        "agent_id": "agent-1",
        "title": "Old attempt",
        "score": 0.5,
        "status": "improved",
        "parent_hash": None,
        "timestamp": "2026-03-11T10:00:00Z",
    }
    attempt = Attempt.from_dict(data)
    assert attempt.shared_state_hash is None
    assert attempt.parent_shared_state_hash is None


# --------------------------------------------------------------------------- #
# Budget class (issue #73)                                                    #
# --------------------------------------------------------------------------- #


def test_get_budget_class_default_real():
    """Empty / missing metadata defaults to 'real' for backward compat."""
    assert get_budget_class(None) == BUDGET_CLASS_REAL
    assert get_budget_class({}) == BUDGET_CLASS_REAL
    assert get_budget_class({"other_key": "x"}) == BUDGET_CLASS_REAL


def test_get_budget_class_recognizes_known_values():
    assert get_budget_class({"budget_class": "real"}) == BUDGET_CLASS_REAL
    assert get_budget_class({"budget_class": "grader_error"}) == BUDGET_CLASS_GRADER_ERROR
    assert get_budget_class({"budget_class": "tune"}) == BUDGET_CLASS_TUNE


def test_get_budget_class_rejects_unknown():
    """Unknown values fall back to 'real' rather than corrupting accounting."""
    assert get_budget_class({"budget_class": "garbage"}) == BUDGET_CLASS_REAL


def test_attempt_budget_class_property():
    """Attempt.budget_class reads from metadata with default 'real'."""
    a = Attempt(
        commit_hash="abc",
        agent_id="a-1",
        title="t",
        score=0.5,
        status="improved",
        parent_hash=None,
        timestamp="2026-03-11T10:00:00Z",
    )
    assert a.budget_class == BUDGET_CLASS_REAL

    a.metadata["budget_class"] = "tune"
    assert a.budget_class == BUDGET_CLASS_TUNE

    a.metadata["budget_class"] = "grader_error"
    assert a.budget_class == BUDGET_CLASS_GRADER_ERROR


def test_attempt_legacy_json_loads_as_real():
    """Pre-issue-73 JSON without budget_class metadata reads as 'real'."""
    data = {
        "commit_hash": "abc",
        "agent_id": "a-1",
        "title": "old",
        "score": 0.5,
        "status": "improved",
        "parent_hash": None,
        "timestamp": "2026-03-11T10:00:00Z",
    }
    a = Attempt.from_dict(data)
    assert a.budget_class == BUDGET_CLASS_REAL
