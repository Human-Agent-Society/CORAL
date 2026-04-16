"""CORAL Self-Distillation — STaR-style SFT on improving trajectories.

Replaces RL (GRPO) with self-distillation:
- Eval improved → trajectory + diagnosis rationale → SFT data
- Eval stalled → discard (wrong rationale, don't train on it)
- Agent self-diagnoses every eval via diagnose heartbeat
- Only correct rationales (ones that led to improvement) are trained on

Usage:
    Set CORAL_TASK_YAML environment variable, then SLIME calls
    ``generate_distill_data()`` as the rollout function.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

from coral_api_server import CoralAPIServer
from slime.rollout.base_types import RolloutFnTrainOutput
from slime.rollout.sglang_rollout import eval_rollout
from slime.utils.async_utils import run
from slime.utils.types import Sample

logger = logging.getLogger(__name__)

_global_worker = None
_worker_lock = threading.Lock()


def get_global_worker(args, data_buffer):
    global _global_worker
    with _worker_lock:
        if _global_worker is None or not _global_worker.worker_thread.is_alive():
            _global_worker = DistillWorker(args, data_buffer)
            _global_worker.start()
        return _global_worker


def stop_global_worker():
    global _global_worker
    with _worker_lock:
        if _global_worker is not None:
            _global_worker.stop()
            _global_worker = None


# ---------------------------------------------------------------------------
# CORAL lifecycle helpers (shared with coral_rollout.py)
# ---------------------------------------------------------------------------

def _discover_coral_dir(task_yaml: str) -> Path:
    """Discover the .coral directory created by ``coral start``."""
    import yaml

    with open(task_yaml) as f:
        cfg = yaml.safe_load(f)

    results_dir_raw = cfg.get("workspace", {}).get("results_dir", "./results")
    results_dir = Path(results_dir_raw)
    if not results_dir.is_absolute():
        results_dir = (Path.cwd() / results_dir).resolve()
    task_name = cfg.get("task", {}).get("name", "")

    slug = task_name.lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    task_dir = results_dir / slug
    latest = task_dir / "latest"

    logger.info("Looking for .coral dir at %s/latest/.coral", task_dir)

    deadline = time.time() + 120
    while time.time() < deadline:
        if latest.exists():
            resolved = latest.resolve() if latest.is_symlink() else latest
            coral = resolved / ".coral"
            if coral.is_dir():
                logger.info("Found .coral directory: %s", coral)
                return coral
        time.sleep(1)

    raise RuntimeError(f"Could not find .coral directory under {task_dir}.")


def _start_coral(task_yaml: str, base_url: str, model: str) -> subprocess.Popen:
    """Launch ``coral start`` as a background subprocess."""
    cmd = [
        "coral", "start", "--config", str(task_yaml),
        "run.session=local",
        "run.verbose=true",
    ]

    logger.info("Running: %s", " ".join(cmd))

    log_dir = Path("/tmp") / "ttt_logs"
    log_dir.mkdir(exist_ok=True)
    stdout_log = log_dir / "coral_distill_stdout.log"
    stderr_log = log_dir / "coral_distill_stderr.log"

    env = os.environ.copy()
    extra_paths = [
        str(Path.home() / ".opencode" / "bin"),
        str(Path.home() / ".local" / "bin"),
    ]
    env["PATH"] = ":".join(extra_paths) + ":" + env.get("PATH", "")
    existing_no_proxy = env.get("no_proxy", env.get("NO_PROXY", ""))
    no_proxy_hosts = {"localhost", "127.0.0.1"}
    if existing_no_proxy:
        no_proxy_hosts.update(existing_no_proxy.split(","))
    env["no_proxy"] = ",".join(sorted(no_proxy_hosts))
    env["NO_PROXY"] = env["no_proxy"]
    env["UV_BREAK_SYSTEM_PACKAGES"] = "1"
    env["PIP_BREAK_SYSTEM_PACKAGES"] = "1"

    stdout_f = open(stdout_log, "w")
    stderr_f = open(stderr_log, "w")
    proc = subprocess.Popen(
        cmd,
        stdout=stdout_f,
        stderr=stderr_f,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )
    logger.info("Started coral (PID %d) — logs at %s", proc.pid, log_dir)
    time.sleep(5)
    return proc


def _stop_coral() -> None:
    """Run ``coral stop`` and wait for it to finish."""
    logger.info("Stopping coral agents...")
    try:
        result = subprocess.run(
            ["coral", "stop"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            logger.warning("coral stop returned %d: %s", result.returncode, result.stderr)
    except subprocess.TimeoutExpired:
        logger.warning("coral stop timed out")
    except Exception as e:
        logger.warning("coral stop failed: %s", e)


def _read_attempt(attempts_dir: Path, commit_hash: str) -> dict | None:
    """Read a single attempt JSON file."""
    path = attempts_dir / f"{commit_hash}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# DistillWorker
# ---------------------------------------------------------------------------


class DistillWorker:
    """STaR-style SFT data collection from CORAL agent trajectories.

    Scoring (follows STaR — only train on correct rationales):
    - improvement > 0: keep trajectory as SFT data. The diagnosis
      heartbeat captured why the change worked — correct rationale.
    - improvement <= 0: discard trajectory. The diagnosis was wrong
      reasoning — don't train on it. Agent retries with fresh diagnosis.
    """

    def __init__(self, args, data_buffer):
        self.args = args
        self.data_buffer = data_buffer
        self.running = True
        self.output_queue: queue.Queue = queue.Queue(maxsize=100000)
        self.worker_thread = None
        self._submission_enabled = threading.Event()
        self._submission_enabled.set()

        self._server = CoralAPIServer(
            args=args,
            output_queue=self.output_queue,
            submission_enabled=self._submission_enabled,
        )

        # CORAL process state
        self._coral_proc: subprocess.Popen | None = None
        self._coral_dir: Path | None = None
        self._seen_hashes: set[str] = set()
        self._task_yaml = os.environ.get("CORAL_TASK_YAML", "")
        self._eval_monitor_thread: threading.Thread | None = None

        # Distillation metrics
        self._total_evals = 0
        self._improved_evals = 0
        self._stalled_evals = 0
        self._recovery_count = 0  # stalled → improved transitions
        self._agent_was_stalled: dict[str, bool] = {}  # tracks stall state per agent

        # Sample logger: writes JSONL with every keep/discard decision
        log_dir = Path("/tmp") / "ttt_logs"
        log_dir.mkdir(exist_ok=True)
        self._sample_log_path = log_dir / "distill_samples.jsonl"
        self._sample_log = open(self._sample_log_path, "a", buffering=1)
        logger.info("Distill sample log: %s", self._sample_log_path)

    async def continuous_worker_loop(self):
        while self.running:
            await asyncio.sleep(1.0)

    def worker_thread_func(self):
        asyncio.run(self.continuous_worker_loop())

    def start(self):
        self._server.start()
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.worker_thread = threading.Thread(
                target=self.worker_thread_func, daemon=True,
            )
            self.worker_thread.start()

    def start_agents_if_needed(self):
        if self._coral_proc is not None:
            return
        if not self._task_yaml:
            logger.warning("CORAL_TASK_YAML not set")
            return
        self._start_coral_agents()
        self._start_eval_monitor()

    def _start_coral_agents(self):
        api_port = int(os.getenv("PORT", "30000"))
        base_url = f"http://127.0.0.1:{api_port}"
        model = os.getenv("SERVED_MODEL_NAME", "qwen3-30b-a3b")

        import httpx
        test_body = {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }
        for attempt in range(90):
            try:
                r = httpx.post(f"{base_url}/v1/chat/completions", json=test_body, timeout=10)
                if r.status_code == 200:
                    logger.info("API server ready at %s", base_url)
                    break
            except Exception:
                pass
            if attempt % 10 == 0:
                logger.info("Waiting for API server (attempt %d)...", attempt)
            time.sleep(2)

        self._coral_proc = _start_coral(self._task_yaml, base_url, model)
        self._coral_dir = _discover_coral_dir(self._task_yaml)

        gateway_log = self._coral_dir / "public" / "gateway" / "requests.jsonl"
        self._server.set_gateway_log(str(gateway_log))

    def _start_eval_monitor(self):
        if self._coral_dir is None:
            return
        self._eval_monitor_thread = threading.Thread(
            target=self._eval_monitor_loop, daemon=True,
        )
        self._eval_monitor_thread.start()

    def _eval_monitor_loop(self):
        """Poll for eval attempts. Route to distill scoring instead of RL rewards."""
        attempts_dir = self._coral_dir / "public" / "attempts"
        logger.info("Distill eval monitor started, watching %s", attempts_dir)

        while self.running:
            if not attempts_dir.exists():
                time.sleep(5)
                continue

            all_hashes = {f.stem for f in attempts_dir.glob("*.json")}
            new_hashes = all_hashes - self._seen_hashes

            for commit_hash in sorted(new_hashes):
                attempt = _read_attempt(attempts_dir, commit_hash)
                if attempt is None:
                    continue

                agent_id = attempt.get("agent_id", "unknown")
                score = attempt.get("score") or 0.0
                feedback = attempt.get("feedback", "")
                parent_hash = attempt.get("parent_hash")
                parent_score = 0.0

                if parent_hash:
                    parent = _read_attempt(attempts_dir, parent_hash)
                    if parent:
                        parent_score = parent.get("score") or 0.0

                self._handle_eval_result(
                    agent_id=agent_id,
                    score=score,
                    parent_score=parent_score,
                    feedback=feedback,
                )
                self._seen_hashes.add(commit_hash)

            time.sleep(5)

    def _handle_eval_result(
        self,
        agent_id: str,
        score: float,
        parent_score: float,
        feedback: str,
    ) -> None:
        """STaR-style scoring: only train on rationales that led to improvement.

        improved (score > parent_score):
          Submit current pending trajectory as SFT data. This trajectory
          contains the diagnosis from the heartbeat ("I did X, it worked
          because Y") — a correct rationale leading to a correct outcome.
          Discard any stashed samples from previous stalls (those were
          wrong rationales that didn't lead to improvement).

        not improved (score <= parent_score):
          Discard all pending samples. The diagnosis from this eval
          ("I think X caused the problem") is likely wrong reasoning —
          it didn't lead to improvement. Don't train on it.
          The agent will get a fresh diagnosis prompt on the next
          heartbeat and try again.
        """
        self._total_evals += 1
        improvement = score - parent_score
        # First eval (no parent) with any positive score counts as improvement
        is_first_eval = (parent_score == 0.0 and score > 0.0)
        improved = improvement > 0 or is_first_eval

        # Snapshot pending samples for logging before they get popped
        with self._server._pending_lock:
            pending = self._server._pending_samples.get(agent_id, [])
            sample_previews = self._preview_samples(pending)

        if improved:
            self._improved_evals += 1

            # Track recovery (was stalled, now improved)
            if self._agent_was_stalled.get(agent_id, False):
                self._recovery_count += 1
            self._agent_was_stalled[agent_id] = False

            # Submit current trajectory as SFT data.
            self._server.report_eval_score_distill(agent_id, score, keep=True)

            self._log_sample(
                agent_id=agent_id, score=score, parent_score=parent_score,
                keep=True, feedback=feedback, samples=sample_previews,
            )

            logger.info(
                "[Distill] IMPROVED: agent=%s %.4f→%.4f (+%.4f) — "
                "%d evals / %d improved / %d recoveries",
                agent_id, parent_score, score, improvement,
                self._total_evals, self._improved_evals, self._recovery_count,
            )
        else:
            self._stalled_evals += 1
            self._agent_was_stalled[agent_id] = True

            # Discard: wrong rationale, didn't lead to improvement.
            self._server.report_eval_score_distill(agent_id, score, keep=False)

            self._log_sample(
                agent_id=agent_id, score=score, parent_score=parent_score,
                keep=False, feedback=feedback, samples=sample_previews,
            )

            logger.info(
                "[Distill] STALLED: agent=%s %.4f→%.4f (no improvement) — "
                "discarding samples (wrong rationale), feedback='%s'",
                agent_id, parent_score, score, feedback[:100],
            )

    def _preview_samples(self, samples: list, max_len: int = 500) -> list[dict]:
        """Create truncated previews of samples for logging."""
        previews = []
        for s in samples:
            previews.append({
                "index": s.index,
                "prompt_tail": (s.prompt or "")[-max_len:],
                "response_head": (s.response or "")[:max_len],
                "response_length": s.response_length,
                "loss_mask_sum": sum(s.loss_mask) if s.loss_mask else 0,
            })
        return previews

    def _log_sample(
        self, agent_id: str, score: float, parent_score: float,
        keep: bool, feedback: str, samples: list[dict],
    ) -> None:
        """Write a JSONL entry for each eval decision."""
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "agent_id": agent_id,
            "score": score,
            "parent_score": parent_score,
            "improvement": score - parent_score,
            "keep": keep,
            "feedback": feedback[:200],
            "num_samples": len(samples),
            "samples": samples[:3],  # log up to 3 sample previews
        }
        try:
            self._sample_log.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def pause_submission(self):
        if self._submission_enabled.is_set():
            self._submission_enabled.clear()
            self._server.purge_record_files()
            print("[Distill] submission paused", flush=True)

    def resume_submission(self):
        if not self._submission_enabled.is_set():
            self._submission_enabled.set()
            print("[Distill] submission resumed", flush=True)

    def get_completed_groups(self) -> list[tuple]:
        completed = []
        while True:
            try:
                completed.append(self.output_queue.get_nowait())
            except queue.Empty:
                break
        return completed

    def get_queue_size(self) -> int:
        return self.output_queue.qsize()

    def stop(self):
        self.running = False
        self._submission_enabled.clear()

        # Flush remaining — discard since no final eval
        with self._server._pending_lock:
            for agent_id in list(self._server._pending_samples.keys()):
                self._server.flush_agent(agent_id)

        if self._coral_proc is not None:
            _stop_coral()
            try:
                self._coral_proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._coral_proc.kill()
            self._coral_proc = None

        self._server.stop()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)

        # Close sample log
        if hasattr(self, "_sample_log") and self._sample_log:
            self._sample_log.close()

        # Print final stats
        print(
            f"[Distill] Final stats: {self._total_evals} evals, "
            f"{self._improved_evals} improved, {self._stalled_evals} stalled, "
            f"{self._recovery_count} recoveries\n"
            f"[Distill] Sample log: {self._sample_log_path}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# Drain & rollout function
# ---------------------------------------------------------------------------


async def _drain_output_queue(args, worker: DistillWorker) -> list[list[Sample]]:
    """Wait until rollout_batch_size SFT samples are collected."""
    target_data_size = args.rollout_batch_size
    data: list[list[Sample]] = []
    completed_groups: dict[int, list[Sample]] = {}
    start = time.time()
    last_progress = start

    while len(data) < target_data_size:
        completed = worker.get_completed_groups()
        if completed:
            last_progress = time.time()
            for group_id, group in completed:
                completed_groups[group_id] = group

        for group_id in list(completed_groups.keys()):
            if len(data) >= target_data_size:
                break
            group = completed_groups.pop(group_id)
            if any(s.status == Sample.Status.ABORTED for s in group):
                continue
            # Only keep samples with active loss mask (SFT data)
            if any(sum(s.loss_mask) > 0 for s in group):
                data.append(group)

        if time.time() - last_progress > 30:
            print(
                f"[Distill] waiting for SFT samples: {len(data)}/{target_data_size}, "
                f"queue={worker.get_queue_size()}",
                flush=True,
            )
            last_progress = time.time()

        if len(data) < target_data_size:
            await asyncio.sleep(0.05)

    data.sort(
        key=lambda group: group[0].index if group and group[0].index is not None else -1,
    )
    print(
        f"[Distill] drained {len(data)} SFT groups in {time.time() - start:.2f}s",
        flush=True,
    )
    return data


def generate_distill_data(args, rollout_id, data_buffer, evaluation=False):
    """SLIME rollout function entry point for self-distillation.

    Registered via ``--rollout-function-path coral_distill.generate_distill_data``.
    """
    worker = get_global_worker(args, data_buffer)

    if evaluation:
        eval_output, _ = run(eval_rollout(args, rollout_id))
        return eval_output

    worker._server.reset_eval_scores()
    worker.resume_submission()
    worker.start_agents_if_needed()
    completed_samples = run(_drain_output_queue(args, worker))
    worker.pause_submission()

    extra_metrics = {
        "distill/total_evals": worker._total_evals,
        "distill/improved_evals": worker._improved_evals,
        "distill/stalled_evals": worker._stalled_evals,
        "distill/recovery_count": worker._recovery_count,
    }

    eval_scores = worker._server.drain_eval_scores()
    if eval_scores:
        avg_score = sum(eval_scores) / len(eval_scores)
        extra_metrics["distill/avg_eval_score"] = avg_score
        success_rate = len([s for s in eval_scores if s > 0]) / len(eval_scores)
        extra_metrics["distill/success_rate"] = success_rate
        print(
            f"[Distill] avg_score={avg_score:.4f} success_rate={success_rate:.2%} "
            f"(n={len(eval_scores)})",
            flush=True,
        )

    return RolloutFnTrainOutput(samples=completed_samples, metrics=extra_metrics)


atexit.register(stop_global_worker)
