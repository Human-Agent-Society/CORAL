"""CORAL Agent Generator — runs CORAL agents and collects gateway traces as trajectories.

Spawns CORAL agents via CLI subprocess, waits for N eval attempts, stops agents,
reads gateway request logs, and converts them to rllm Trajectory objects.

Usage:
    The trainer must set _coral_state["task_yaml"] before the first call to generator().
"""

from __future__ import annotations

import atexit
import json
import logging
import subprocess
import time
from collections import defaultdict
from pathlib import Path

import rllm
from rllm.experimental.eval.types import AgentConfig, Task
from rllm.types import Episode, Step, Trajectory

logger = logging.getLogger(__name__)

N_EVALS = 1  # Number of eval attempts to wait for per training step

_coral_state: dict = {
    "task_yaml": None,        # Path to task.yaml — set by trainer before first call
    "started": False,         # Whether coral start has been called
    "coral_dir": None,        # Path to .coral directory (discovered after start)
    "trace_offset": 0,        # Line offset in requests.jsonl for incremental reads
    "seen_hashes": set(),     # commit_hashes of attempts already processed
    "manager_proc": None,     # Background subprocess running coral start/resume
}


def _cleanup() -> None:
    """Ensure CORAL agents are stopped when the process exits."""
    if _coral_state.get("started"):
        try:
            subprocess.run(
                ["coral", "stop"],
                capture_output=True,
                timeout=30,
            )
        except Exception:
            pass


atexit.register(_cleanup)


def _discover_coral_dir(task_yaml: str) -> Path:
    """Discover the .coral directory created by coral start.

    After ``coral start -c task.yaml``, the run directory is created at
    ``<results_dir>/<task_slug>/latest/.coral``.  We read the task YAML to
    figure out ``results_dir`` and ``task.name``, then follow the "latest"
    symlink.
    """
    import yaml

    with open(task_yaml) as f:
        cfg = yaml.safe_load(f)

    results_dir = Path(cfg.get("workspace", {}).get("results_dir", "./results")).resolve()
    task_name = cfg.get("task", {}).get("name", "")

    # Slugify the task name the same way CORAL does
    slug = task_name.lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    task_dir = results_dir / slug
    latest = task_dir / "latest"

    # Wait for the latest symlink to appear (coral start is async)
    deadline = time.time() + 60
    while time.time() < deadline:
        if latest.exists():
            resolved = latest.resolve() if latest.is_symlink() else latest
            coral = resolved / ".coral"
            if coral.is_dir():
                return coral
        time.sleep(1)

    raise RuntimeError(
        f"Could not find .coral directory under {task_dir}. "
        "Ensure coral start created the run successfully."
    )


def _wait_for_n_evals(
    coral_dir: Path, n: int, seen_hashes: set[str], timeout: int = 600
) -> list[str]:
    """Poll the attempts directory until *n* new attempts appear.

    Identifies new attempts by commit_hash (the filename stem of each
    ``<commit_hash>.json`` file).  Returns the list of new commit hashes.
    """
    attempts_dir = coral_dir / "public" / "attempts"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if attempts_dir.exists():
            all_hashes = {f.stem for f in attempts_dir.glob("*.json")}
            new_hashes = all_hashes - seen_hashes
            if len(new_hashes) >= n:
                return sorted(new_hashes)
        time.sleep(5)
    # Timed out — return whatever new hashes we have
    if attempts_dir.exists():
        all_hashes = {f.stem for f in attempts_dir.glob("*.json")}
        return sorted(all_hashes - seen_hashes)
    return []


def _read_new_traces(coral_dir: Path, offset: int) -> tuple[list[dict], int]:
    """Read new JSONL lines from the gateway log starting at *offset*.

    Returns (list of parsed entries, new offset).
    """
    log_path = coral_dir / "public" / "gateway" / "requests.jsonl"
    entries: list[dict] = []
    new_offset = offset

    if not log_path.exists():
        return entries, new_offset

    with open(log_path) as f:
        for i, line in enumerate(f):
            if i < offset:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Skipping malformed JSONL line %d", i)
            new_offset = i + 1

    return entries, new_offset


def _read_attempts_by_hash(
    coral_dir: Path, commit_hashes: list[str]
) -> list[dict]:
    """Read specific attempt JSON files identified by their commit hashes."""
    attempts_dir = coral_dir / "public" / "attempts"
    attempts = []
    for h in commit_hashes:
        path = attempts_dir / f"{h}.json"
        if not path.exists():
            logger.warning("Attempt file not found: %s", path)
            continue
        try:
            attempts.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read attempt: %s", path)
    attempts.sort(key=lambda a: a.get("timestamp", ""))
    return attempts


def _traces_to_trajectories(entries: list[dict]) -> list[Trajectory]:
    """Convert gateway JSONL entries into rllm Trajectory objects.

    Groups entries by agent_id. Each entry becomes a Step whose
    ``chat_completions`` field stores the request messages plus the
    assistant response.
    """
    by_agent: dict[str, list[Step]] = defaultdict(list)

    for entry in entries:
        agent_id = entry.get("agent_id", "unknown")
        request = entry.get("request", {})
        response = entry.get("response", {})

        messages = request.get("messages", [])
        content = response.get("content", "") if isinstance(response, dict) else str(response)

        step = Step(
            chat_completions=messages + [{"role": "assistant", "content": content}],
            model_response=content,
            action=content,
        )
        by_agent[agent_id].append(step)

    trajectories = []
    for agent_id, steps in by_agent.items():
        trajectories.append(Trajectory(name=agent_id, steps=steps))

    return trajectories


def _start_coral(task_yaml: str) -> subprocess.Popen:
    """Launch ``coral start`` as a background subprocess."""
    proc = subprocess.Popen(
        ["coral", "start", "--config", str(task_yaml), "run.session=local"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    logger.info("Started coral (PID %d) with config %s", proc.pid, task_yaml)
    return proc


def _resume_coral(task_yaml: str) -> subprocess.Popen:
    """Launch ``coral resume`` as a background subprocess."""
    # Derive task slug from YAML for explicit --task flag
    import yaml

    with open(task_yaml) as f:
        cfg = yaml.safe_load(f)
    task_name = cfg.get("task", {}).get("name", "")
    slug = task_name.lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")

    cmd = ["coral", "resume", "--task", slug, "run.session=local"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    logger.info("Resumed coral (PID %d) for task %s", proc.pid, slug)
    return proc


def _stop_coral() -> None:
    """Run ``coral stop`` and wait for it to finish."""
    result = subprocess.run(
        ["coral", "stop"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        logger.warning("coral stop returned %d: %s", result.returncode, result.stderr)

    # Also clean up the background manager process
    proc = _coral_state.get("manager_proc")
    if proc is not None:
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        _coral_state["manager_proc"] = None


@rllm.rollout(name="generator")
def generator(task: Task, config: AgentConfig) -> Episode:  # noqa: ARG001
    """Run CORAL agents on a task and collect LLM traces as trajectories."""
    task_yaml = _coral_state.get("task_yaml")
    if task_yaml is None:
        raise ValueError(
            "task_yaml not set. The trainer must set "
            "ttt.generator._coral_state['task_yaml'] before training."
        )

    # --- 1. Start or resume CORAL agents ---
    if not _coral_state["started"]:
        proc = _start_coral(task_yaml)
        _coral_state["manager_proc"] = proc
        _coral_state["coral_dir"] = _discover_coral_dir(task_yaml)
        _coral_state["started"] = True
        _coral_state["seen_hashes"] = set()
        _coral_state["trace_offset"] = 0
    else:
        proc = _resume_coral(task_yaml)
        _coral_state["manager_proc"] = proc

    coral_dir = _coral_state["coral_dir"]

    # --- 2. Wait for N new eval attempts (identified by commit_hash) ---
    new_hashes = _wait_for_n_evals(
        coral_dir, N_EVALS, _coral_state["seen_hashes"]
    )
    _coral_state["seen_hashes"].update(new_hashes)

    # --- 3. Stop agents (saves sessions for next resume) ---
    _stop_coral()

    # --- 4. Read new attempts for the evaluator ---
    new_attempts = _read_attempts_by_hash(coral_dir, new_hashes)

    # --- 5. Collect new gateway traces ---
    entries, new_offset = _read_new_traces(coral_dir, _coral_state["trace_offset"])
    _coral_state["trace_offset"] = new_offset

    # --- 5. Convert to rllm Trajectories ---
    trajectories = _traces_to_trajectories(entries)

    if not trajectories:
        # Return an empty episode if no traces were captured
        trajectories = [Trajectory(name="agent", steps=[])]

    return Episode(
        trajectories=trajectories,
        metadata={
            "coral_dir": str(coral_dir),
            "new_commit_hashes": new_hashes,
            "new_attempts": new_attempts,
        },
    )
