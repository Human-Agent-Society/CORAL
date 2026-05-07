"""Tests for the grader daemon and the agent↔grader file-queue protocol."""

from __future__ import annotations

import json
import multiprocessing
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from coral.config import CoralConfig
from coral.grader.daemon import (
    _find_pending,
    _is_git_repo,
    _repo_dir,
    process_pending_once,
    run_daemon,
)
from coral.hooks.post_commit import submit_eval
from coral.hub.attempts import read_attempt, read_eval_count, write_attempt
from coral.types import Attempt

# The fixture below uses the deprecated eval/grader.py loading path on
# purpose (it's the simplest way to wire a TaskGrader without standing up a
# real grader venv). Silence the DeprecationWarning for the whole module.
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

def _init_repo_and_coral(base_dir: Path, score: float = 0.5) -> Path:
    """Create a git repo with .coral/ wired up to a minimal eval/grader.py."""
    repo = base_dir / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@test.com"],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        capture_output=True, check=True,
    )

    (repo / "main.py").write_text("print('hello')\n")
    (repo / ".gitignore").write_text(
        ".coral/\n.coral_dir\n.claude/\n.coral_agent_id\nCLAUDE.md\n"
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "main.py", ".gitignore"],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "Initial"],
        capture_output=True, check=True,
    )

    coral_dir = repo / ".coral"
    (coral_dir / "public" / "attempts").mkdir(parents=True)
    eval_dir = coral_dir / "private" / "eval"
    eval_dir.mkdir(parents=True)

    (repo / ".coral_dir").write_text(str(coral_dir.resolve()))

    (eval_dir / "grader.py").write_text(
        "from coral.grader.task_grader import TaskGrader\n"
        "class Grader(TaskGrader):\n"
        "    def evaluate(self):\n"
        f"        return {score!r}\n"
    )

    config = {
        "task": {"name": "daemon_test", "description": "Daemon test"},
        "grader": {
            "timeout": 60,
        },
        "agents": {"count": 1},
        "sharing": {"attempts": True, "notes": True, "skills": True},
        "workspace": {"base_dir": str(repo), "repo_path": str(repo)},
    }
    with open(coral_dir / "config.yaml", "w") as f:
        yaml.dump(config, f)

    return repo


# --------------------------------------------------------------------------- #
# _repo_dir — handles both production and test layouts                        #
# --------------------------------------------------------------------------- #

def test_repo_dir_detects_test_layout():
    """When .coral/ lives inside the repo, daemon falls back to coral_dir.parent."""
    with tempfile.TemporaryDirectory() as d:
        repo = _init_repo_and_coral(Path(d))
        coral_dir = repo / ".coral"

        assert _repo_dir(coral_dir) == repo
        assert _is_git_repo(repo)
        assert not _is_git_repo(coral_dir)


def test_repo_dir_prefers_run_dir_repo():
    """Production layout places repo/ alongside .coral/. Daemon picks it."""
    with tempfile.TemporaryDirectory() as d:
        run_dir = Path(d)
        repo = run_dir / "repo"
        _init_repo_and_coral(run_dir)  # creates run_dir/repo and run_dir/repo/.coral

        # Copy .coral up to the run_dir level so we get run_dir/.coral + run_dir/repo
        production_coral = run_dir / ".coral"
        (repo / ".coral").rename(production_coral)
        assert _repo_dir(production_coral) == repo


# --------------------------------------------------------------------------- #
# process_pending_once — drains the queue without spawning a daemon           #
# --------------------------------------------------------------------------- #

def test_process_pending_once_grades_pending():
    """A submitted pending attempt gets scored after one drain."""
    with tempfile.TemporaryDirectory() as d:
        repo = _init_repo_and_coral(Path(d), score=0.42)
        sys.path.insert(0, str(repo))
        try:
            (repo / "main.py").write_text("print('v2')\n")
            pending = submit_eval(
                message="Change", agent_id="agent-1", workdir=str(repo), wait=False,
            )
            assert pending.status == "pending"

            finalized = process_pending_once(repo / ".coral")
            assert len(finalized) == 1
            assert finalized[0].score == 0.42
            assert finalized[0].status == "improved"
            assert finalized[0].commit_hash == pending.commit_hash

            # No more pending after the drain.
            assert _find_pending(repo / ".coral") == []
        finally:
            sys.path.pop(0)


def test_process_pending_once_is_idempotent():
    """Running the drain a second time is a no-op when nothing is pending."""
    with tempfile.TemporaryDirectory() as d:
        repo = _init_repo_and_coral(Path(d))
        sys.path.insert(0, str(repo))
        try:
            (repo / "main.py").write_text("print('v2')\n")
            submit_eval(message="c", agent_id="agent-1", workdir=str(repo), wait=False)

            first = process_pending_once(repo / ".coral")
            second = process_pending_once(repo / ".coral")
            assert len(first) == 1
            assert second == []
        finally:
            sys.path.pop(0)


def test_process_pending_once_preserves_submission_fields():
    """Grader finalization must not clobber commit_hash, title, timestamp, parent_hash."""
    with tempfile.TemporaryDirectory() as d:
        repo = _init_repo_and_coral(Path(d))
        sys.path.insert(0, str(repo))
        try:
            (repo / "main.py").write_text("print('v2')\n")
            pending = submit_eval(
                message="Preserve me", agent_id="agent-1",
                workdir=str(repo), wait=False,
            )
            original_ts = pending.timestamp
            process_pending_once(repo / ".coral")

            final = read_attempt(repo / ".coral", pending.commit_hash)
            assert final is not None
            assert final.commit_hash == pending.commit_hash
            assert final.title == "Preserve me"
            assert final.agent_id == "agent-1"
            assert final.timestamp == original_ts  # daemon doesn't restamp
            assert final.parent_hash == pending.parent_hash
        finally:
            sys.path.pop(0)


def test_process_pending_multiple_in_submission_order():
    """Pending attempts are graded in submission (timestamp) order."""
    with tempfile.TemporaryDirectory() as d:
        repo = _init_repo_and_coral(Path(d))
        # This test exercises consumer-side ordering, so disable the
        # producer-side per-agent pending cap (default 1) to allow stacking.
        cfg_path = repo / ".coral" / "config.yaml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        cfg["grader"]["max_pending_per_agent"] = 0
        with open(cfg_path, "w") as f:
            yaml.dump(cfg, f)

        sys.path.insert(0, str(repo))
        try:
            (repo / "main.py").write_text("print('a')\n")
            a = submit_eval(message="a", agent_id="agent-1",
                            workdir=str(repo), wait=False)
            (repo / "main.py").write_text("print('b')\n")
            b = submit_eval(message="b", agent_id="agent-1",
                            workdir=str(repo), wait=False)

            finalized = process_pending_once(repo / ".coral")
            assert [f.commit_hash for f in finalized] == [a.commit_hash, b.commit_hash]
        finally:
            sys.path.pop(0)


# --------------------------------------------------------------------------- #
# Atomic write — writer and concurrent reader never collide                   #
# --------------------------------------------------------------------------- #

def test_write_attempt_is_atomic():
    """Rapid writes interleaved with reads never yield a partial JSON.

    Cheap proxy: write_attempt should use tmp+rename so any read either sees
    the previous complete version or the new complete version.
    """
    with tempfile.TemporaryDirectory() as d:
        coral_dir = Path(d) / ".coral"
        (coral_dir / "public" / "attempts").mkdir(parents=True)

        commit_hash = "a" * 40
        attempt = Attempt(
            commit_hash=commit_hash,
            agent_id="a1",
            title="t",
            score=None,
            status="pending",
            parent_hash=None,
            timestamp=datetime.now(UTC).isoformat(),
        )
        write_attempt(str(coral_dir), attempt)

        target = coral_dir / "public" / "attempts" / f"{commit_hash}.json"
        # Hammer the writer while reading; every read must parse as JSON.
        for i in range(50):
            attempt.score = float(i)
            write_attempt(str(coral_dir), attempt)
            data = json.loads(target.read_text())
            assert data["score"] == float(i)


# --------------------------------------------------------------------------- #
# Isolated worktree — grader doesn't see agent's post-submit edits            #
# --------------------------------------------------------------------------- #

def test_grader_sees_committed_code_not_working_tree():
    """If the agent mutates files after submit, grader must grade the commit snapshot."""
    with tempfile.TemporaryDirectory() as d:
        repo = _init_repo_and_coral(Path(d))
        # Grader reports sentinel = content of main.py at checkout time.
        (repo / ".coral" / "private" / "eval" / "grader.py").write_text(
            "import os\n"
            "from coral.grader.task_grader import TaskGrader\n"
            "class Grader(TaskGrader):\n"
            "    def evaluate(self):\n"
            "        with open(os.path.join(self.codebase_path, 'main.py')) as f:\n"
            "            content = f.read()\n"
            "        return 1.0 if 'COMMITTED' in content else 0.0\n"
        )
        try:
            (repo / "main.py").write_text("# COMMITTED\nprint('x')\n")
            pending = submit_eval(
                message="stable snapshot", agent_id="agent-1",
                workdir=str(repo), wait=False,
            )
            # Agent now mutates the working tree post-submission — should NOT affect grading.
            (repo / "main.py").write_text("# POST-SUBMIT\nprint('y')\n")

            process_pending_once(repo / ".coral")
            final = read_attempt(repo / ".coral", pending.commit_hash)
            assert final is not None
            assert final.score == 1.0, (
                "Grader must use the isolated checkout at commit_hash, "
                "not the agent's live working tree."
            )
        finally:
            pass


# --------------------------------------------------------------------------- #
# run_daemon subprocess — submit from main process, daemon in child           #
# --------------------------------------------------------------------------- #

def test_run_daemon_subprocess_grades_pending():
    """End-to-end: spawn the daemon in a subprocess and verify it picks up pending."""
    with tempfile.TemporaryDirectory() as d:
        repo = _init_repo_and_coral(Path(d), score=0.9)

        # Grader module must be importable in the daemon subprocess too.
        env_shim = repo / "conftest_shim.pth"
        # Use a .pth-style trick: prepend repo to sys.path via PYTHONPATH env.
        import os

        sys.path.insert(0, str(repo))
        os.environ["PYTHONPATH"] = (
            str(repo) + os.pathsep + os.environ.get("PYTHONPATH", "")
        )
        try:
            (repo / "main.py").write_text("print('real daemon')\n")
            pending = submit_eval(
                message="daemon run", agent_id="agent-1",
                workdir=str(repo), wait=False,
            )

            stop_event = multiprocessing.Event()
            proc = multiprocessing.Process(
                target=run_daemon, args=(str(repo / ".coral"), stop_event),
            )
            proc.start()
            try:
                deadline = time.monotonic() + 30.0
                final = None
                while time.monotonic() < deadline:
                    final = read_attempt(repo / ".coral", pending.commit_hash)
                    if final and final.status != "pending":
                        break
                    time.sleep(0.2)
                assert final is not None and final.status != "pending"
                assert final.score == 0.9
            finally:
                stop_event.set()
                proc.join(timeout=10)
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=5)
                proc.close()
        finally:
            sys.path.pop(0)
            _ = env_shim  # silence linter


# --------------------------------------------------------------------------- #
# Parallel drain (issue #81)                                                  #
# --------------------------------------------------------------------------- #


def test_default_max_workers_is_1():
    """Configs without `grader.parallel` get max_workers=1 (legacy behavior)."""
    cfg = CoralConfig.from_dict(
        {"task": {"name": "x", "description": "y"}, "agents": {"count": 1}}
    )
    assert cfg.grader.parallel.max_workers == 1


def _install_concurrency_probe_grader(repo: Path, sleep_seconds: float) -> Path:
    """Overwrite eval/grader.py with one that reports peak concurrent executions.

    Each grade increments a shared counter on entry, sleeps, decrements on
    exit. The counter is in a JSON file under private_dir, mutated under
    fcntl.flock so concurrent grades can't lose updates. Returns the path to
    that file so the test can read `max` after the drain.
    """
    coral_dir = repo / ".coral"
    log_path = coral_dir / "private" / "concurrency.json"
    grader_src = (
        "import fcntl, json, time\n"
        "from pathlib import Path\n"
        "from coral.grader.task_grader import TaskGrader\n"
        "\n"
        f"LOG_PATH = {str(log_path)!r}\n"
        f"SLEEP = {sleep_seconds!r}\n"
        "\n"
        "def _bump(delta):\n"
        "    p = Path(LOG_PATH)\n"
        "    p.touch(exist_ok=True)\n"
        "    with open(p, 'r+') as f:\n"
        "        fcntl.flock(f, fcntl.LOCK_EX)\n"
        "        text = f.read() or '{}'\n"
        "        try: data = json.loads(text)\n"
        "        except Exception: data = {}\n"
        "        data['current'] = data.get('current', 0) + delta\n"
        "        if delta > 0:\n"
        "            data['max'] = max(data.get('max', 0), data['current'])\n"
        "        f.seek(0); f.truncate()\n"
        "        f.write(json.dumps(data))\n"
        "        f.flush()\n"
        "        fcntl.flock(f, fcntl.LOCK_UN)\n"
        "\n"
        "class Grader(TaskGrader):\n"
        "    def evaluate(self):\n"
        "        _bump(1)\n"
        "        try:\n"
        "            time.sleep(SLEEP)\n"
        "        finally:\n"
        "            _bump(-1)\n"
        "        return 1.0\n"
    )
    (coral_dir / "private" / "eval" / "grader.py").write_text(grader_src)
    return log_path


def _set_config(repo: Path, **grader_overrides) -> None:
    """Patch grader fields in .coral/config.yaml in-place."""
    cfg_path = repo / ".coral" / "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("grader", {}).update(grader_overrides)
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f)


def _submit_n(repo: Path, n: int) -> list[str]:
    """Make N distinct commits and submit each as a pending attempt."""
    hashes = []
    for i in range(n):
        (repo / "main.py").write_text(f"print('v{i}')\n")
        attempt = submit_eval(
            message=f"v{i}", agent_id="agent-1", workdir=str(repo), wait=False,
        )
        hashes.append(attempt.commit_hash)
    return hashes


def test_drain_runs_in_parallel_when_max_workers_gt_1():
    """With max_workers=4, four 0.4s grades overlap (peak concurrency > 1)."""
    with tempfile.TemporaryDirectory() as d:
        repo = _init_repo_and_coral(Path(d))
        log_path = _install_concurrency_probe_grader(repo, sleep_seconds=0.4)
        _set_config(
            repo,
            max_pending_per_agent=0,  # allow stacking 4 pending from one agent
            parallel={"max_workers": 4},
        )

        sys.path.insert(0, str(repo))
        try:
            _submit_n(repo, 4)
            finalized = process_pending_once(repo / ".coral")
            assert len(finalized) == 4
            assert all(a.score == 1.0 for a in finalized)

            data = json.loads(log_path.read_text())
            assert data["max"] >= 2, (
                f"Expected overlapping grades with max_workers=4, got max={data['max']}"
            )
            assert data["current"] == 0  # all grades finished
        finally:
            sys.path.pop(0)


def test_drain_serializes_when_max_workers_is_1():
    """max_workers=1 keeps the legacy serial behavior — peak concurrency stays 1."""
    with tempfile.TemporaryDirectory() as d:
        repo = _init_repo_and_coral(Path(d))
        log_path = _install_concurrency_probe_grader(repo, sleep_seconds=0.2)
        _set_config(
            repo,
            max_pending_per_agent=0,
            parallel={"max_workers": 1},
        )

        sys.path.insert(0, str(repo))
        try:
            _submit_n(repo, 3)
            finalized = process_pending_once(repo / ".coral")
            assert len(finalized) == 3

            data = json.loads(log_path.read_text())
            assert data["max"] == 1, (
                f"Expected serial grading with max_workers=1, got max={data['max']}"
            )
        finally:
            sys.path.pop(0)


def test_eval_count_correct_under_parallel_grading():
    """Race-prone increment_eval_count stays correct when grades run in parallel."""
    with tempfile.TemporaryDirectory() as d:
        repo = _init_repo_and_coral(Path(d))
        _install_concurrency_probe_grader(repo, sleep_seconds=0.1)
        _set_config(
            repo,
            max_pending_per_agent=0,
            parallel={"max_workers": 4},
        )

        sys.path.insert(0, str(repo))
        try:
            _submit_n(repo, 5)
            process_pending_once(repo / ".coral")
            assert read_eval_count(repo / ".coral") == 5
        finally:
            sys.path.pop(0)


def test_invalid_max_workers_rejected():
    """grader.parallel.max_workers must be >= 1."""
    with pytest.raises(ValueError, match="max_workers"):
        CoralConfig.from_dict(
            {
                "task": {"name": "x", "description": "y"},
                "grader": {"parallel": {"max_workers": 0}},
            }
        )
