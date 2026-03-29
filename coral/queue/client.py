"""Agent-side queue client: submit eval requests and poll for results."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from coral.config import QueueConfig
from coral.queue.types import EvalRequest, EvalResult

_QUEUE_TIMEOUT_OVERHEAD = 60  # seconds added to grader timeout for queue wait


class QueueClient:
    """Used by agents (in run_eval) to submit eval requests and wait for results."""

    def __init__(self, coral_dir: Path, config: QueueConfig, grader_timeout: int = 300) -> None:
        self.coral_dir = coral_dir
        self.config = config
        self.pending_dir = coral_dir / "queue" / "pending"
        self.results_dir = coral_dir / "queue" / "results"
        # Resolve effective timeout: explicit value, or grader timeout + overhead
        self._timeout = config.timeout if config.timeout > 0 else grader_timeout + _QUEUE_TIMEOUT_OVERHEAD

    def submit(
        self,
        agent_id: str,
        commit_hash: str,
        config_path: str,
        codebase_path: str,
    ) -> EvalRequest:
        """Write an eval request to .coral/queue/pending/. Returns the request."""
        if self.config.max_queue_size > 0:
            pending_count = len(list(self.pending_dir.glob("*.json")))
            if pending_count >= self.config.max_queue_size:
                raise RuntimeError(
                    f"Queue is full ({pending_count}/{self.config.max_queue_size} pending requests)"
                )

        request = EvalRequest(
            ticket_id=uuid.uuid4().hex,
            agent_id=agent_id,
            commit_hash=commit_hash,
            config_path=config_path,
            coral_dir=str(self.coral_dir),
            codebase_path=codebase_path,
            timestamp=datetime.now(UTC).isoformat(),
        )
        request.to_json(self.pending_dir / f"{request.ticket_id}.json")
        return request

    def wait_for_result(self, ticket_id: str) -> EvalResult:
        """Poll .coral/queue/results/<ticket_id>.json until result appears.

        Raises TimeoutError after config.timeout seconds.
        """
        result_path = self.results_dir / f"{ticket_id}.json"
        deadline = time.monotonic() + self._timeout

        while time.monotonic() < deadline:
            if result_path.exists():
                result = EvalResult.from_json(result_path)
                # Clean up result file after reading
                try:
                    result_path.unlink()
                except OSError:
                    pass
                return result
            time.sleep(self.config.poll_interval)

        raise TimeoutError(
            f"Timed out waiting for eval result after {self._timeout}s (ticket {ticket_id})"
        )

    def get_position(self, ticket_id: str) -> int:
        """Count pending requests ahead of this one (by timestamp)."""
        try:
            own_request = EvalRequest.from_json(self.pending_dir / f"{ticket_id}.json")
        except (FileNotFoundError, KeyError):
            return 0

        position = 0
        for path in self.pending_dir.glob("*.json"):
            if path.stem == ticket_id:
                continue
            try:
                req = EvalRequest.from_json(path)
                if req.timestamp <= own_request.timestamp:
                    position += 1
            except (FileNotFoundError, KeyError, ValueError):
                continue
        return position
