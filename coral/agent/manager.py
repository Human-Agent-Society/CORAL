"""Spawn N agents, monitor health, auto-resume with eval feedback."""

from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coral.agent.heartbeat import HeartbeatRunner
from coral.agent.registry import get_runtime
from coral.agent.runtime import AgentHandle, AgentRuntime
from coral.config import CoralConfig
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
    setup_opencode_settings,
    setup_gitignore,
    setup_shared_state,
    setup_worktree_env,
    write_agent_id,
    write_coral_dir,
)

logger = logging.getLogger(__name__)


class AgentManager:
    """Manage the lifecycle of multiple CORAL agents."""

    def __init__(self, config: CoralConfig, verbose: bool = False, config_dir: Path | None = None) -> None:
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
        self._gateway: Any | None = None
        self._gateway_keys: dict[str, str] = {}  # agent_id -> proxy key

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

        # 2. Seed global heartbeat config if not already present
        if not read_global_heartbeat(self.paths.coral_dir):
            write_global_heartbeat(self.paths.coral_dir, default_global_actions(self.config))
            logger.info("Seeded global heartbeat config")

        # 3. For each agent: create worktree, generate CLAUDE.md, spawn runtime
        handles = []
        for i in range(self.config.agents.count):
            agent_id = f"agent-{i + 1}"
            if i > 0 and self.config.agents.stagger_seconds > 0:
                logger.info(f"Staggering {agent_id} by {self.config.agents.stagger_seconds}s")
                time.sleep(self.config.agents.stagger_seconds)
            handle = self._setup_and_start_agent(agent_id)
            handles.append(handle)

        self.handles = handles
        self._running = True

        # 4. Write PID file
        self._write_pid_file()

        # 5. Register atexit handler as safety net for unexpected exits
        atexit.register(self._atexit_cleanup)

        return handles

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

    def _setup_and_start_agent(
        self, agent_id: str,
        resume_session_id: str | None = None,
        prompt: str | None = None,
        prompt_source: str | None = None,
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

        # Runtime-specific: write permission settings per worktree
        if shared_dir_name == ".claude":
            setup_claude_settings(worktree_path, coral_dir=self.paths.coral_dir, research=self.config.agents.research)
        elif shared_dir_name == ".opencode":
            setup_opencode_settings(worktree_path, coral_dir=self.paths.coral_dir, research=self.config.agents.research)

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

        # Register agent with gateway if active
        if self._gateway and agent_id not in self._gateway_keys:
            proxy_key = self._gateway.register_agent(agent_id, worktree_path)
            self._gateway_keys[agent_id] = proxy_key

        # Start agent
        gateway_url = self._gateway.url if self._gateway else None
        gateway_api_key = self._gateway_keys.get(agent_id)
        handle = self.runtime.start(
            worktree_path=worktree_path,
            coral_md_path=worktree_path / instruction_file,
            model=self.config.agents.model,
            runtime_options=self.config.agents.runtime_options,
            max_turns=self.config.agents.max_turns,
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

    def resume_all(self, paths: ProjectPaths, instruction: str | None = None) -> list[AgentHandle]:
        """Resume agents into an existing run's worktrees."""
        self._start_time = datetime.now(UTC)
        self.paths = paths

        # Start gateway if configured
        self._start_gateway_if_enabled()

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

    def _get_seen_attempts(self) -> set[str]:
        """Get the set of attempt filenames currently in .coral/public/attempts/."""
        assert self.paths is not None
        attempts_dir = self.paths.coral_dir / "public" / "attempts"
        if not attempts_dir.exists():
            return set()
        return {f.name for f in attempts_dir.glob("*.json")}

    def _read_latest_attempt(self, new_files: set[str]) -> dict[str, Any] | None:
        """Read the most recent attempt from a set of new attempt filenames."""
        assert self.paths is not None
        attempts_dir = self.paths.coral_dir / "public" / "attempts"
        newest = None
        newest_mtime = 0.0
        for fname in new_files:
            path = attempts_dir / fname
            if path.exists():
                mtime = path.stat().st_mtime
                if mtime > newest_mtime:
                    newest_mtime = mtime
                    newest = path
        if newest:
            try:
                return json.loads(newest.read_text())
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read attempt {newest}: {e}")
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

        seen_attempts = self._get_seen_attempts()

        logger.info(f"Monitoring {len(self.handles)} agent(s) (check every {check_interval}s)...")

        while self._running:
            # Check for new attempts
            current_attempts = self._get_seen_attempts()
            new_attempts = current_attempts - seen_attempts

            if new_attempts:
                seen_attempts = current_attempts
                attempt_data = self._read_latest_attempt(new_attempts)

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
                    exit_code = handle.process.returncode if handle.process else None
                    count = self._restart_counts.get(handle.agent_id, 0) + 1

                    # Build resume prompt from latest attempt if available
                    eval_count = self._get_eval_count()
                    latest = self._read_latest_attempt(current_attempts)
                    if latest:
                        prompt = self._build_score_prompt(latest, eval_count)
                    else:
                        prompt = None

                    logger.warning(
                        f"Agent {handle.agent_id} exited (code: {exit_code}), "
                        f"restart #{count}"
                    )
                    if self.verbose:
                        print(f"[coral] {handle.agent_id} exited (code: {exit_code}), resuming...")
                    self.handles[i] = self._restart_agent(i, prompt=prompt)
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


def _log_has_session_error(log_path: Path) -> bool:
    """Check if a log file indicates a session-not-found error.

    This happens when resuming on a different machine where the Claude Code
    session doesn't exist.
    """
    try:
        content = log_path.read_text()
        return "No conversation found" in content
    except (OSError, UnicodeDecodeError):
        return False
