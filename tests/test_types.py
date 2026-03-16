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
