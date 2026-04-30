"""Spawn N agents, monitor health, auto-resume with eval feedback."""

from __future__ import annotations

import atexit
import json
import logging
import multiprocessing
import os
import signal
import threading
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coral.agent.exit_classifier import (
    classify_by_uptime,
)
from coral.agent.exit_classifier import (
    claude_code_log_has_session_error as _log_has_session_error,
)
from coral.agent.heartbeat import HeartbeatRunner
from coral.agent.registry import get_runtime
from coral.agent.runtime import AgentHandle, AgentRuntime
from coral.agent.state import (
    AgentRuntimeState,
    AgentStateDocument,
    RestartEvent,
    write_agent_state,
)
from coral.agent.warmstart import WarmStartRunner
from coral.config import CoralConfig
from coral.hub.attempts import agent_in_grader_queue, read_attempts
from coral.hub.heartbeat import (
    DEFAULT_PROMPTS,
    DEFAULT_TRIGGER,
    default_global_actions,
    default_local_actions,
    read_agent_heartbeat,
    read_global_heartbeat,
    write_agent_heartbeat,
    write_global_heartbeat,
)
from coral.template.coral_md import generate_coral_md
from coral.workspace import (
    ProjectPaths,
    create_agent_worktree,
    create_project,
    setup_claude_settings,
    setup_codex_settings,
    setup_gitignore,
    setup_opencode_settings,
    setup_shared_state,
    setup_worktree_env,
    write_agent_id,
    write_coral_dir,
)

logger = logging.getLogger(__name__)


class AgentManager:
    """Manage the lifecycle of multiple CORAL agents."""

    def __init__(
        self, config: CoralConfig, verbose: bool = False,
        config_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.config_dir = config_dir
        self.runtime: AgentRuntime = get_runtime(config.agents.runtime)
        self.handles: list[AgentHandle] = []
        self.paths: ProjectPaths | None = None
        self.verbose = verbose
        self._running = False
        self._stop_event = threading.Event()
        self._stopping = False
        self._start_time: datetime | None = None
        self._restart_counts: dict[str, int] = {}
        self._agent_eval_counts: dict[str, int] = {}
        self._agent_best_scores: dict[str, float] = {}
        self._agent_evals_since_improvement: dict[str, int] = {}
        # Reliability state. `_started_at` records when each agent's current
        # subprocess began running (epoch seconds), used as the uptime input
        # for the runtime exit classifier. `_crash_history` is the sliding
        # window of non-clean exits the circuit breaker counts. `_paused_until`
        # is the wall-clock deadline at which a paused agent is allowed to
        # restart again. `_pause_count` and `_last_fault_at` are persisted
        # metadata on `agent_state.json` for `coral status`.
        # `_pending_restart_after_pause` tracks agents whose pause just
        # expired so the dead-agent branch restarts them once without
        # re-classifying the original exit (which would double-count it).
        self._started_at: dict[str, float] = {}
        self._crash_history: dict[str, deque[RestartEvent]] = {}
        self._paused_until: dict[str, float] = {}
        self._pause_count: dict[str, int] = {}
        self._last_fault_at: dict[str, str] = {}
        self._pending_restart_after_pause: set[str] = set()
        self._gateway: Any | None = None
        self._gateway_keys: dict[str, str] = {}  # agent_id -> proxy key
        self._grader_proc: multiprocessing.Process | None = None
        self._grader_stop_event: Any | None = None  # multiprocessing.Event

    def start_all(self) -> list[AgentHandle]:
        """Create workspace structure and spawn all agents."""
        self._start_time = datetime.now(UTC)

        # 1. Create project structure
        self.paths = create_project(self.config, config_dir=self.config_dir)
        logger.info(f"Run directory: {self.paths.run_dir}")
        logger.info(f"  coral_dir: {self.paths.coral_dir}")
        logger.info(f"  repo_dir:  {self.paths.repo_dir}")

        # 1b. Start gateway if configured
        self._start_gateway_if_enabled()

        # 1c. Start grader daemon. Agents' `coral eval` writes pending attempts;
        #     the daemon picks them up, grades inside an isolated worktree,
        #     and writes the score back. Must be running before agents start.
        self._start_grader_daemon()

        # 2. Seed global heartbeat config if not already present
        if not read_global_heartbeat(self.paths.coral_dir):
            write_global_heartbeat(self.paths.coral_dir, default_global_actions(self.config))
            logger.info("Seeded global heartbeat config")

        # 3. Warm-start research phase (optional)
        agent_ids = [f"agent-{i + 1}" for i in range(self.config.agents.count)]
        warmstart = WarmStartRunner(self.config, self.runtime.shared_dir_name)
        research_sessions: dict[str, str] = {}

        if warmstart.enabled:
            research_sessions = self._run_warmstart_research(warmstart, agent_ids)

        # 4. For each agent: create worktree, generate CLAUDE.md, spawn runtime
        handles = []
        for i, agent_id in enumerate(agent_ids):
            if i > 0 and self.config.agents.stagger_seconds > 0:
                logger.info(f"Staggering {agent_id} by {self.config.agents.stagger_seconds}s")
                time.sleep(self.config.agents.stagger_seconds)
            handle = self._setup_and_start_agent(
                agent_id,
                resume_session_id=research_sessions.get(agent_id),
                prompt=warmstart.main_prompt() if warmstart.enabled else None,
                prompt_source="warmstart:main" if warmstart.enabled else None,
            )
            handles.append(handle)

        self.handles = handles
        self._running = True

        # 5. Write PID file
        self._write_pid_file()

        # 6. Register atexit handler as safety net for unexpected exits
        atexit.register(self._atexit_cleanup)

        return handles

    def _start_grader_daemon(self) -> None:
        """Spawn the grader daemon subprocess. Idempotent.

        Before spawning, kills any stale daemon from a prior run whose PID is
        still recorded in .coral/public/grader_daemon.pid — otherwise two
        daemons would race for the same pending attempts.
        """
        assert self.paths is not None

        if self._grader_proc is not None and self._grader_proc.is_alive():
            return

        # Best-effort cleanup of a stale daemon from a previous run.
        pid_file = self.paths.coral_dir / "public" / "grader_daemon.pid"
        if pid_file.exists():
            try:
                stale_pid = int(pid_file.read_text().strip())
                os.kill(stale_pid, signal.SIGTERM)
                logger.info(f"Killed stale grader daemon PID {stale_pid}")
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                pass  # PID gone or unkillable — just move on
            try:
                pid_file.unlink()
            except OSError:
                pass

        # Lazy import — tests and CLI-only paths should not trigger grader import.
        from coral.grader.daemon import run_daemon

        stop_event = multiprocessing.Event()
        proc = multiprocessing.Process(
            target=run_daemon,
            args=(str(self.paths.coral_dir), stop_event),
            name="coral-grader-daemon",
            daemon=False,  # explicit: we manage its lifecycle
        )
        proc.start()
        self._grader_proc = proc
        self._grader_stop_event = stop_event
        try:
            pid_file.write_text(str(proc.pid))
        except OSError:
            pass
        logger.info(f"Grader daemon started (PID {proc.pid})")
        if self.verbose:
            print(f"[coral] Grader daemon running (PID {proc.pid})")

    def _stop_grader_daemon(self, timeout: float = 10.0) -> None:
        """Signal the grader daemon to stop, then wait and fall back to SIGTERM/SIGKILL."""
        proc = self._grader_proc
        if proc is None:
            return

        if self._grader_stop_event is not None:
            try:
                self._grader_stop_event.set()
            except Exception:
                pass

        try:
            proc.join(timeout=timeout)
            if proc.is_alive():
                logger.warning("Grader daemon ignored stop event; sending SIGTERM")
                proc.terminate()
                proc.join(timeout=5)
            if proc.is_alive():
                logger.warning("Grader daemon ignored SIGTERM; sending SIGKILL")
                proc.kill()
                proc.join(timeout=5)
        finally:
            try:
                proc.close()
            except Exception:
                pass
            self._grader_proc = None
            self._grader_stop_event = None
            if self.paths is not None:
                pid_file = self.paths.coral_dir / "public" / "grader_daemon.pid"
                try:
                    if pid_file.exists():
                        pid_file.unlink()
                except OSError:
                    pass
            logger.info("Grader daemon stopped")

    def _start_gateway_if_enabled(self) -> None:
        """Start the LiteLLM gateway if configured."""
        assert self.paths is not None
        gw_cfg = self.config.agents.gateway
        if not gw_cfg.enabled:
            return

        from coral.gateway.config import generate_default_litellm_config
        from coral.gateway.server import GatewayManager

        # Resolve config path relative to task dir
        config_path = gw_cfg.config
        if not config_path:
            # Generate default config at project root
            config_path = str(self.paths.run_dir / "litellm_config.yaml")
            generate_default_litellm_config(
                Path(config_path), model=self.config.agents.model,
            )
        elif not Path(config_path).is_absolute():
            if self.config.task_dir:
                config_path = str(self.config.task_dir / config_path)
            else:
                logger.warning(
                    f"Cannot resolve relative gateway config '{config_path}': "
                    f"task_dir is unknown. Trying as-is."
                )

        log_dir = self.paths.coral_dir / "public" / "gateway"
        gateway = GatewayManager(
            port=gw_cfg.port,
            config_path=config_path,
            api_key=gw_cfg.api_key,
            log_dir=log_dir,
        )
        gateway.start()
        self._gateway = gateway
        logger.info(f"Gateway running at {gateway.url}")

    def _run_warmstart_research(
        self, warmstart: WarmStartRunner, agent_ids: list[str],
    ) -> dict[str, str]:
        """Run the warm-start research phase. Returns {agent_id: session_id}."""
        assert self.paths is not None

        research_prompt = warmstart.research_prompt()

        if self.verbose:
            print("\n[coral] Warm-start: research phase...\n")
        logger.info("Warm-start: starting research phase")

        research_handles = []
        for i, agent_id in enumerate(agent_ids):
            if i > 0 and self.config.agents.stagger_seconds > 0:
                time.sleep(self.config.agents.stagger_seconds)
            handle = self._setup_and_start_agent(
                agent_id,
                prompt=research_prompt,
                prompt_source="warmstart:research",
            )
            research_handles.append(handle)

        # Wait for all research agents to finish
        warmstart.wait_for_research(research_handles)

        # Extract session IDs for resumption in the main phase
        sessions: dict[str, str] = {}
        for handle in research_handles:
            sid = self.runtime.extract_session_id(handle.log_path)
            if sid:
                sessions[handle.agent_id] = sid
            handle.stop()

        if self.verbose:
            print(f"[coral] Warm-start: research complete. {len(sessions)} session(s) captured.\n")
        logger.info(f"Warm-start: research complete. {len(sessions)} session(s) captured.")

        return sessions

    def _setup_and_start_agent(
        self, agent_id: str,
        resume_session_id: str | None = None,
        prompt: str | None = None,
        prompt_source: str | None = None,
        max_turns: int | None = None,
    ) -> AgentHandle:
        """Set up a single agent and start it."""
        assert self.paths is not None

        # Create worktree (idempotent)
        logger.info(f"Setting up {agent_id}...")
        worktree_path = create_agent_worktree(
            self.paths.repo_dir, agent_id, self.paths.agents_dir,
        )
        logger.info(f"  Worktree: {worktree_path}")

        # Set up .gitignore for CORAL files
        setup_gitignore(worktree_path)

        # Run setup commands (uv sync, etc.) and install coral in the worktree
        setup_worktree_env(worktree_path, self.config.workspace.setup)

        # Write .coral_dir breadcrumb (used by workspace guard hook)
        write_coral_dir(worktree_path, self.paths.coral_dir)

        # Set up shared state directory (notes, skills, attempts symlinks)
        shared_dir_name = self.runtime.shared_dir_name
        setup_shared_state(worktree_path, self.paths.coral_dir, shared_dir_name)

        # Register agent with gateway if active (before settings so we have the key)
        if self._gateway and agent_id not in self._gateway_keys:
            proxy_key = self._gateway.register_agent(agent_id, worktree_path)
            self._gateway_keys[agent_id] = proxy_key

        gateway_url = self._gateway.url if self._gateway else None
        gateway_api_key = self._gateway_keys.get(agent_id)

        # Runtime-specific: write permission settings per worktree
        if shared_dir_name == ".claude":
            setup_claude_settings(
                worktree_path, coral_dir=self.paths.coral_dir,
                research=self.config.agents.research,
                gateway_url=gateway_url,
                gateway_api_key=gateway_api_key,
            )
        elif shared_dir_name == ".opencode":
            setup_opencode_settings(
                worktree_path, coral_dir=self.paths.coral_dir,
                research=self.config.agents.research,
                gateway_url=gateway_url,
                gateway_api_key=gateway_api_key,
            )
        elif shared_dir_name == ".codex":
            setup_codex_settings(
                worktree_path, coral_dir=self.paths.coral_dir,
                research=self.config.agents.research,
                gateway_url=gateway_url,
                gateway_api_key=gateway_api_key,
            )

        # Seed local heartbeat config from task YAML if not already present
        if not read_agent_heartbeat(self.paths.coral_dir, agent_id):
            write_agent_heartbeat(self.paths.coral_dir, agent_id, default_local_actions(self.config))
            logger.info(f"  Seeded heartbeat config for {agent_id}")

        # Write agent ID
        write_agent_id(worktree_path, agent_id)

        # Generate instruction file (CLAUDE.md, AGENTS.md, etc.)
        instruction_file = self.runtime.instruction_filename
        single_agent = self.config.agents.count == 1
        coral_md = generate_coral_md(
            self.config, agent_id,
            single_agent=single_agent,
            shared_dir=shared_dir_name,
        )
        (worktree_path / instruction_file).write_text(coral_md)

        # Start agent
        handle = self.runtime.start(
            worktree_path=worktree_path,
            coral_md_path=worktree_path / instruction_file,
            model=self.config.agents.model,
            runtime_options=self.config.agents.runtime_options,
            max_turns=max_turns if max_turns is not None else self.config.agents.max_turns,
            verbose=self.verbose,
            log_dir=self.paths.coral_dir / "public" / "logs",
            resume_session_id=resume_session_id,
            prompt=prompt,
            prompt_source=prompt_source,
            task_name=self.config.task.name,
            task_description=self.config.task.description,
            gateway_url=gateway_url,
            gateway_api_key=gateway_api_key,
        )
        # Record fresh process start time for the exit-classifier uptime check.
        self._started_at[agent_id] = time.time()
        return handle

    def _restart_agent(
        self, idx: int, prompt: str | None = None,
        prompt_source: str | None = None,
    ) -> AgentHandle:
        """Restart a dead agent, resuming its session with optional feedback prompt."""
        old_handle = self.handles[idx]
        agent_id = old_handle.agent_id
        self._restart_counts[agent_id] = self._restart_counts.get(agent_id, 0) + 1

        # Ensure old process and file handles are fully cleaned up
        old_handle.stop()

        # Check if the previous exit was a session-not-found error
        session_id: str | None = None
        if not _log_has_session_error(old_handle.log_path):
            # Try to extract session_id from the old log for resumption
            session_id = self.runtime.extract_session_id(old_handle.log_path)

        if session_id:
            logger.info(f"Resuming {agent_id} with session {session_id}")
        else:
            logger.info(f"Starting {agent_id} fresh (no session to resume)")

        return self._setup_and_start_agent(
            agent_id, resume_session_id=session_id, prompt=prompt,
            prompt_source=prompt_source or "restart",
        )

    def _interrupt_and_resume(
        self, idx: int, prompt: str,
        prompt_source: str | None = None,
    ) -> AgentHandle:
        """Interrupt a running agent and resume with a feedback prompt."""
        handle = self.handles[idx]
        agent_id = handle.agent_id

        # SIGINT the agent — Claude Code saves session gracefully
        session_id = handle.interrupt()
        self._restart_counts[agent_id] = self._restart_counts.get(agent_id, 0) + 1

        if session_id:
            logger.info(f"Interrupted {agent_id}, resuming session {session_id} with feedback")
        else:
            logger.warning(f"No session_id for {agent_id}, starting fresh")

        return self._setup_and_start_agent(
            agent_id, resume_session_id=session_id, prompt=prompt,
            prompt_source=prompt_source,
        )

    def resume_all(
        self,
        paths: ProjectPaths,
        instruction: str | None = None,
    ) -> list[AgentHandle]:
        """Resume agents into an existing run's worktrees."""
        self._start_time = datetime.now(UTC)
        self.paths = paths

        # Start gateway if configured
        self._start_gateway_if_enabled()

        # Start grader daemon (must be up before resumed agents submit evals).
        self._start_grader_daemon()

        # Kill any leftover agent processes from a previous run so they
        # don't hold session locks and block the new agents.
        self._kill_old_agent_processes()

        # Load saved sessions
        saved_sessions = self._load_saved_sessions()

        # Validate saved sessions by checking if they exist locally
        validated_sessions = _validate_sessions(saved_sessions, coral_dir=paths.coral_dir)

        # Discover agents from existing worktrees
        if not paths.agents_dir.is_dir():
            raise RuntimeError(f"No agents directory found at {paths.agents_dir}")

        agent_dirs = sorted(
            d for d in paths.agents_dir.iterdir() if d.is_dir()
        )
        if not agent_dirs:
            raise RuntimeError(f"No agent worktrees found in {paths.agents_dir}")

        fresh_start_prompt = (
            "Begin. This is a resumed run — previous work already exists. "
            "Before writing any code, review the current state:\n"
            "1. Run `coral log` to see the leaderboard\n"
            "2. Run `coral log --recent` to see recent activity\n"
            "3. Read notes in your shared directory (e.g. `.claude/notes/`)\n"
            "4. Check skills in your shared directory (e.g. `.claude/skills/`)\n"
            "5. Inspect top attempts with `coral show <hash>` to understand what's been tried\n\n"
            "Build on what worked. Don't duplicate prior efforts."
        )

        if instruction:
            fresh_start_prompt += f"\n\n## Additional Instructions\n{instruction}"

        handles = []
        for agent_dir in agent_dirs:
            agent_id = agent_dir.name
            session_id = validated_sessions.get(agent_id)

            # Fallback: extract from latest log file
            if not session_id:
                session_id = self._find_latest_session_from_logs(agent_id)
                # Validate this one too
                if session_id and not _session_exists(session_id, coral_dir=paths.coral_dir):
                    logger.info(
                        f"Session {session_id} for {agent_id} not found locally "
                        f"(different machine?), starting fresh"
                    )
                    session_id = None

            if session_id:
                logger.info(f"Resuming {agent_id} with session {session_id}")
                prompt = instruction if instruction else None  # None → runtime default
            else:
                logger.info(f"Starting {agent_id} fresh (no session to resume)")
                prompt = fresh_start_prompt

            handle = self._setup_and_start_agent(
                agent_id, resume_session_id=session_id, prompt=prompt,
            )
            handles.append(handle)

        self.handles = handles
        self._running = True
        self._write_pid_file()
        atexit.register(self._atexit_cleanup)
        return handles

    def _save_sessions(self) -> None:
        """Persist agent session IDs to sessions.json for later resume."""
        if not self.paths:
            return
        sessions: dict[str, str] = {}
        for handle in self.handles:
            sid = handle.session_id
            if not sid:
                sid = self.runtime.extract_session_id(handle.log_path)
            if sid:
                sessions[handle.agent_id] = sid
        sessions_file = self.paths.coral_dir / "public" / "sessions.json"
        sessions_file.write_text(json.dumps(sessions, indent=2))
        logger.info(f"Saved {len(sessions)} session ID(s) to sessions.json")

    def _load_saved_sessions(self) -> dict[str, str]:
        """Load saved session IDs from sessions.json."""
        if not self.paths:
            return {}
        sessions_file = self.paths.coral_dir / "public" / "sessions.json"
        if sessions_file.exists():
            try:
                return json.loads(sessions_file.read_text())
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read sessions.json: {e}")
        return {}

    def _find_latest_session_from_logs(self, agent_id: str) -> str | None:
        """Extract session ID from the most recent log file for an agent."""
        if not self.paths:
            return None
        logs_dir = self.paths.coral_dir / "public" / "logs"
        if not logs_dir.exists():
            return None
        logs = sorted(
            logs_dir.glob(f"{agent_id}.*.log"),
            key=lambda p: p.stat().st_mtime,
        )
        if logs:
            return self.runtime.extract_session_id(logs[-1])
        return None

    def stop_all(self) -> None:
        """Gracefully stop all agents.

        Uses SIGINT first so Claude Code can save sessions for later resume,
        then falls back to SIGTERM/SIGKILL if needed.
        """
        if self._stopping:
            return
        self._stopping = True
        self._running = False
        self._stop_event.set()
        # Save session IDs before killing processes
        self._save_sessions()
        for handle in self.handles:
            # Try graceful interrupt first so sessions can be resumed
            handle.interrupt()
        # Force-stop any that didn't exit
        for handle in self.handles:
            if handle.alive:
                handle.stop()
        self._cleanup_pid_file()
        # Stop grader daemon before the gateway so any in-flight grade can
        # finish its LLM call (if the grader uses the gateway).
        self._stop_grader_daemon()
        # Stop gateway after all agents are down
        if self._gateway:
            self._gateway.stop()
            self._gateway = None
        logger.info("All agents stopped.")

    def status(self) -> list[dict[str, Any]]:
        """Get status of all agents."""
        statuses = []
        for handle in self.handles:
            statuses.append({
                "agent_id": handle.agent_id,
                "alive": handle.alive,
                "pid": handle.process.pid if handle.process else None,
                "worktree": str(handle.worktree_path),
                "log": str(handle.log_path),
                "session_id": handle.session_id,
                "restarts": self._restart_counts.get(handle.agent_id, 0),
            })
        return statuses

    def grader_daemon_alive(self) -> bool:
        """Whether the grader daemon subprocess is currently running."""
        proc = self._grader_proc
        return bool(proc and proc.is_alive())

    def _get_seen_attempts(self) -> set[str]:
        """Get the set of attempt filenames currently in .coral/public/attempts/."""
        assert self.paths is not None
        attempts_dir = self.paths.coral_dir / "public" / "attempts"
        if not attempts_dir.exists():
            return set()
        return {f.name for f in attempts_dir.glob("*.json")}

    def _filter_scored(self, new_files: set[str]) -> set[str]:
        """Return only those filenames whose attempt status is not 'pending'.

        Pending attempts are grader-in-progress: the monitor loop must skip
        them (not trigger heartbeat, not advance plateau counters) until the
        grader daemon finalizes them. Malformed files are also skipped and
        will be retried next tick.
        """
        assert self.paths is not None
        attempts_dir = self.paths.coral_dir / "public" / "attempts"
        scored: set[str] = set()
        for fname in new_files:
            path = attempts_dir / fname
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                # Transient read (e.g. mid-rename on some filesystems) — retry next tick.
                continue
            status = data.get("status")
            if status and status != "pending":
                scored.add(fname)
        return scored

    def _read_latest_attempt(
        self, new_files: set[str], agent_id: str | None = None
    ) -> dict[str, Any] | None:
        """Read the most recent attempt from a set of new attempt filenames.

        When `agent_id` is provided, only attempts owned by that agent are
        considered. This prevents cross-agent score leakage when building a
        resume prompt for a dying agent in multi-agent runs.
        """
        assert self.paths is not None
        attempts_dir = self.paths.coral_dir / "public" / "attempts"
        newest_path: Path | None = None
        newest_data: dict[str, Any] | None = None
        newest_mtime = 0.0
        for fname in new_files:
            path = attempts_dir / fname
            if not path.exists():
                continue
            mtime = path.stat().st_mtime
            if mtime <= newest_mtime:
                continue
            if agent_id is not None:
                # When filtering, we have to read each candidate to inspect
                # its agent_id field; cache the parse so we do not re-read.
                try:
                    data = json.loads(path.read_text())
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning(f"Failed to read attempt {path}: {e}")
                    continue
                if data.get("agent_id") != agent_id:
                    continue
                newest_mtime = mtime
                newest_path = path
                newest_data = data
            else:
                newest_mtime = mtime
                newest_path = path
                newest_data = None  # parse lazily below
        if newest_data is not None:
            return newest_data
        if newest_path is not None:
            try:
                return json.loads(newest_path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read attempt {newest_path}: {e}")
        return None

    def _get_eval_count(self) -> int:
        """Read the current eval count from .coral/eval_count."""
        assert self.paths is not None
        counter_file = self.paths.coral_dir / "public" / "eval_count"
        if counter_file.exists():
            try:
                return int(counter_file.read_text().strip())
            except ValueError:
                pass
        return 0

    def _get_heartbeat_runner(self, agent_id: str) -> HeartbeatRunner:
        """Build a HeartbeatRunner by merging local + global heartbeat configs."""
        from coral.agent.heartbeat import HeartbeatAction

        assert self.paths is not None
        shared_dir = self.runtime.shared_dir_name

        local_actions = read_agent_heartbeat(self.paths.coral_dir, agent_id)
        global_actions = read_global_heartbeat(self.paths.coral_dir)

        heartbeat_actions = []
        for ad in local_actions:
            prompt_template = ad.get("prompt") or DEFAULT_PROMPTS.get(ad["name"], "")
            prompt = prompt_template.format(shared_dir=shared_dir, agent_id=agent_id) if prompt_template else ""
            trigger = ad.get("trigger") or DEFAULT_TRIGGER.get(ad["name"], "interval")
            heartbeat_actions.append(HeartbeatAction(
                name=ad["name"], every=ad["every"], prompt=prompt, is_global=False,
                trigger=trigger,
            ))
        for ad in global_actions:
            prompt_template = ad.get("prompt") or DEFAULT_PROMPTS.get(ad["name"], "")
            prompt = prompt_template.format(shared_dir=shared_dir, agent_id=agent_id) if prompt_template else ""
            trigger = ad.get("trigger") or DEFAULT_TRIGGER.get(ad["name"], "interval")
            heartbeat_actions.append(HeartbeatAction(
                name=ad["name"], every=ad["every"], prompt=prompt, is_global=True,
                trigger=trigger,
            ))
        return HeartbeatRunner(heartbeat_actions)

    def _is_paused(self, agent_id: str) -> bool:
        """Return True if the agent is currently in PAUSED state.

        On expiry the deadline is cleared, the crash window is reset (so a
        single fresh exit cannot retrigger the breaker), and the agent is
        marked for an unconditional one-shot restart on the next dead-agent
        observation. This avoids re-classifying the same dead handle and
        double-counting the exit that originally triggered the pause.
        """
        until = self._paused_until.get(agent_id)
        if until is None:
            return False
        if time.time() >= until:
            self._paused_until.pop(agent_id, None)
            self._crash_history.pop(agent_id, None)
            self._pending_restart_after_pause.add(agent_id)
            self._persist_agent_state()
            logger.info(f"Agent {agent_id} pause expired; eligible for restart")
            return False
        return True

    def _classify_agent_exit(
        self, agent_id: str, log_path: Path, exit_code: int | None
    ) -> str:
        """Dispatch to the runtime's classifier with the manager's uptime view."""
        started = self._started_at.get(agent_id)
        uptime = time.time() - started if started is not None else None
        min_clean = self.config.agents.min_clean_runtime_seconds
        runtime = self.runtime
        if hasattr(runtime, "classify_exit"):
            try:
                return runtime.classify_exit(
                    log_path, exit_code, uptime,
                    min_clean_runtime_seconds=min_clean,
                )
            except Exception as e:
                logger.warning(
                    f"runtime.classify_exit raised for {agent_id}: {e}; "
                    f"falling back to uptime heuristic"
                )
        return classify_by_uptime(exit_code, uptime, min_clean)

    def _record_crash(
        self,
        agent_id: str,
        exit_code: int | None,
        log_path: Path,
        classification: str,
    ) -> None:
        """Append a non-clean exit event and prune entries outside the window.

        When the breaker is disabled (any knob == 0) we do not even allocate
        history: the breaker cannot fire, so accumulating events would just
        leak memory across an overnight run.
        """
        if not self._breaker_enabled():
            return
        history = self._crash_history.setdefault(agent_id, deque(maxlen=64))
        history.append(
            RestartEvent(
                timestamp=time.time(),
                exit_code=exit_code,
                log_path=str(log_path),
                classification=classification,
            )
        )
        cutoff = time.time() - self.config.agents.restart_burst_window
        while history and history[0].timestamp < cutoff:
            history.popleft()

    def _breaker_enabled(self) -> bool:
        """Return True iff all three breaker knobs are positive (>0).

        Setting any of `restart_burst_threshold`, `restart_burst_window`, or
        `restart_pause_seconds` to 0 disables the breaker entirely, matching
        the `agents.timeout=0`-disables-the-stall-watchdog convention.
        """
        cfg = self.config.agents
        return (
            cfg.restart_burst_threshold > 0
            and cfg.restart_burst_window > 0
            and cfg.restart_pause_seconds > 0
        )

    def _should_pause_for_burst(self, agent_id: str) -> bool:
        """Return True iff the recent crash count meets the configured threshold."""
        if not self._breaker_enabled():
            return False
        history = self._crash_history.get(agent_id)
        if not history:
            return False
        return len(history) >= self.config.agents.restart_burst_threshold

    def _enter_paused(self, agent_id: str, log_path: Path) -> None:
        """Transition the agent into PAUSED, dump fault evidence, persist state."""
        pause_seconds = self.config.agents.restart_pause_seconds
        self._paused_until[agent_id] = time.time() + pause_seconds
        self._pause_count[agent_id] = self._pause_count.get(agent_id, 0) + 1
        fault_at = self._dump_fault_log(agent_id, log_path)
        if fault_at:
            self._last_fault_at[agent_id] = fault_at
        self._persist_agent_state()
        burst_count = len(self._crash_history.get(agent_id, []))
        logger.warning(
            f"Agent {agent_id} entered PAUSED for {pause_seconds}s after "
            f"{burst_count} crashes within {self.config.agents.restart_burst_window}s. "
            f"Fault dump under public/diagnostics/{agent_id}/fault.log"
        )
        if self.verbose:
            print(
                f"[coral] {agent_id} PAUSED ({pause_seconds}s) — "
                f"see public/diagnostics/{agent_id}/fault.log"
            )

    def _dump_fault_log(self, agent_id: str, log_path: Path) -> str | None:
        """Write a fault dump under public/diagnostics/<agent_id>/fault.log.

        The file is overwritten on each pause cycle so stale data does not
        linger. Returns the ISO-8601 timestamp of the dump on success, or
        None if the dump could not be written.
        """
        assert self.paths is not None
        diag_dir = self.paths.coral_dir / "public" / "diagnostics" / agent_id
        try:
            diag_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create diagnostics dir for {agent_id}: {e}")
            return None
        fault_path = diag_dir / "fault.log"
        now_iso = datetime.now(UTC).isoformat()
        history = list(self._crash_history.get(agent_id, []))
        try:
            with open(fault_path, "w", encoding="utf-8") as f:
                f.write(f"# Fault dump for {agent_id}\n")
                f.write(f"# Written: {now_iso}\n")
                f.write(f"# Pause cycle #{self._pause_count.get(agent_id, 0)}\n")
                f.write(f"# Burst window: {self.config.agents.restart_burst_window}s\n")
                f.write(f"# Burst threshold: {self.config.agents.restart_burst_threshold}\n")
                f.write("# Recent crash events (oldest first):\n")
                for ev in history:
                    ev_iso = datetime.fromtimestamp(ev.timestamp, UTC).isoformat()
                    f.write(
                        f"#   {ev_iso} exit_code={ev.exit_code} "
                        f"classification={ev.classification} log={ev.log_path}\n"
                    )
                f.write("#\n")
                f.write(f"# --- Last 200 lines of {log_path} ---\n")
                try:
                    tail: deque[str] = deque(maxlen=200)
                    with open(log_path, encoding="utf-8", errors="replace") as src:
                        for line in src:
                            tail.append(line)
                    f.writelines(tail)
                except OSError as e:
                    f.write(f"# (could not read agent log: {e})\n")
                # Append the per-agent stderr tail when available — typically
                # this is where startup-time crash messages land for runtimes
                # that emit nothing useful to the stream-json log.
                err_path = (
                    self.paths.coral_dir / "public" / "diagnostics" / agent_id / "agent.err"
                )
                if err_path.exists():
                    f.write(f"#\n# --- Last 100 lines of {err_path} ---\n")
                    try:
                        err_tail: deque[str] = deque(maxlen=100)
                        with open(err_path, encoding="utf-8", errors="replace") as src:
                            for line in src:
                                err_tail.append(line)
                        f.writelines(err_tail)
                    except OSError as e:
                        f.write(f"# (could not read stderr capture: {e})\n")
            return now_iso
        except OSError as e:
            logger.error(f"Failed to write fault dump for {agent_id}: {e}")
            return None

    def _grader_alive(self) -> bool:
        """Return True iff the grader daemon multiprocessing.Process is alive.

        We use the live process handle the manager already owns
        (`self._grader_proc`) rather than the on-disk
        `<coral_dir>/public/grader_daemon_heartbeat` file. The heartbeat file
        is only refreshed in the daemon's idle path and around each grade
        attempt; during a long-running grade subprocess the file's mtime can
        drift past any reasonable freshness threshold. The live process check
        is both stricter (catches a daemon that died mid-grade) and looser
        on the only axis that matters (does not falsely report dead during a
        healthy long grade).
        """
        proc = self._grader_proc
        if proc is None:
            return False
        try:
            return bool(proc.is_alive())
        except Exception:
            return False

    def _attempt_age_seconds(self, timestamp_iso: str) -> float | None:
        """Return age in seconds of an attempt's ISO timestamp, or None on parse failure."""
        try:
            ts = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return (datetime.now(UTC) - ts).total_seconds()

    def _persist_agent_state(self) -> None:
        """Persist current paused/active state to public/agent_state.json."""
        if self.paths is None:
            return
        document = AgentStateDocument()
        for handle in self.handles:
            agent_id = handle.agent_id
            until = self._paused_until.get(agent_id)
            state = "paused" if until is not None else "active"
            document.agents[agent_id] = AgentRuntimeState(
                state=state,
                paused_until=until,
                pause_count=self._pause_count.get(agent_id, 0),
                last_fault_at=self._last_fault_at.get(agent_id),
            )
        try:
            write_agent_state(self.paths.coral_dir, document)
        except OSError as e:
            logger.error(f"Failed to persist agent_state.json: {e}")

    def _build_score_prompt(self, attempt: dict[str, Any], eval_count: int) -> str:
        """Build a resume prompt with just the eval results (no reflection)."""
        score = attempt.get("score")
        score_str = f"{score:.10f}" if score is not None else "FAILED"
        commit = attempt.get("commit_hash", "unknown")[:12]
        feedback = attempt.get("feedback", "")
        title = attempt.get("title", "")

        lines = [
            f"Eval #{eval_count}: score={score_str} (commit {commit})",
            f"What you did: {title}",
        ]
        if feedback:
            lines.append(f"Feedback: {feedback}")
        lines.append("")
        lines.append("Continue optimizing.")
        return "\n".join(lines)

    def monitor_loop(self, check_interval: int = 5) -> None:
        """Monitor agents, deliver eval feedback via --resume, auto-restart.

        Watches .coral/attempts/ for new attempt files. When a new attempt appears
        and it's a reflection point, interrupts the agent and resumes with a
        feedback + reflection prompt. Otherwise, lets the agent continue; if it
        dies (max-turns), resumes with a score summary.
        """
        def _signal_handler(sig: int, frame: Any) -> None:
            if self._stopping:
                # Second Ctrl+C: force immediate exit
                logger.warning("Force exit (second signal)")
                for handle in self.handles:
                    if handle.process and handle.alive:
                        try:
                            os.killpg(os.getpgid(handle.process.pid), signal.SIGKILL)
                        except (ProcessLookupError, PermissionError):
                            try:
                                handle.process.kill()
                            except Exception:
                                pass
                self._cleanup_pid_file()
                os._exit(1)
            logger.info(f"Received signal {sig}, shutting down...")
            self.stop_all()

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        # Only mark already-scored attempts as "seen" at startup. Pending
        # attempts left over from a previous manager (still in the grader
        # queue or mid-grade when we came up) need to flow through the
        # normal new-attempts path so heartbeat fires for them when they
        # transition to scored. Without this, anything pending at the
        # moment of a `coral resume` would silently bypass the per-eval
        # interrupt-and-resume cycle for the rest of the run.
        seen_attempts = self._filter_scored(self._get_seen_attempts())

        logger.info(f"Monitoring {len(self.handles)} agent(s) (check every {check_interval}s)...")

        while self._running:
            # Check for new attempts
            current_attempts = self._get_seen_attempts()
            new_attempts = current_attempts - seen_attempts

            # Pending attempts (grader daemon hasn't scored them yet) are kept
            # on the re-check list — we neither mark them as seen nor trigger
            # heartbeat until they transition to a terminal status.
            scored_new = self._filter_scored(new_attempts)
            seen_attempts = seen_attempts | scored_new

            if scored_new:
                attempt_data = self._read_latest_attempt(scored_new)

                if attempt_data:
                    committing_agent_id = attempt_data.get("agent_id")
                    if not committing_agent_id:
                        continue

                    # Increment per-agent eval count
                    self._agent_eval_counts[committing_agent_id] = (
                        self._agent_eval_counts.get(committing_agent_id, 0) + 1
                    )
                    agent_eval_count = self._agent_eval_counts[committing_agent_id]
                    global_eval_count = self._get_eval_count()

                    # Track plateau state (evals since personal-best improvement)
                    score = attempt_data.get("score")
                    minimize = self.config.grader.direction == "minimize"
                    if score is not None:
                        prev_best = self._agent_best_scores.get(committing_agent_id)
                        improved = (
                            prev_best is None
                            or (minimize and score < prev_best)
                            or (not minimize and score > prev_best)
                        )
                        if improved:
                            self._agent_best_scores[committing_agent_id] = score
                            self._agent_evals_since_improvement[committing_agent_id] = 0
                        else:
                            self._agent_evals_since_improvement[committing_agent_id] = (
                                self._agent_evals_since_improvement.get(committing_agent_id, 0) + 1
                            )
                    else:
                        # Failed/crashed eval counts as non-improving
                        self._agent_evals_since_improvement[committing_agent_id] = (
                            self._agent_evals_since_improvement.get(committing_agent_id, 0) + 1
                        )

                    evals_since_improvement = self._agent_evals_since_improvement.get(
                        committing_agent_id, 0
                    )

                    # Check heartbeat actions
                    runner = self._get_heartbeat_runner(committing_agent_id)
                    actions = runner.check(
                        local_eval_count=agent_eval_count,
                        global_eval_count=global_eval_count,
                        evals_since_improvement=evals_since_improvement,
                    )
                    if not actions:
                        continue

                    # Find the committing agent's handle
                    committing_idx = None
                    for i, handle in enumerate(self.handles):
                        if handle.agent_id == committing_agent_id and handle.alive:
                            committing_idx = i
                            break
                    if committing_idx is None:
                        continue

                    # Build eval header + combined heartbeat prompts
                    score_str = f"{score:.10f}" if score is not None else "FAILED"
                    commit = attempt_data.get("commit_hash", "unknown")[:12]
                    feedback = attempt_data.get("feedback", "")
                    title = attempt_data.get("title", "")

                    header_lines = [
                        f"## Eval #{agent_eval_count} Results",
                        "",
                        f"Score: {score_str}",
                        f"Commit: {commit}",
                        f"What you did: {title}",
                    ]
                    if feedback:
                        header_lines.append(f"Feedback: {feedback}")
                    header_lines.append("")

                    prompts = ["\n".join(header_lines)]
                    action_names = [a.name for a in actions]
                    prompts.extend(a.prompt for a in actions if a.prompt)

                    combined_prompt = "\n\n".join(prompts)
                    names = ", ".join(action_names)
                    logger.info(
                        f"Heartbeat [{names}] (agent eval #{agent_eval_count}): "
                        f"interrupting {committing_agent_id}"
                    )
                    if self.verbose:
                        print(f"\n[coral] Agent eval #{agent_eval_count}: score={attempt_data.get('score', '?')}")
                        print(f"[coral] Interrupting {committing_agent_id} for {names}...\n")
                    self.handles[committing_idx] = self._interrupt_and_resume(
                        committing_idx, combined_prompt,
                        prompt_source=f"heartbeat:{names}",
                    )
                    self._write_agent_pids()

            # Check for dead agents (max-turns exit, crash, etc.)
            for i, handle in enumerate(self.handles):
                if not handle.alive and self._running:
                    agent_id = handle.agent_id

                    # Honor an active PAUSED window: skip the restart entirely
                    # until the cooldown deadline passes.
                    if self._is_paused(agent_id):
                        continue

                    # Just-expired pause: restart without re-classifying. The
                    # exit that triggered the pause was already counted; the
                    # crash window was cleared on expiry, so a single fresh
                    # exit on the new process cannot retrigger the breaker.
                    if agent_id in self._pending_restart_after_pause:
                        self._pending_restart_after_pause.discard(agent_id)
                        count = self._restart_counts.get(agent_id, 0) + 1
                        eval_count = self._get_eval_count()
                        latest = self._read_latest_attempt(current_attempts, agent_id=agent_id)
                        prompt = self._build_score_prompt(latest, eval_count) if latest else None
                        logger.warning(
                            f"Agent {agent_id} restarting after pause cooldown "
                            f"(restart #{count})"
                        )
                        if self.verbose:
                            print(f"[coral] {agent_id} resuming after pause cooldown")
                        self.handles[i] = self._restart_agent(
                            i, prompt=prompt, prompt_source="post-pause"
                        )
                        self._write_agent_pids()
                        continue

                    exit_code = handle.process.returncode if handle.process else None
                    log_path = handle.log_path

                    # Classify the exit. Only non-clean exits feed the breaker;
                    # clean `max_turns`-style completions never trip it.
                    classification = self._classify_agent_exit(agent_id, log_path, exit_code)
                    if classification != "clean":
                        self._record_crash(agent_id, exit_code, log_path, classification)
                        if self._should_pause_for_burst(agent_id):
                            self._enter_paused(agent_id, log_path)
                            self._write_agent_pids()
                            continue

                    count = self._restart_counts.get(agent_id, 0) + 1

                    # Build resume prompt from this agent's own latest attempt
                    # so multi-agent runs do not feed cross-agent feedback.
                    eval_count = self._get_eval_count()
                    latest = self._read_latest_attempt(current_attempts, agent_id=agent_id)
                    if latest:
                        prompt = self._build_score_prompt(latest, eval_count)
                    else:
                        prompt = None

                    logger.warning(
                        f"Agent {agent_id} exited "
                        f"(code: {exit_code}, classification: {classification}), "
                        f"restart #{count}"
                    )
                    if self.verbose:
                        print(
                            f"[coral] {agent_id} exited "
                            f"(code: {exit_code}, {classification}), resuming..."
                        )
                    self.handles[i] = self._restart_agent(i, prompt=prompt)
                    self._write_agent_pids()

            # Check for stalled agents (alive but no output for > timeout).
            # `agents.timeout == 0` disables the watchdog entirely.
            stall_threshold = self.config.agents.timeout
            if stall_threshold > 0:
                # Cache pending attempts and the grader liveness once per tick
                # so per-agent exemption checks do not rescan the attempts dir.
                attempts_cache = read_attempts(self.paths.coral_dir)
                grader_alive = self._grader_alive()

                for i, handle in enumerate(self.handles):
                    if handle.alive and self._running:
                        try:
                            age = time.time() - handle.log_path.stat().st_mtime
                        except OSError:
                            continue
                        if age <= stall_threshold:
                            continue

                        # Grader-queue exemption: an agent that just submitted
                        # an attempt is silent because the grader is working,
                        # not because it deadlocked. Skip the stall check
                        # only when the grader process is alive AND the
                        # pending attempt has not aged past the cap (so a
                        # forgotten pending file cannot mask a true hang).
                        if grader_alive:
                            pending = agent_in_grader_queue(
                                self.paths.coral_dir, handle.agent_id, attempts_cache
                            )
                            if pending is not None:
                                pending_age = self._attempt_age_seconds(pending.timestamp)
                                if (
                                    pending_age is not None
                                    and pending_age <= self.config.agents.grader_pending_max_age
                                ):
                                    logger.info(
                                        f"Agent {handle.agent_id} silent for "
                                        f"{int(age)}s but pending attempt "
                                        f"{pending.commit_hash[:12]} is in grader queue "
                                        f"({int(pending_age)}s old); "
                                        f"stall check exempt"
                                    )
                                    continue

                        logger.warning(
                            f"Agent {handle.agent_id} stalled "
                            f"({int(age)}s since last output), restarting"
                        )
                        if self.verbose:
                            print(
                                f"[coral] {handle.agent_id} stalled "
                                f"({int(age)}s with no output), restarting..."
                            )
                        self.handles[i] = self._interrupt_and_resume(
                            i,
                            "You were automatically restarted because you "
                            "produced no output for an extended period. "
                            "Continue working on the task.",
                            prompt_source="timeout",
                        )
                        self._write_agent_pids()

            # Interruptible sleep
            if self._stop_event.wait(timeout=check_interval):
                break

    def wait_for_completion(self) -> None:
        """Single-agent verbose mode: watch for attempts and deliver feedback via --resume."""
        self.monitor_loop(check_interval=3)

    def _kill_old_agent_processes(self) -> None:
        """Kill leftover agent processes from a previous run.

        When resuming, old claude processes may still hold session locks,
        preventing new agents from resuming those sessions.  We send
        SIGINT first so Claude Code can save the session gracefully,
        then escalate to SIGKILL if needed.
        """
        if not self.paths:
            return
        agent_pids_file = self.paths.coral_dir / "public" / "agent.pids"
        if not agent_pids_file.exists():
            return
        import time

        pids = []
        for line in agent_pids_file.read_text().strip().splitlines():
            line = line.strip()
            if line:
                pids.append(int(line))

        if not pids:
            return

        # SIGINT first for graceful session save
        for pid in pids:
            try:
                os.kill(pid, signal.SIGINT)
                logger.info(f"Sent SIGINT to leftover agent process {pid}")
            except (ProcessLookupError, PermissionError):
                pass

        # Wait for graceful exit
        time.sleep(3)

        # Force kill any survivors
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
                logger.info(f"Force-killed leftover agent process {pid}")
            except (ProcessLookupError, PermissionError):
                pass

    def _write_pid_file(self) -> None:
        if self.paths:
            pid_file = self.paths.coral_dir / "public" / "manager.pid"
            pid_file.write_text(str(os.getpid()))
            # Also write agent PIDs so coral stop can kill them as fallback
            self._write_agent_pids()

    def _write_agent_pids(self) -> None:
        """Write agent PIDs to file for fallback cleanup by coral stop."""
        if self.paths:
            agent_pids_file = self.paths.coral_dir / "public" / "agent.pids"
            pids = []
            pid_map = {}
            for handle in self.handles:
                if handle.process and handle.process.pid:
                    pids.append(str(handle.process.pid))
                    pid_map[handle.agent_id] = handle.process.pid
            agent_pids_file.write_text("\n".join(pids))
            # Also write JSON mapping for the web UI to check process liveness
            pid_map_file = self.paths.coral_dir / "public" / "agent_pids.json"
            pid_map_file.write_text(json.dumps(pid_map))

    def _atexit_cleanup(self) -> None:
        """Safety net: kill any surviving agent processes on interpreter exit."""
        self._save_sessions()
        for handle in self.handles:
            if handle.process and handle.alive:
                try:
                    os.killpg(os.getpgid(handle.process.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    try:
                        handle.process.kill()
                    except Exception:
                        pass
        # Kill grader daemon too if still running.
        proc = self._grader_proc
        if proc is not None and proc.is_alive():
            try:
                proc.kill()
            except Exception:
                pass
        if self._gateway:
            self._gateway.stop()
            self._gateway = None
        self._cleanup_pid_file()

    def _cleanup_pid_file(self) -> None:
        if self.paths:
            for name in ("manager.pid", "agent.pids", "agent_pids.json"):
                f = self.paths.coral_dir / "public" / name
                if f.exists():
                    f.unlink()


def _session_exists(session_id: str, coral_dir: Path | None = None) -> bool:
    """Check if a Claude Code session exists locally.

    Checks the CORAL sessions dir first (sessions stored with results via
    CLAUDE_CONFIG_DIR), then falls back to the default Claude Code locations.
    """
    # Check CORAL sessions dir (stored with results, portable across machines)
    if coral_dir:
        sessions_dir = coral_dir / "public" / "sessions"
        if sessions_dir.exists():
            for project_dir in sessions_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                if (project_dir / f"{session_id}.jsonl").exists():
                    return True

    # Check default Claude Code locations
    for base in [
        Path.home() / ".config" / "claude" / "projects",
        Path.home() / ".claude" / "projects",
    ]:
        if not base.exists():
            continue
        for project_dir in base.iterdir():
            if not project_dir.is_dir():
                continue
            if (project_dir / f"{session_id}.jsonl").exists():
                return True
    return False


def _validate_sessions(
    sessions: dict[str, str], coral_dir: Path | None = None,
) -> dict[str, str]:
    """Filter saved sessions to only those that exist locally."""
    if not sessions:
        return {}
    validated = {}
    for agent_id, session_id in sessions.items():
        if _session_exists(session_id, coral_dir=coral_dir):
            validated[agent_id] = session_id
        else:
            logger.info(
                f"Session {session_id} for {agent_id} not found locally "
                f"(different machine?), will start fresh"
            )
    return validated
