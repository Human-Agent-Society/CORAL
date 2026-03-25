"""Tests for core types."""

from coral.types import Attempt, Score, ScoreBundle, Task


def test_task_roundtrip():
    task = Task(id="t1", name="Test", description="A test task", metadata={"key": "val"})
    data = task.to_dict()
    restored = Task.from_dict(data)
    assert restored.id == "t1"
    assert restored.name == "Test"
    assert restored.metadata == {"key": "val"}


def test_score_to_float():
    assert Score(value=True, name="s").to_float() == 1.0
    assert Score(value=False, name="s").to_float() == 0.0
    assert Score(value=0.75, name="s").to_float() == 0.75
    assert Score(value="CORRECT", name="s").to_float() == 1.0
    assert Score(value="PARTIAL", name="s").to_float() == 0.5


def test_score_bundle_aggregation():
    bundle = ScoreBundle(scores={
        "a": Score(value=0.8, name="a"),
        "b": Score(value=0.6, name="b"),
    })
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
