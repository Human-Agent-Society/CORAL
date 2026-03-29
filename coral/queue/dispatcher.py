"""Manager-side dispatcher: poll pending requests, submit to submitit, write results."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import submitit

from coral.config import QueueConfig
from coral.queue.types import EvalRequest, EvalResult
from coral.queue.worker import run_grader_job

logger = logging.getLogger(__name__)


class QueueDispatcher:
    """Runs in the manager process. Polls for eval requests and dispatches to submitit."""

    def __init__(self, coral_dir: Path, config: QueueConfig) -> None:
        self.coral_dir = coral_dir
        self.config = config
        self.pending_dir = coral_dir / "queue" / "pending"
        self.results_dir = coral_dir / "queue" / "results"
        self.executor = self._create_executor(config)
        self.active_jobs: dict[str, submitit.Job[EvalResult]] = {}
        self._last_eval_time: dict[str, float] = {}  # agent_id -> monotonic timestamp

    def _create_executor(self, config: QueueConfig) -> submitit.Executor:
        log_dir = self.coral_dir / "queue" / "submitit_logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        if config.executor == "slurm":
            ex = submitit.SlurmExecutor(folder=str(log_dir))
            ex.update_parameters(**config.executor_args)
        else:
            ex = submitit.LocalExecutor(folder=str(log_dir))

        return ex

    def poll_and_dispatch(self) -> None:
        """Called from manager's monitor_loop. Non-blocking.

        1. Check completed jobs and write results
        2. Read pending requests
        3. Apply scheduling policy + rate limiting
        4. Submit eligible requests (up to max_concurrent)
        """
        self._check_completed()
        self._dispatch_pending()

    def _check_completed(self) -> None:
        """Check active submitit jobs for completion and write results."""
        completed_tickets = []
        for ticket_id, job in self.active_jobs.items():
            if job.done():
                try:
                    result: EvalResult = job.result()
                except Exception as e:
                    result = EvalResult(
                        ticket_id=ticket_id,
                        score=None,
                        status="error",
                        error=str(e),
                    )
                result.to_json(self.results_dir / f"{ticket_id}.json")
                completed_tickets.append(ticket_id)
                logger.info(f"Eval completed: ticket={ticket_id} score={result.score}")

        for ticket_id in completed_tickets:
            del self.active_jobs[ticket_id]

    def _dispatch_pending(self) -> None:
        """Read pending requests, apply scheduling, and submit eligible ones."""
        # How many more jobs can we submit?
        available_slots = self.config.max_concurrent - len(self.active_jobs)
        if available_slots <= 0:
            return

        # Read all pending requests
        requests = self._read_pending()
        if not requests:
            return

        # Apply scheduling policy
        ordered = self._schedule(requests)

        # Apply rate limiting and submit
        submitted = 0
        for request in ordered:
            if submitted >= available_slots:
                break

            # Rate limiting per agent
            if self.config.rate_limit > 0:
                last_time = self._last_eval_time.get(request.agent_id, 0)
                if (time.monotonic() - last_time) < self.config.rate_limit:
                    continue

            self._submit(request)
            submitted += 1

    def _read_pending(self) -> list[EvalRequest]:
        """Read all pending request JSON files."""
        requests = []
        for path in self.pending_dir.glob("*.json"):
            try:
                req = EvalRequest.from_json(path)
                # Skip requests that are already being processed
                if req.ticket_id not in self.active_jobs:
                    requests.append(req)
            except (ValueError, KeyError, OSError) as e:
                logger.warning(f"Skipping malformed request {path}: {e}")
        return requests

    def _schedule(self, requests: list[EvalRequest]) -> list[EvalRequest]:
        """Order requests by scheduling strategy."""
        if self.config.strategy == "priority":
            return sorted(requests, key=lambda r: (-r.priority, r.timestamp))
        elif self.config.strategy == "fair":
            return self._fair_schedule(requests)
        else:  # fifo
            return sorted(requests, key=lambda r: r.timestamp)

    def _fair_schedule(self, requests: list[EvalRequest]) -> list[EvalRequest]:
        """Round-robin by agent_id, ordered by timestamp within each agent."""
        by_agent: dict[str, list[EvalRequest]] = {}
        for req in requests:
            by_agent.setdefault(req.agent_id, []).append(req)
        for reqs in by_agent.values():
            reqs.sort(key=lambda r: r.timestamp)

        # Round-robin: take one from each agent in turn
        result: list[EvalRequest] = []
        agent_ids = sorted(by_agent.keys())
        while agent_ids:
            exhausted = []
            for aid in agent_ids:
                if by_agent[aid]:
                    result.append(by_agent[aid].pop(0))
                else:
                    exhausted.append(aid)
            for aid in exhausted:
                agent_ids.remove(aid)
        return result

    def _submit(self, request: EvalRequest) -> None:
        """Submit a grader job to the executor and remove from pending."""
        job = self.executor.submit(run_grader_job, request)
        self.active_jobs[request.ticket_id] = job
        self._last_eval_time[request.agent_id] = time.monotonic()

        # Remove from pending directory
        pending_path = self.pending_dir / f"{request.ticket_id}.json"
        try:
            pending_path.unlink()
        except OSError:
            pass

        logger.info(
            f"Dispatched eval: ticket={request.ticket_id} "
            f"agent={request.agent_id} commit={request.commit_hash[:12]}"
        )

    def shutdown(self) -> None:
        """Cancel any active jobs."""
        for ticket_id, job in self.active_jobs.items():
            try:
                job.cancel()
            except Exception:
                pass
            # Write error result so agents don't hang
            result = EvalResult(
                ticket_id=ticket_id,
                score=None,
                status="error",
                error="Queue dispatcher shut down",
            )
            result.to_json(self.results_dir / f"{ticket_id}.json")
        self.active_jobs.clear()
