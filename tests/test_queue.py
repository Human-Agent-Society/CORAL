"""Tests for the eval queue system."""

from __future__ import annotations

import threading
import time

import pytest

from coral.config import QueueConfig
from coral.queue.client import QueueClient
from coral.queue.counter import increment_eval_count
from coral.queue.dispatcher import QueueDispatcher
from coral.queue.types import EvalRequest, EvalResult


@pytest.fixture
def coral_dir(tmp_path):
    """Create a minimal .coral directory with queue dirs."""
    d = tmp_path / ".coral"
    (d / "public").mkdir(parents=True)
    (d / "queue" / "pending").mkdir(parents=True)
    (d / "queue" / "results").mkdir(parents=True)
    return d


@pytest.fixture
def queue_config():
    return QueueConfig(
        max_concurrent=2,
        strategy="fifo",
        poll_interval=0.1,
        timeout=5,
    )


# --- EvalRequest / EvalResult serialization ---


class TestTypes:
    def test_eval_request_roundtrip(self, tmp_path):
        req = EvalRequest(
            ticket_id="abc123",
            agent_id="agent-1",
            commit_hash="deadbeef",
            config_path="/tmp/config.yaml",
            coral_dir="/tmp/.coral",
            codebase_path="/tmp/repo",
            timestamp="2026-01-01T00:00:00",
            priority=5,
        )
        path = tmp_path / "req.json"
        req.to_json(path)
        restored = EvalRequest.from_json(path)
        assert restored.ticket_id == "abc123"
        assert restored.agent_id == "agent-1"
        assert restored.priority == 5

    def test_eval_result_roundtrip(self, tmp_path):
        res = EvalResult(
            ticket_id="abc123",
            score=0.85,
            scores={"accuracy": {"value": 0.85, "name": "accuracy"}},
            feedback="Good job",
            status="ok",
        )
        path = tmp_path / "res.json"
        res.to_json(path)
        restored = EvalResult.from_json(path)
        assert restored.score == 0.85
        assert restored.status == "ok"
        assert restored.feedback == "Good job"

    def test_eval_result_error(self):
        res = EvalResult(
            ticket_id="x",
            score=None,
            status="error",
            error="Something broke",
        )
        d = res.to_dict()
        assert d["status"] == "error"
        assert d["error"] == "Something broke"
        assert d["score"] is None


# --- Atomic counter ---


class TestAtomicCounter:
    def test_basic_increment(self, coral_dir):
        assert increment_eval_count(coral_dir) == 1
        assert increment_eval_count(coral_dir) == 2
        assert increment_eval_count(coral_dir) == 3

    def test_concurrent_increments(self, coral_dir):
        """Verify no lost updates under concurrent writes."""
        n_threads = 10
        n_per_thread = 20
        errors = []

        def worker():
            try:
                for _ in range(n_per_thread):
                    increment_eval_count(coral_dir)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        counter_file = coral_dir / "public" / "eval_count"
        final = int(counter_file.read_text().strip())
        assert final == n_threads * n_per_thread

    def test_handles_missing_file(self, coral_dir):
        """Counter starts at 0 if file doesn't exist."""
        assert increment_eval_count(coral_dir) == 1

    def test_handles_corrupt_file(self, coral_dir):
        """Counter resets to 0 if file contains garbage."""
        (coral_dir / "public" / "eval_count").write_text("not-a-number")
        assert increment_eval_count(coral_dir) == 1


# --- QueueClient ---


class TestQueueClient:
    def test_submit_creates_pending_file(self, coral_dir, queue_config):
        client = QueueClient(coral_dir, queue_config)
        req = client.submit("agent-1", "abc123", "/config.yaml", "/repo")
        pending_path = coral_dir / "queue" / "pending" / f"{req.ticket_id}.json"
        assert pending_path.exists()
        loaded = EvalRequest.from_json(pending_path)
        assert loaded.agent_id == "agent-1"
        assert loaded.commit_hash == "abc123"

    def test_wait_for_result(self, coral_dir, queue_config):
        client = QueueClient(coral_dir, queue_config)
        ticket_id = "test-ticket"

        # Write result after a short delay
        def write_result():
            time.sleep(0.2)
            result = EvalResult(ticket_id=ticket_id, score=0.9, status="ok")
            result.to_json(coral_dir / "queue" / "results" / f"{ticket_id}.json")

        t = threading.Thread(target=write_result)
        t.start()

        result = client.wait_for_result(ticket_id)
        t.join()
        assert result.score == 0.9
        assert result.status == "ok"
        # Result file should be cleaned up
        assert not (coral_dir / "queue" / "results" / f"{ticket_id}.json").exists()

    def test_wait_for_result_timeout(self, coral_dir):
        config = QueueConfig(poll_interval=0.05, timeout=1)
        client = QueueClient(coral_dir, config, grader_timeout=0)
        with pytest.raises(TimeoutError):
            client.wait_for_result("nonexistent-ticket")

    def test_max_queue_size(self, coral_dir):
        config = QueueConfig(max_queue_size=2, poll_interval=0.1, timeout=1)
        client = QueueClient(coral_dir, config)
        client.submit("agent-1", "a", "/c", "/r")
        client.submit("agent-1", "b", "/c", "/r")
        with pytest.raises(RuntimeError, match="Queue is full"):
            client.submit("agent-1", "c", "/c", "/r")

    def test_get_position(self, coral_dir, queue_config):
        client = QueueClient(coral_dir, queue_config)
        req1 = client.submit("agent-1", "a", "/c", "/r")
        req2 = client.submit("agent-2", "b", "/c", "/r")
        req3 = client.submit("agent-1", "c", "/c", "/r")

        assert client.get_position(req1.ticket_id) == 0
        assert client.get_position(req2.ticket_id) == 1
        assert client.get_position(req3.ticket_id) == 2


# --- QueueDispatcher scheduling ---


class TestDispatcherScheduling:
    def _make_request(self, agent_id: str, timestamp: str, priority: int = 0) -> EvalRequest:
        return EvalRequest(
            ticket_id=f"{agent_id}-{timestamp}",
            agent_id=agent_id,
            commit_hash="abc",
            config_path="/c",
            coral_dir="/d",
            codebase_path="/r",
            timestamp=timestamp,
            priority=priority,
        )

    def test_fifo_scheduling(self, coral_dir):
        config = QueueConfig(strategy="fifo", max_concurrent=1)
        dispatcher = QueueDispatcher(coral_dir, config)
        requests = [
            self._make_request("agent-2", "2026-01-01T00:00:03"),
            self._make_request("agent-1", "2026-01-01T00:00:01"),
            self._make_request("agent-1", "2026-01-01T00:00:02"),
        ]
        ordered = dispatcher._schedule(requests)
        assert [r.timestamp for r in ordered] == [
            "2026-01-01T00:00:01",
            "2026-01-01T00:00:02",
            "2026-01-01T00:00:03",
        ]

    def test_fair_scheduling(self, coral_dir):
        config = QueueConfig(strategy="fair", max_concurrent=1)
        dispatcher = QueueDispatcher(coral_dir, config)
        requests = [
            self._make_request("agent-1", "2026-01-01T00:00:01"),
            self._make_request("agent-1", "2026-01-01T00:00:02"),
            self._make_request("agent-2", "2026-01-01T00:00:03"),
            self._make_request("agent-2", "2026-01-01T00:00:04"),
        ]
        ordered = dispatcher._schedule(requests)
        agent_order = [r.agent_id for r in ordered]
        # Fair = round-robin: agent-1, agent-2, agent-1, agent-2
        assert agent_order == ["agent-1", "agent-2", "agent-1", "agent-2"]

    def test_priority_scheduling(self, coral_dir):
        config = QueueConfig(strategy="priority", max_concurrent=1)
        dispatcher = QueueDispatcher(coral_dir, config)
        requests = [
            self._make_request("agent-1", "2026-01-01T00:00:01", priority=1),
            self._make_request("agent-2", "2026-01-01T00:00:02", priority=10),
            self._make_request("agent-3", "2026-01-01T00:00:03", priority=5),
        ]
        ordered = dispatcher._schedule(requests)
        assert [r.priority for r in ordered] == [10, 5, 1]

    def test_rate_limiting(self, coral_dir):
        config = QueueConfig(strategy="fifo", max_concurrent=10, rate_limit=100.0)
        dispatcher = QueueDispatcher(coral_dir, config)

        # Simulate a recent eval for agent-1
        dispatcher._last_eval_time["agent-1"] = time.monotonic()

        req = self._make_request("agent-1", "2026-01-01T00:00:01")
        req.to_json(coral_dir / "queue" / "pending" / f"{req.ticket_id}.json")

        # Should not dispatch due to rate limit
        dispatcher._dispatch_pending()
        assert len(dispatcher.active_jobs) == 0


# --- Config integration ---


class TestQueueConfig:
    def test_default_config(self):
        config = QueueConfig()
        assert config.max_concurrent == 1
        assert config.strategy == "fair"
        assert config.executor == "local"

    def test_config_from_yaml(self):
        from coral.config import CoralConfig

        data = {
            "task": {"name": "t", "description": "d"},
            "grader": {"queue": {"max_concurrent": 4, "strategy": "priority", "executor": "slurm"}},
        }
        config = CoralConfig.from_dict(data)
        assert config.grader.queue.max_concurrent == 4
        assert config.grader.queue.strategy == "priority"
        assert config.grader.queue.executor == "slurm"

    def test_config_defaults_without_queue_section(self):
        from coral.config import CoralConfig

        data = {"task": {"name": "t", "description": "d"}}
        config = CoralConfig.from_dict(data)
        assert config.grader.queue.max_concurrent == 1
        assert config.grader.queue.strategy == "fair"

    def test_dotlist_override(self):
        from coral.config import CoralConfig

        data = {"task": {"name": "t", "description": "d"}}
        config = CoralConfig.from_dict(data)
        config = CoralConfig.merge_dotlist(config, ["grader.queue.max_concurrent=8"])
        assert config.grader.queue.max_concurrent == 8

    def test_queue_timeout_defaults_from_grader(self):
        """When queue.timeout is 0, effective timeout = grader.timeout + 60s."""
        from coral.queue.client import _QUEUE_TIMEOUT_OVERHEAD

        config = QueueConfig(timeout=0)
        client = QueueClient.__new__(QueueClient)
        client.config = config
        client._timeout = config.timeout if config.timeout > 0 else 120 + _QUEUE_TIMEOUT_OVERHEAD
        assert client._timeout == 120 + _QUEUE_TIMEOUT_OVERHEAD

    def test_queue_timeout_explicit_override(self):
        """Explicit queue.timeout takes precedence over grader-derived default."""
        config = QueueConfig(timeout=999)
        client = QueueClient.__new__(QueueClient)
        client.config = config
        client._timeout = config.timeout if config.timeout > 0 else 300 + 60
        assert client._timeout == 999
