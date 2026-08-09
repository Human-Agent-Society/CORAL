"""Spawn N agents, monitor health, auto-resume with eval feedback."""

from __future__ import annotations

import atexit
import json
import logging
import multiprocessing
import os
import random
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coral.agent.assignments import (
    AgentSpec,
    partition_into_islands,
    resolve_agent_specs,
)
from coral.agent.exit_classifier import (
    classify_by_uptime,
)
from coral.agent.exit_classifier import (
    claude_code_log_has_session_error as _log_has_session_error,
)
from coral.agent.heartbeat import HeartbeatRunner
from coral.agent.migration import (
    IslandRoster,
    MigrationCandidate,
    MigrationResyncOp,
    MigrationRunner,
    choose_roster_balanced_subset,
)
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
from coral.hub._island import island_root
from coral.hub.attempts import (
    agent_in_grader_queue,
    archive_attempts,
    get_leaderboard,
    read_attempts,
    read_eval_count,
)
from coral.hub.auto_stop import write_auto_stop
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
from coral.hub.steering import ContinueFromAction, mark_applied, read_pending
from coral.template.coral_md import generate_coral_md
from coral.types import BUDGET_CLASS_REAL, Attempt, get_budget_class
from coral.workspace import (
    ProjectPaths,
    apply_runtime_mounts,
    create_agent_worktree,
    create_project,
    repoint_shared_state,
    seed_agent_role,
    setup_claude_settings,
    setup_codex_settings,
    setup_cursor_settings,
    setup_git_exclude,
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
        self,
        config: CoralConfig,
        verbose: bool = False,
        config_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.config_dir = config_dir
        base_specs = resolve_agent_specs(config)
        if config.islands.count > len(base_specs):
            raise ValueError(
                "islands.count cannot exceed the number of agents "
                f"(got islands.count={config.islands.count}, agents={len(base_specs)})"
            )
        self.specs: list[AgentSpec] = partition_into_islands(base_specs, count=config.islands.count)
        self.specs_by_id: dict[str, AgentSpec] = {s.agent_id: s for s in self.specs}
        self.runtimes: dict[str, AgentRuntime] = {
            s.agent_id: get_runtime(s.runtime) for s in self.specs
        }
        self.runtime: AgentRuntime = self.runtimes[self.specs[0].agent_id]
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
        self._agent_island: dict[str, str] = {
            s.agent_id: s.island_id for s in self.specs if s.island_id is not None
        }
        self._agent_score_history: dict[str, list[float | None]] = {}
        self._started_at: dict[str, float] = {}
        self._crash_history: dict[str, deque[RestartEvent]] = {}
        self._paused_until: dict[str, float] = {}
        self._pause_count: dict[str, int] = {}
        self._last_fault_at: dict[str, str] = {}
        self._pending_restart_after_pause: set[str] = set()
        self._gateway: Any | None = None
        self._gateway_keys: dict[str, str] = {}
        self._sandbox: Any | None = None
        self._grader_proc: multiprocessing.Process | None = None
        self._grader_stop_event: Any | None = None
        self._migration_runner: MigrationRunner = MigrationRunner(
            config.islands,
            minimize=(config.grader.direction == "minimize"),
            rng=random.Random(),
        )
        self._deferred_candidates: list[tuple[MigrationCandidate, str]] = []
        self._last_migrated_eval: dict[str, int] = {}

    def _runtime_for(self, agent_id: str) -> AgentRuntime:
        runtime = self.runtimes.get(agent_id)
        if runtime is None:
            runtime = self.runtime
            self.runtimes[agent_id] = runtime
        return runtime

    def _mounts_base_dir(self) -> Path:
        for candidate in (self.config.task_dir, self.config_dir):
            if candidate is not None:
                return Path(candidate)
        return Path.cwd()

    def start_all(self) -> list[AgentHandle]:
        """Create workspace structure and spawn all agents."""
        self._start_time = datetime.now(UTC)

        self.paths = create_project(self.config, config_dir=self.config_dir)
        logger.info(f"Run directory: {self.paths.run_dir}")
        logger.info(f"  coral_dir: {self.paths.coral_dir}")
        logger.info(f"  repo_dir:  {self.paths.repo_dir}")
        self._last_migrated_eval = _read_last_migrated_evals(self.paths.coral_dir)

        self._start_gateway_if_enabled()
        self._start_sandbox_if_enabled()
        self._start_grader_daemon()

        if self.config.islands.count > 1:
            for island_id in {s.island_id for s in self.specs if s.island_id is not None}:
                if not read_global_heartbeat(self.paths.coral_dir, island_id=island_id):
                    write_global_heartbeat(
                        self.paths.coral_dir,
                        default_global_actions(self.config),
                        island_id=island_id,
                    )
                    logger.info(f"Seeded global heartbeat config for island {island_id}")
        else:
            if not read_global_heartbeat(self.paths.coral_dir):
                write_global_heartbeat(self.paths.coral_dir, default_global_actions(self.config))
                logger.info("Seeded global heartbeat config")

        agent_ids = [s.agent_id for s in self.specs]
        warmstart = WarmStartRunner(self.config)
        research_sessions: dict[str, str] = {}

        if warmstart.enabled:
            research_sessions = self._run_warmstart_research(warmstart, agent_ids)

        handles = []
        for i, agent_id in enumerate(agent_ids):
            spec = self.specs_by_id.get(agent_id)
            island_id = spec.island_id if spec else None
            if i > 0 and self.config.agents.stagger_seconds > 0:
                logger.info(f"Staggering {agent_id} by {self.config.agents.stagger_seconds}s")
                time.sleep(self.config.agents.stagger_seconds)
            shared_dir = self._runtime_for(agent_id).shared_dir_name
            handle = self._setup_and_start_agent(
                agent_id,
                island_id=island_id,
                resume_session_id=research_sessions.get(agent_id),
                prompt=warmstart.main_prompt(shared_dir) if warmstart.enabled else None,
                prompt_source="warmstart:main" if warmstart.enabled else None,
            )
            handles.append(handle)

        self.handles = handles
        self._running = True

        self._write_pid_file()
        self._persist_agent_state()
        atexit.register(self._atexit_cleanup)

        return handles

    def _start_grader_daemon(self) -> None:
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")

        if self._grader_proc is not None and self._grader_proc.is_alive():
            return

        pid_file = self.paths.coral_dir / "public" / "grader_daemon.pid"
        if pid_file.exists():
            try:
                stale_pid = int(pid_file.read_text(encoding="utf-8").strip())
                os.kill(stale_pid, signal.SIGTERM)
                logger.info(f"Killed stale grader daemon PID {stale_pid}")
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                pass
            try:
                pid_file.unlink()
            except OSError:
                pass

        from coral.grader.daemon import run_daemon

        stop_event = multiprocessing.Event()
        proc = multiprocessing.Process(
            target=run_daemon,
            args=(str(self.paths.coral_dir), stop_event),
            name="coral-grader-daemon",
            daemon=False,
        )
        proc.start()
        self._grader_proc = proc
        self._grader_stop_event = stop_event
        try:
            pid_file.write_text(str(proc.pid), encoding="utf-8")
        except OSError:
            pass
        logger.info(f"Grader daemon started (PID {proc.pid})")
        if self.verbose:
            print(f"[coral] Grader daemon running (PID {proc.pid})")

    def _stop_grader_daemon(self, timeout: float = 10.0) -> None:
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
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")
        gw_cfg = self.config.agents.gateway
        if not gw_cfg.enabled:
            return

        from coral.gateway.config import generate_default_litellm_config
        from coral.gateway.server import GatewayManager

        config_path = gw_cfg.config
        if not config_path:
            config_path = str(self.paths.run_dir / "litellm_config.yaml")
            generate_default_litellm_config(
                Path(config_path),
                model=self.config.agents.model,
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

    def _start_sandbox_if_enabled(self) -> None:
        sb = self.config.agents.sandbox
        if not sb.enabled or self._sandbox is not None:
            return

        from coral.sandbox import get_sandbox_provider

        provider = get_sandbox_provider(sb)
        provider.validate(self.config.agents)
        provider.start()
        self._sandbox = provider
        logger.info(f"Sandbox provider {sb.provider!r} active")
        if self.verbose:
            print(f"[coral] Sandbox provider {sb.provider!r} active")

    def _stop_sandbox(self) -> None:
        if self._sandbox is not None:
            self._sandbox.stop()
            self._sandbox = None

    def _island_worktrees(self, agent_id: str) -> list[Path]:
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")

        def island_of(aid: str) -> str | None:
            spec = self.specs_by_id.get(aid)
            return self._agent_island.get(aid) or (spec.island_id if spec else None)

        own = island_of(agent_id)
        return [
            self.paths.agents_dir / s.agent_id for s in self.specs if island_of(s.agent_id) == own
        ]

    def _sandbox_spec_for(self, agent_id: str, worktree_path: Path, shared_dir_name: str):
        if self._sandbox is None:
            return None
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")

        from coral.sandbox import AgentSandboxContext

        spec = self._sandbox.prepare_agent(
            AgentSandboxContext(
                agent_id=agent_id,
                worktree_path=worktree_path,
                coral_dir=self.paths.coral_dir,
                repo_dir=self.paths.repo_dir,
                shared_dir_name=shared_dir_name,
                sibling_worktrees=self._island_worktrees(agent_id),
            )
        )
        logger.info(f"  {agent_id}: sandboxed via {self.config.agents.sandbox.provider!r}")
        return spec

    def _run_warmstart_research(
        self,
        warmstart: WarmStartRunner,
        agent_ids: list[str],
    ) -> dict[str, str]:
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")

        if self.verbose:
            print("\n[coral] Warm-start: research phase...\n")
        logger.info("Warm-start: starting research phase")

        research_handles = []
        for i, agent_id in enumerate(agent_ids):
            spec = self.specs_by_id.get(agent_id)
            island_id = spec.island_id if spec else None
            if i > 0 and self.config.agents.stagger_seconds > 0:
                time.sleep(self.config.agents.stagger_seconds)
            shared_dir = self._runtime_for(agent_id).shared_dir_name
            handle = self._setup_and_start_agent(
                agent_id,
                island_id=island_id,
                prompt=warmstart.research_prompt(shared_dir),
                prompt_source="warmstart:research",
            )
            research_handles.append(handle)

        warmstart.wait_for_research(research_handles)

        sessions: dict[str, str] = {}
        for handle in research_handles:
            sid = self._runtime_for(handle.agent_id).extract_session_id(handle.log_path)
            if sid:
                sessions[handle.agent_id] = sid
            handle.stop()

        if self.verbose:
            print(f"[coral] Warm-start: research complete. {len(sessions)} session(s) captured.\n")
        logger.info(f"Warm-start: research complete. {len(sessions)} session(s) captured.")

        return sessions

    def _setup_and_start_agent(
        self,
        agent_id: str,
        island_id: str | None = None,
        resume_session_id: str | None = None,
        prompt: str | None = None,
        prompt_source: str | None = None,
        max_turns: int | None = None,
    ) -> AgentHandle:
        """Set up a single agent workspace (if needed) and start its runtime process."""
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")

        runtime = self._runtime_for(agent_id)
        spec = self.specs_by_id.get(agent_id)

        if island_id is not None:
            self._agent_island[agent_id] = island_id

        logger.info(f"Setting up {agent_id}...")
        worktree_path = create_agent_worktree(
            self.paths.repo_dir,
            agent_id,
            self.paths.agents_dir,
        )

        setup_git_exclude(worktree_path)
        setup_worktree_env(worktree_path, self.config.workspace.setup)
        write_coral_dir(worktree_path, self.paths.coral_dir)

        shared_dir_name = runtime.shared_dir_name
        setup_shared_state(
            worktree_path,
            self.paths.coral_dir,
            shared_dir_name,
            island_id=island_id,
        )

        if self._gateway and agent_id not in self._gateway_keys:
            proxy_key = self._gateway.register_agent(agent_id, worktree_path)
            self._gateway_keys[agent_id] = proxy_key

        gateway_url = self._gateway.url if self._gateway else None
        gateway_api_key = self._gateway_keys.get(agent_id)

        if spec is not None:
            model = spec.model
            runtime_options = spec.runtime_options
        else:
            model = self.config.agents.model
            runtime_options = self.config.agents.runtime_options

        if shared_dir_name == ".claude":
            setup_claude_settings(
                worktree_path,
                coral_dir=self.paths.coral_dir,
                research=self.config.agents.research,
                gateway_url=gateway_url,
                gateway_api_key=gateway_api_key,
                island_id=island_id,
            )
        elif shared_dir_name == ".opencode":
            setup_opencode_settings(
                worktree_path,
                coral_dir=self.paths.coral_dir,
                research=self.config.agents.research,
                gateway_url=gateway_url,
                gateway_api_key=gateway_api_key,
                island_id=island_id,
            )
        elif shared_dir_name == ".codex":
            setup_codex_settings(
                worktree_path,
                coral_dir=self.paths.coral_dir,
                research=self.config.agents.research,
                gateway_url=gateway_url,
                gateway_api_key=gateway_api_key,
                island_id=island_id,
            )
        elif shared_dir_name == ".cursor":
            setup_cursor_settings(
                worktree_path,
                coral_dir=self.paths.coral_dir,
                research=self.config.agents.research,
                gateway_url=gateway_url,
                gateway_api_key=gateway_api_key,
                island_id=island_id,
            )

        mounts = (runtime_options or {}).get("mounts") or {}
        if mounts:
            apply_runtime_mounts(worktree_path, mounts, self._mounts_base_dir())

        if not read_agent_heartbeat(self.paths.coral_dir, agent_id, island_id=island_id):
            write_agent_heartbeat(
                self.paths.coral_dir,
                agent_id,
                default_local_actions(self.config),
                island_id=island_id,
            )

        write_agent_id(worktree_path, agent_id)

        role_file = (runtime_options or {}).get("role_file")
        seed_agent_role(
            self.paths.coral_dir,
            agent_id,
            source=role_file,
            base_dir=self._mounts_base_dir() if role_file else None,
            island_id=island_id,
        )

        instruction_file = runtime.instruction_filename
        single_agent = len(self.specs) == 1
        coral_md = generate_coral_md(
            self.config,
            agent_id,
            single_agent=single_agent,
            shared_dir=shared_dir_name,
            island_id=island_id,
        )
        (worktree_path / instruction_file).write_text(coral_md, encoding="utf-8")

        run_as_user = self._apply_user_isolation(worktree_path, island_id, shared_dir_name)
        sandbox_spec = self._sandbox_spec_for(agent_id, worktree_path, shared_dir_name)

        if island_id is not None:
            log_dir = self.paths.coral_dir / "islands" / str(island_id) / "logs"
        else:
            log_dir = self.paths.coral_dir / "public" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handle = runtime.start(
            worktree_path=worktree_path,
            coral_md_path=worktree_path / instruction_file,
            model=model,
            runtime_options=runtime_options,
            max_turns=max_turns if max_turns is not None else self.config.agents.max_turns,
            verbose=self.verbose,
            log_dir=log_dir,
            resume_session_id=resume_session_id,
            prompt=prompt,
            prompt_source=prompt_source,
            task_name=self.config.task.name,
            task_description=self.config.task.description,
            gateway_url=gateway_url,
            gateway_api_key=gateway_api_key,
            run_as_user=run_as_user,
            sandbox=sandbox_spec,
        )
        self._started_at[agent_id] = time.time()
        return handle

    def _apply_user_isolation(
        self,
        worktree_path: Path,
        island_id: str | int | None,
        shared_dir_name: str,
    ) -> dict | None:
        from coral.workspace import user_isolation as ui

        isolate_user = getattr(self.config.agents, "isolate_user", "")
        if not ui.is_enabled(isolate_user):
            return None

        spec = ui.resolve(isolate_user)
        ui.apply_ownership(
            worktree_path,
            self.paths.coral_dir,
            self.paths.repo_dir,
            spec,
            island_id=island_id,
        )
        home = ui.provision_home_state(spec, shared_dir_name)
        logger.info(
            "Agent workspace isolated as user %s (uid=%d); private/ locked to root",
            spec.name,
            spec.uid,
        )
        return {"name": spec.name, "uid": spec.uid, "gid": spec.gid, "home": home}

    def _restart_agent(
        self,
        idx: int,
        prompt: str | None = None,
        prompt_source: str | None = None,
    ) -> AgentHandle:
        old_handle = self.handles[idx]
        agent_id = old_handle.agent_id
        self._restart_counts[agent_id] = self._restart_counts.get(agent_id, 0) + 1

        old_handle.stop()

        session_id: str | None = None
        if not _log_has_session_error(old_handle.log_path):
            session_id = self._runtime_for(agent_id).extract_session_id(old_handle.log_path)

        if session_id:
            logger.info(f"Resuming {agent_id} with session {session_id}")
        else:
            logger.info(f"Starting {agent_id} fresh (no session to resume)")

        spec = self.specs_by_id.get(agent_id)
        island_id = self._agent_island.get(agent_id) or (spec.island_id if spec else None)

        return self._setup_and_start_agent(
            agent_id,
            island_id=island_id,
            resume_session_id=session_id,
            prompt=prompt,
            prompt_source=prompt_source or "restart",
        )

    def _interrupt_and_resume(
        self,
        idx: int,
        prompt: str,
        prompt_source: str | None = None,
        pre_restart_ops: Sequence[Callable[[str], None]] = (),
    ) -> AgentHandle:
        handle = self.handles[idx]
        agent_id = handle.agent_id

        handle.interrupt()
        session_id = self._runtime_for(agent_id).extract_session_id(handle.log_path)
        for op in pre_restart_ops:
            op(agent_id)
        self._restart_counts[agent_id] = self._restart_counts.get(agent_id, 0) + 1

        if session_id:
            logger.info(f"Interrupted {agent_id}, resuming session {session_id} with feedback")
        else:
            logger.warning(f"No session_id for {agent_id}, starting fresh")

        spec = self.specs_by_id.get(agent_id)
        island_id = self._agent_island.get(agent_id) or (spec.island_id if spec else None)

        return self._setup_and_start_agent(
            agent_id,
            island_id=island_id,
            resume_session_id=session_id,
            prompt=prompt,
            prompt_source=prompt_source,
        )

    def resume_all(
        self,
        paths: ProjectPaths,
        instruction: str | None = None,
        resume_from: str | None = None,
    ) -> list[AgentHandle]:
        """Resume agents into an existing run's worktrees."""
        self._start_time = datetime.now(UTC)
        self.paths = paths
        self._last_migrated_eval = _read_last_migrated_evals(paths.coral_dir)

        self._start_gateway_if_enabled()
        self._start_sandbox_if_enabled()
        self._start_grader_daemon()
        self._kill_old_agent_processes()

        saved_sessions = self._load_saved_sessions()
        validated_sessions = _validate_sessions(saved_sessions, coral_dir=paths.coral_dir)

        if not paths.agents_dir.is_dir():
            raise RuntimeError(f"No agents directory found at {paths.agents_dir}")

        agent_dirs = sorted(
            d for d in paths.agents_dir.iterdir() if d.is_dir() and (d / ".coral_agent_id").exists()
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

        resume_actions: list[ContinueFromAction] = []
        if resume_from:
            resume_actions.append(ContinueFromAction(hash=resume_from, instruction=""))
        resume_actions.extend(
            action
            for action in read_pending(paths.coral_dir)
            if isinstance(action, ContinueFromAction)
        )
        steering_by_agent: dict[str, ContinueFromAction] = {}
        applied_actions: set[str] = set()
        for action in resume_actions:
            matched = [
                agent_dir
                for agent_dir in agent_dirs
                if _worktree_head_descends_from(agent_dir, action.hash)
            ]
            if not matched:
                continue
            for agent_dir in matched:
                steering_by_agent[agent_dir.name] = action
            if action.id:
                applied_actions.add(action.id)

        for agent_dir in agent_dirs:
            action = steering_by_agent.get(agent_dir.name)
            if action is None:
                continue
            discarded = _discarded_commit_hashes(agent_dir, action.hash)
            _reset_worktree_to_commit(agent_dir, action.hash)
            if discarded:
                archived = archive_attempts(
                    paths.coral_dir,
                    discarded,
                    reason=f"discarded by resume --from {action.hash}",
                )
                if archived:
                    logger.info(
                        f"Archived {len(archived)} attempt(s) discarded by "
                        f"resume --from {action.hash} ({agent_dir.name})"
                    )

        handles = []
        for agent_dir in agent_dirs:
            agent_id = agent_dir.name
            session_id = validated_sessions.get(agent_id)
            steering_action = steering_by_agent.get(agent_id)

            island_bc = agent_dir / ".coral_island"
            island_id: str | None = None
            if island_bc.exists():
                try:
                    island_id = island_bc.read_text(encoding="utf-8").strip() or None
                except OSError:
                    island_id = None
            if island_id is not None:
                self._agent_island[agent_id] = island_id

            if not session_id:
                session_id = self._find_latest_session_from_logs(agent_id)
                if session_id and not _session_exists(session_id, coral_dir=paths.coral_dir):
                    logger.info(
                        f"Session {session_id} for {agent_id} not found locally "
                        f"(different machine?), starting fresh"
                    )
                    session_id = None

            if session_id:
                logger.info(f"Resuming {agent_id} with session {session_id}")
                prompt = instruction if instruction else None
            else:
                logger.info(f"Starting {agent_id} fresh (no session to resume)")
                prompt = fresh_start_prompt

            if steering_action is not None:
                prompt = _compose_resume_instruction(
                    base_prompt=prompt,
                    action=steering_action,
                    instruction=instruction,
                )
                if steering_action.id and steering_action.id in applied_actions:
                    mark_applied(paths.coral_dir, steering_action.id)

            handle = self._setup_and_start_agent(
                agent_id,
                island_id=island_id,
                resume_session_id=session_id,
                prompt=prompt,
            )
            handles.append(handle)

        self.handles = handles
        self._running = True
        self._write_pid_file()
        self._persist_agent_state()
        atexit.register(self._atexit_cleanup)
        return handles

    def _save_sessions(self) -> None:
        if not self.paths:
            return
        sessions: dict[str, str] = {}
        for handle in self.handles:
            sid = handle.session_id
            if not sid:
                sid = self._runtime_for(handle.agent_id).extract_session_id(handle.log_path)
            if sid:
                sessions[handle.agent_id] = sid
        sessions_file = self.paths.coral_dir / "public" / "sessions.json"
        sessions_file.write_text(json.dumps(sessions, indent=2), encoding="utf-8")
        logger.info(f"Saved {len(sessions)} session ID(s) to sessions.json")

    def _load_saved_sessions(self) -> dict[str, str]:
        if not self.paths:
            return {}
        sessions_file = self.paths.coral_dir / "public" / "sessions.json"
        if sessions_file.exists():
            try:
                return json.loads(sessions_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read sessions.json: {e}")
        return {}

    def _find_latest_session_from_logs(self, agent_id: str) -> str | None:
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
            return self._runtime_for(agent_id).extract_session_id(logs[-1])
        return None

    def stop_all(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        self._running = False
        self._stop_event.set()
        self._save_sessions()
        for handle in self.handles:
            handle.interrupt()
        for handle in self.handles:
            if handle.alive:
                handle.stop()
        self._cleanup_pid_file()
        self._stop_grader_daemon()
        if self._gateway:
            self._gateway.stop()
            self._gateway = None
        self._stop_sandbox()
        logger.info("All agents stopped.")

    def status(self) -> list[dict[str, Any]]:
        sandbox = self.config.agents.sandbox.provider if self._sandbox is not None else None
        statuses = []
        for handle in self.handles:
            statuses.append(
                {
                    "agent_id": handle.agent_id,
                    "alive": handle.alive,
                    "pid": handle.process.pid if handle.process else None,
                    "worktree": str(handle.worktree_path),
                    "log": str(handle.log_path),
                    "session_id": handle.session_id,
                    "restarts": self._restart_counts.get(handle.agent_id, 0),
                    "sandbox": sandbox,
                }
            )
        return statuses

    def grader_daemon_alive(self) -> bool:
        proc = self._grader_proc
        return bool(proc and proc.is_alive())

    def _get_seen_attempts(self) -> set[str]:
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")
        coral_dir = self.paths.coral_dir
        islands_dir = coral_dir / "islands"
        if islands_dir.exists():
            seen: set[str] = set()
            for island in islands_dir.iterdir():
                attempts = island / "attempts"
                if attempts.exists():
                    seen.update(f.name for f in attempts.glob("*.json"))
            return seen
        attempts_dir = coral_dir / "public" / "attempts"
        if not attempts_dir.exists():
            return set()
        return {f.name for f in attempts_dir.glob("*.json")}

    def _resolve_attempt_path(self, fname: str) -> Path | None:
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")
        coral_dir = self.paths.coral_dir
        islands_dir = coral_dir / "islands"
        if islands_dir.exists():
            for island in islands_dir.iterdir():
                p = island / "attempts" / fname
                if p.exists():
                    return p
        p = coral_dir / "public" / "attempts" / fname
        return p if p.exists() else None

    def _filter_scored(self, new_files: set[str]) -> set[str]:
        scored: set[str] = set()
        for fname in new_files:
            path = self._resolve_attempt_path(fname)
            if path is None:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            status = data.get("status")
            if status and status != "pending":
                scored.add(fname)
        return scored

    def _read_latest_attempt(
        self, new_files: set[str], agent_id: str | None = None
    ) -> dict[str, Any] | None:
        newest_path: Path | None = None
        newest_data: dict[str, Any] | None = None
        newest_mtime = 0.0
        for fname in new_files:
            path = self._resolve_attempt_path(fname)
            if path is None:
                continue
            mtime = path.stat().st_mtime
            if mtime <= newest_mtime:
                continue
            if agent_id is not None:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
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
                newest_data = None
        if newest_data is not None:
            return newest_data
        if newest_path is not None:
            try:
                return json.loads(newest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read attempt {newest_path}: {e}")
        return None

    def _get_eval_count(self) -> int:
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")
        coral_dir = self.paths.coral_dir
        if (coral_dir / "islands").exists():
            counter_file = coral_dir / "eval_count"
        else:
            counter_file = coral_dir / "public" / "eval_count"
        if counter_file.exists():
            try:
                return int(counter_file.read_text(encoding="utf-8").strip())
            except ValueError:
                pass
        return 0

    def _get_migration_eval_count(self) -> int:
        return self._get_finalized_real_attempt_count()

    def _read_all_run_attempts(self) -> list[Attempt]:
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")
        coral_dir = self.paths.coral_dir
        if (coral_dir / "islands").exists():
            attempts = []
            for island_dir in sorted((coral_dir / "islands").iterdir()):
                if island_dir.is_dir():
                    attempts.extend(read_attempts(coral_dir, island_id=island_dir.name))
            return attempts
        return read_attempts(coral_dir)

    def _get_finalized_real_attempt_count(self) -> int:
        attempts = self._read_all_run_attempts()
        return sum(
            1
            for attempt in attempts
            if attempt.status != "pending" and attempt.budget_class == BUDGET_CLASS_REAL
        )

    def _latest_finalized_real_attempt(self) -> Attempt | None:
        attempts = [
            a
            for a in self._read_all_run_attempts()
            if a.status != "pending" and a.budget_class == BUDGET_CLASS_REAL
        ]
        if not attempts:
            return None
        return max(attempts, key=lambda a: a.timestamp or "")

    def _attempt_dict_for_auto_stop(
        self, attempt: Attempt | dict[str, Any] | None
    ) -> dict[str, Any]:
        if attempt is None:
            return {
                "attempt_id": None,
                "agent_id": None,
                "score": None,
                "budget_class": None,
            }
        if isinstance(attempt, dict):
            return {
                "attempt_id": attempt.get("commit_hash"),
                "agent_id": attempt.get("agent_id"),
                "score": attempt.get("score"),
                "budget_class": get_budget_class(attempt.get("metadata")),
            }
        return {
            "attempt_id": attempt.commit_hash,
            "agent_id": attempt.agent_id,
            "score": attempt.score,
            "budget_class": attempt.budget_class,
        }

    def _score_meets_auto_stop_threshold(self, score: float | int | None, threshold: float) -> bool:
        if score is None:
            return False
        value = float(score)
        if self.config.grader.direction == "minimize":
            return value <= threshold
        return value >= threshold

    def _auto_stop_reason_from_attempt(self, attempt_data: dict[str, Any]) -> dict[str, Any] | None:
        stop_config = self.config.run.stop
        if stop_config.score_threshold is None and stop_config.max_real_attempts is None:
            return None

        attempt_info = self._attempt_dict_for_auto_stop(attempt_data)
        if attempt_info["budget_class"] != BUDGET_CLASS_REAL:
            return None

        real_attempt_count = self._get_finalized_real_attempt_count()
        threshold = stop_config.score_threshold
        if threshold is not None and self._score_meets_auto_stop_threshold(
            attempt_info["score"], threshold
        ):
            return self._build_auto_stop_reason(
                "score_threshold",
                attempt_info,
                real_attempt_count,
            )

        max_real_attempts = stop_config.max_real_attempts
        if max_real_attempts is not None and real_attempt_count >= max_real_attempts:
            return self._build_auto_stop_reason(
                "max_real_attempts",
                attempt_info,
                real_attempt_count,
            )
        return None

    def _auto_stop_reason_from_current_state(self) -> dict[str, Any] | None:
        stop_config = self.config.run.stop
        if stop_config.score_threshold is None and stop_config.max_real_attempts is None:
            return None

        real_attempt_count = self._get_finalized_real_attempt_count()
        threshold = stop_config.score_threshold
        if threshold is not None:
            if self.paths is None:
                raise RuntimeError("run paths are not initialized; start_all() has not run")
            best = get_leaderboard(
                self.paths.coral_dir,
                top_n=1,
                direction=self.config.grader.direction,
                include_tune=False,
            )
            if best and self._score_meets_auto_stop_threshold(best[0].score, threshold):
                return self._build_auto_stop_reason(
                    "score_threshold",
                    self._attempt_dict_for_auto_stop(best[0]),
                    real_attempt_count,
                )

        max_real_attempts = stop_config.max_real_attempts
        if max_real_attempts is not None and real_attempt_count >= max_real_attempts:
            return self._build_auto_stop_reason(
                "max_real_attempts",
                self._attempt_dict_for_auto_stop(self._latest_finalized_real_attempt()),
                real_attempt_count,
            )
        return None

    def _build_auto_stop_reason(
        self,
        reason: str,
        attempt_info: dict[str, Any],
        real_attempt_count: int,
    ) -> dict[str, Any]:
        stop_config = self.config.run.stop
        return {
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
            "attempt_id": attempt_info["attempt_id"],
            "agent_id": attempt_info["agent_id"],
            "score": attempt_info["score"],
            "score_threshold": stop_config.score_threshold,
            "direction": self.config.grader.direction,
            "real_attempt_count": real_attempt_count,
            "max_real_attempts": stop_config.max_real_attempts,
        }

    def _auto_stop(self, reason: dict[str, Any]) -> None:
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")
        write_auto_stop(self.paths.coral_dir, reason)
        logger.info(
            "Auto-stop triggered: %s (score=%s, real_attempts=%s)",
            reason["reason"],
            reason["score"],
            reason["real_attempt_count"],
        )
        if self.verbose:
            print(
                "[coral] Auto-stop: "
                f"{reason['reason']} "
                f"(score={reason['score']}, "
                f"real_attempts={reason['real_attempt_count']})"
            )
        self.stop_all()

    def _get_heartbeat_runner(self, agent_id: str) -> HeartbeatRunner:
        from coral.agent.heartbeat import HeartbeatAction

        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")
        shared_dir = self._runtime_for(agent_id).shared_dir_name
        island_id = self._agent_island.get(agent_id)

        local_actions = read_agent_heartbeat(self.paths.coral_dir, agent_id, island_id=island_id)
        global_actions = read_global_heartbeat(self.paths.coral_dir, island_id=island_id)

        heartbeat_actions = []
        for ad in local_actions:
            prompt_template = ad.get("prompt") or DEFAULT_PROMPTS.get(ad["name"], "")
            prompt = (
                prompt_template.format(shared_dir=shared_dir, agent_id=agent_id)
                if prompt_template
                else ""
            )
            trigger = ad.get("trigger") or DEFAULT_TRIGGER.get(ad["name"], "interval")
            heartbeat_actions.append(
                HeartbeatAction(
                    name=ad["name"],
                    every=ad["every"],
                    prompt=prompt,
                    is_global=False,
                    trigger=trigger,
                    options=dict(ad.get("options") or {}),
                )
            )
        for ad in global_actions:
            prompt_template = ad.get("prompt") or DEFAULT_PROMPTS.get(ad["name"], "")
            prompt = (
                prompt_template.format(shared_dir=shared_dir, agent_id=agent_id)
                if prompt_template
                else ""
            )
            trigger = ad.get("trigger") or DEFAULT_TRIGGER.get(ad["name"], "interval")
            heartbeat_actions.append(
                HeartbeatAction(
                    name=ad["name"],
                    every=ad["every"],
                    prompt=prompt,
                    is_global=True,
                    trigger=trigger,
                    options=dict(ad.get("options") or {}),
                )
            )
        return HeartbeatRunner(heartbeat_actions)

    def _is_paused(self, agent_id: str) -> bool:
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

    def _classify_agent_exit(self, agent_id: str, log_path: Path, exit_code: int | None) -> str:
        started = self._started_at.get(agent_id)
        uptime = time.time() - started if started is not None else None
        min_clean = self.config.agents.min_clean_runtime_seconds
        runtime = self._runtime_for(agent_id)
        if hasattr(runtime, "classify_exit"):
            try:
                return runtime.classify_exit(
                    log_path,
                    exit_code,
                    uptime,
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
        cfg = self.config.agents
        return (
            cfg.restart_burst_threshold > 0
            and cfg.restart_burst_window > 0
            and cfg.restart_pause_seconds > 0
        )

    def _should_pause_for_burst(self, agent_id: str) -> bool:
        if not self._breaker_enabled():
            return False
        history = self._crash_history.get(agent_id)
        if not history:
            return False
        return len(history) >= self.config.agents.restart_burst_threshold

    def _enter_paused(self, agent_id: str, log_path: Path) -> None:
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
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")
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
                err_path = self.paths.coral_dir / "public" / "diagnostics" / agent_id / "agent.err"
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
        proc = self._grader_proc
        if proc is None:
            return False
        try:
            return bool(proc.is_alive())
        except Exception:
            return False

    def _attempt_age_seconds(self, timestamp_iso: str) -> float | None:
        try:
            ts = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return (datetime.now(UTC) - ts).total_seconds()

    def _persist_agent_state(self) -> None:
        if self.paths is None:
            return
        sandbox = self.config.agents.sandbox.provider if self._sandbox is not None else None
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
                sandbox=sandbox,
            )
        try:
            write_agent_state(self.paths.coral_dir, document)
        except OSError as e:
            logger.error(f"Failed to persist agent_state.json: {e}")

    def _build_score_prompt(self, attempt: dict[str, Any], eval_count: int) -> str:
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
        lines.extend(
            [
                "",
                "Keep working. Do NOT exit just because progress has stalled, the "
                "obvious next steps are exhausted, or you concluded last session that "
                "the task is intractable / saturated / done. Even when no immediate "
                "path forward is visible, there is always productive work to do:",
                "",
                "- **Gather new information.** Read parts of the codebase, docs, or "
                "data you haven't touched. Profile or instrument what you've been "
                "guessing at. Search the web for related work. Check what other "
                "agents have tried via `coral log -n 10`, `coral notes`, and "
                "`coral skills`.",
                "- **Run trial experiments.** Probe assumptions you've been treating "
                "as facts. Ablate components you've been treating as load-bearing. "
                "Where the grader supports it, sweep variants cheaply with "
                "`coral eval --tune` before committing a real eval.",
                "- **Organize existing knowledge.** Consolidate scattered notes, "
                "distill reusable skills, write down what you've ruled out and *why* "
                "so the next iteration starts informed instead of repeating dead "
                "ends.",
            ]
        )
        if self.config.agents.count > 1:
            lines.append(
                "- **Find a complementary role on the team.** Reflect on what you've "
                "contributed so far and on what your teammates are working on "
                "(`coral log -n 10 --recent`, `coral notes --recent`). Pick a niche "
                "that complements rather than duplicates them — investigate a "
                "sub-problem nobody is owning, build a shared tool they're missing, "
                "or pursue a direction they haven't explored."
            )
        lines.extend(
            [
                "",
                "A short acknowledgment of the current state is not an acceptable "
                "session. Pick one of the above and act on it.",
            ]
        )
        return "\n".join(lines)

    def _maybe_run_migration_cycle(self) -> None:
        runner = self._migration_runner
        if not runner.enabled or self.paths is None:
            return
        if self._retry_deferred_migration_batch():
            return
        current_evals = self._get_migration_eval_count()
        if not runner.should_run(current_global_evals=current_evals):
            return

        best_scores = self._gather_island_best_scores()
        migrations = runner.run_cycle(
            coral_dir=self.paths.coral_dir,
            island_best_scores=best_scores,
            current_agent_islands=dict(self._agent_island),
            last_migrated_evals=self._last_migrated_eval,
            current_evals=current_evals,
        )
        runner.mark_cycle_complete(current_global_evals=current_evals)

        migrations = self._select_executable_migration_batch(
            self._filter_current_migration_candidates(migrations)
        )

        if not migrations:
            logger.info(
                f"Migration cycle @ real eval#{current_evals}: no executable migration candidates"
            )
            return

        self._apply_migration_batch(migrations, current_evals=current_evals)

    def _gather_island_best_scores(self) -> dict[str, float]:
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")
        results: dict[str, float] = {}
        direction = self.config.grader.direction
        islands_dir = self.paths.coral_dir / "islands"
        if not islands_dir.exists():
            return {}
        for island_dir in sorted(islands_dir.iterdir()):
            if not island_dir.is_dir():
                continue
            top = get_leaderboard(
                self.paths.coral_dir,
                top_n=1,
                direction=direction,
                island_id=island_dir.name,
            )
            if top and top[0].score is not None:
                results[island_dir.name] = top[0].score
        return results

    def _select_executable_migration_batch(
        self,
        migrations: list[MigrationCandidate],
    ) -> list[MigrationCandidate]:
        if not migrations:
            return []

        max_per_cycle = self.migration_config.max_per_cycle
        if not self._agent_island or self.paths is None:
            return migrations[:max_per_cycle]

        island_ids = self._migration_island_ids()
        roster = IslandRoster.from_agent_islands(
            self._agent_island,
            island_ids=island_ids,
        )
        return choose_roster_balanced_subset(
            migrations,
            roster=roster,
            max_per_cycle=max_per_cycle,
            minimize=self.config.grader.direction == "minimize",
        )

    def _migration_island_ids(self) -> list[str]:
        if self.paths is not None:
            islands_dir = self.paths.coral_dir / "islands"
            if islands_dir.exists():
                ids = sorted(d.name for d in islands_dir.iterdir() if d.is_dir())
                if ids:
                    return ids
        return [str(i) for i in range(self.config.islands.count)]

    def _retry_deferred_migration_batch(self) -> bool:
        if not self._deferred_candidates:
            return False
        self._prune_deferred()
        if not self._deferred_candidates:
            return False
        migrations = [candidate for candidate, _reason in self._deferred_candidates]
        logger.info(f"Re-attempting deferred migration batch: {[c.agent_id for c in migrations]}")
        self._apply_migration_batch(migrations, retry=True)
        return True

    def _apply_migration_batch(
        self,
        migrations: list[MigrationCandidate],
        *,
        current_evals: int | None = None,
        retry: bool = False,
    ) -> bool:
        if not migrations:
            return False

        blocked = [
            (candidate, reason)
            for candidate in migrations
            if (reason := self._migration_block_reason(candidate)) is not None
        ]
        if blocked:
            non_retriable = [
                (candidate, reason)
                for candidate, reason in blocked
                if not self._migration_block_is_retriable(reason)
            ]
            if non_retriable:
                for candidate, reason in non_retriable:
                    self._handle_blocked_migration(candidate, reason)
                self._deferred_candidates = []
                logger.info("Dropping migration batch because it went stale")
            else:
                self._defer_migration_batch(migrations, blocked)
                prefix = "Deferred migration batch retry"
                if not retry:
                    prefix = f"Migration cycle @ real eval#{current_evals}"
                logger.info(
                    f"{prefix}: deferring batch because {len(blocked)} candidate(s) are not ready"
                )
            return False

        applied: list[MigrationCandidate] = []
        ok = True
        for candidate in migrations:
            try:
                self._apply_migration(candidate, assume_preflight=True)
                applied.append(candidate)
            except Exception as e:
                logger.exception(
                    f"Migration {candidate.agent_id} {candidate.src_island}→"
                    f"{candidate.dst_island} failed: {e}"
                )
                ok = False
                break
        self._resync_bystanders_after_migration(applied)
        if ok:
            self._deferred_candidates = []
        return ok

    def _migration_resync_ops(self) -> list[MigrationResyncOp]:
        ops: list[MigrationResyncOp] = []
        if self._sandbox is not None:
            ops.append(MigrationResyncOp(name="sandbox"))
        return ops

    def _resync_bystanders_after_migration(self, applied: list[MigrationCandidate]) -> None:
        ops = self._migration_resync_ops()
        if not applied or not ops or not self.migration_config.resync_bystanders:
            return
        affected = {c.src_island for c in applied} | {c.dst_island for c in applied}
        migrated = {c.agent_id for c in applied}
        op_names = ", ".join(op.name for op in ops)
        pre_restart_ops = [op.prepare for op in ops if op.prepare is not None]
        for idx, handle in enumerate(self.handles):
            agent_id = handle.agent_id
            if agent_id in migrated or not handle.alive or self._is_paused(agent_id):
                continue
            if self._agent_island.get(agent_id) in affected:
                logger.info(
                    f"Migration resync ({op_names}): restarting {agent_id} "
                    f"(island partition changed)"
                )
                self.handles[idx] = self._interrupt_and_resume(
                    idx,
                    prompt=_build_resync_prompt(op_names),
                    prompt_source="migration:resync",
                    pre_restart_ops=pre_restart_ops,
                )

    def _migration_block_reason(self, candidate: MigrationCandidate) -> str | None:
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")

        agent_id = candidate.agent_id
        if not any(handle.agent_id == agent_id for handle in self.handles):
            return "missing-handle"
        if self._is_paused(agent_id):
            return "paused"

        current_island = self._agent_island.get(agent_id)
        if current_island is not None and current_island != candidate.src_island:
            return f"stale:{current_island}"

        return None

    @staticmethod
    def _migration_block_is_retriable(reason: str) -> bool:
        return reason == "paused"

    @staticmethod
    def _migration_defer_reason(reason: str) -> str:
        if reason.startswith("stale:"):
            return "stale"
        return reason

    def _defer_migration_batch(
        self,
        migrations: list[MigrationCandidate],
        blocked: list[tuple[MigrationCandidate, str]],
    ) -> None:
        blocked_reasons = {
            candidate.agent_id: self._migration_defer_reason(reason)
            for candidate, reason in blocked
        }
        self._deferred_candidates = [
            (
                candidate,
                blocked_reasons.get(candidate.agent_id, "waiting-for-batch"),
            )
            for candidate in migrations
        ]

    def _handle_blocked_migration(self, candidate: MigrationCandidate, reason: str) -> None:
        agent_id = candidate.agent_id
        if reason == "missing-handle":
            logger.warning(f"Migration target {agent_id} has no live handle; skipping")
            return
        if reason == "paused":
            logger.info(f"Migration target {agent_id} is paused; deferring")
            self._defer_candidate(candidate, reason="paused")
            return
        if reason.startswith("stale:"):
            current = reason.split(":", 1)[1]
            logger.info(
                f"Migration target {agent_id} no longer lives on island "
                f"{candidate.src_island} (current: {current}); skipping stale candidate"
            )
            self._drop_deferred_for(agent_id)
            return
        logger.info(f"Migration target {agent_id} is blocked ({reason}); deferring")
        self._defer_candidate(candidate, reason=reason)

    def _filter_current_migration_candidates(
        self,
        migrations: list[MigrationCandidate],
    ) -> list[MigrationCandidate]:
        filtered: list[MigrationCandidate] = []
        seen_agents: set[str] = set()
        for candidate in migrations:
            current = self._agent_island.get(candidate.agent_id)
            if current is not None and current != candidate.src_island:
                logger.info(
                    f"Skipping stale migration candidate for {candidate.agent_id}: "
                    f"planned from island {candidate.src_island}, currently on {current}"
                )
                continue
            if candidate.agent_id in seen_agents:
                logger.info(
                    f"Skipping duplicate migration candidate for {candidate.agent_id} "
                    f"in the same cycle"
                )
                continue
            seen_agents.add(candidate.agent_id)
            filtered.append(candidate)
        return filtered

    def _defer_candidate(
        self,
        candidate: MigrationCandidate,
        *,
        reason: str,
    ) -> None:
        for i, (c, _r) in enumerate(self._deferred_candidates):
            if c.agent_id == candidate.agent_id:
                self._deferred_candidates[i] = (candidate, reason)
                return
        self._deferred_candidates.append((candidate, reason))

    def _drop_deferred_for(self, agent_id: str) -> None:
        self._deferred_candidates = [
            (c, r) for c, r in self._deferred_candidates if c.agent_id != agent_id
        ]

    def _prune_deferred(self) -> None:
        for candidate, _reason in self._deferred_candidates:
            if self._agent_island.get(candidate.agent_id) != candidate.src_island:
                logger.info(
                    f"Dropping deferred migration batch because {candidate.agent_id} "
                    f"no longer lives on island {candidate.src_island}"
                )
                self._deferred_candidates = []
                return

    def _apply_migration(
        self, candidate: MigrationCandidate, *, assume_preflight: bool = False
    ) -> None:
        """Move candidate.agent_id from src island to dst, then restart it."""
        if self.paths is None:
            raise RuntimeError("run paths are not initialized; start_all() has not run")

        agent_id = candidate.agent_id
        if not assume_preflight:
            reason = self._migration_block_reason(candidate)
            if reason is not None:
                self._handle_blocked_migration(candidate, reason)
                return

        idx: int | None = None
        for i, handle in enumerate(self.handles):
            if handle.agent_id == agent_id:
                idx = i
                break
        if idx is None:
            logger.warning(f"Migration target {agent_id} has no live handle; skipping")
            return

        src = candidate.src_island
        dst = candidate.dst_island
        current_island = self._agent_island.get(agent_id)
        if current_island is not None and current_island != src:
            logger.info(
                f"Migration target {agent_id} no longer lives on island {src} "
                f"(current: {current_island}); skipping stale candidate"
            )
            self._drop_deferred_for(agent_id)
            return
        coral_dir = self.paths.coral_dir
        runtime = self._runtime_for(agent_id)
        shared_dir_name = runtime.shared_dir_name
        worktree_path = self.handles[idx].worktree_path

        self._drop_deferred_for(agent_id)

        self.handles[idx].interrupt()
        session_id = runtime.extract_session_id(self.handles[idx].log_path)

        _move_agent_files(coral_dir, agent_id, src=src, dst=dst)
        repoint_shared_state(worktree_path, coral_dir, shared_dir_name, new_island_id=dst)

        gateway_url = self._gateway.url if self._gateway else None
        gateway_api_key = self._gateway_keys.get(agent_id)
        _refresh_runtime_settings(
            worktree_path,
            coral_dir=coral_dir,
            shared_dir_name=shared_dir_name,
            research=self.config.agents.research,
            gateway_url=gateway_url,
            gateway_api_key=gateway_api_key,
            island_id=dst,
        )

        self._swap_spec_island(agent_id, new_island_id=dst)
        self._agent_island[agent_id] = dst

        self._last_migrated_eval[agent_id] = self._get_migration_eval_count()
        try:
            _write_last_migrated_evals(coral_dir, self._last_migrated_eval)
        except OSError as e:
            logger.warning(f"Failed to persist migration state: {e}")

        if self.migration_config.notify_island:
            try:
                _write_arrival_note(coral_dir, candidate)
            except OSError as e:
                logger.warning(f"Failed to write arrival note for {agent_id}: {e}")

        self._restart_counts[agent_id] = self._restart_counts.get(agent_id, 0) + 1
        prompt = _build_migration_prompt(candidate, shared_dir=shared_dir_name)

        logger.info(f"Migrated {agent_id}: island {src} → {dst} (score={candidate.score:.6f})")
        if self.verbose:
            print(
                f"[coral] Migration: {agent_id} moved island {src} → {dst} "
                f"(score={candidate.score:.6f})"
            )

        self.handles[idx] = self._setup_and_start_agent(
            agent_id,
            island_id=dst,
            resume_session_id=session_id,
            prompt=prompt,
            prompt_source="migration",
        )
        self._write_agent_pids()

    @property
    def migration_config(self):
        return self.config.islands.migration

    def _swap_spec_island(self, agent_id: str, *, new_island_id: str) -> None:
        for i, s in enumerate(self.specs):
            if s.agent_id != agent_id:
                continue
            updated = AgentSpec(
                agent_id=s.agent_id,
                runtime=s.runtime,
                model=s.model,
                runtime_options=dict(s.runtime_options),
                assignment_index=s.assignment_index,
                island_id=new_island_id,
            )
            self.specs[i] = updated
            self.specs_by_id[agent_id] = updated
            return

    def monitor_loop(self, check_interval: int = 5) -> None:
        """Monitor agents, deliver eval feedback via --resume, auto-restart."""

        def _signal_handler(sig: int, frame: Any) -> None:
            if self._stopping:
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

        seen_attempts = self._filter_scored(self._get_seen_attempts())

        startup_auto_stop = self._auto_stop_reason_from_current_state()
        if startup_auto_stop is not None:
            self._auto_stop(startup_auto_stop)
            return

        logger.info(f"Monitoring {len(self.handles)} agent(s) (check every {check_interval}s)...")

        while self._running:
            current_attempts = self._get_seen_attempts()
            new_attempts = current_attempts - seen_attempts

            scored_new = self._filter_scored(new_attempts)
            seen_attempts = seen_attempts | scored_new

            if scored_new:
                attempt_data = self._read_latest_attempt(scored_new)

                if attempt_data:
                    committing_agent_id = attempt_data.get("agent_id")
                    if not committing_agent_id:
                        continue

                    self._agent_eval_counts[committing_agent_id] = (
                        self._agent_eval_counts.get(committing_agent_id, 0) + 1
                    )
                    agent_eval_count = self._agent_eval_counts[committing_agent_id]
                    island_id = self._agent_island.get(committing_agent_id)
                    if island_id is not None:
                        global_eval_count = read_eval_count(
                            self.paths.coral_dir, island_id=island_id
                        )
                    else:
                        global_eval_count = self._get_eval_count()

                    budget_class = get_budget_class(attempt_data.get("metadata"))
                    score = attempt_data.get("score")
                    minimize = self.config.grader.direction == "minimize"
                    if budget_class == BUDGET_CLASS_REAL:
                        if score is not None:
                            prev_best = self._agent_best_scores.get(committing_agent_id)
                            strictly_improved = (
                                prev_best is None
                                or (minimize and score < prev_best)
                                or (not minimize and score > prev_best)
                            )
                            if strictly_improved:
                                self._agent_best_scores[committing_agent_id] = score
                        self._agent_score_history.setdefault(committing_agent_id, []).append(score)

                    auto_stop_reason = (
                        self._auto_stop_reason_from_attempt(attempt_data)
                        or self._auto_stop_reason_from_current_state()
                    )
                    if auto_stop_reason is not None:
                        self._auto_stop(auto_stop_reason)
                        break

                    score_history = self._agent_score_history.get(committing_agent_id, [])

                    runner = self._get_heartbeat_runner(committing_agent_id)
                    actions = runner.check(
                        local_eval_count=agent_eval_count,
                        global_eval_count=global_eval_count,
                        score_history=score_history,
                        minimize=minimize,
                    )
                    if not actions:
                        continue

                    committing_idx = None
                    for i, handle in enumerate(self.handles):
                        if handle.agent_id == committing_agent_id and handle.alive:
                            committing_idx = i
                            break
                    if committing_idx is None:
                        continue

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
                    if budget_class != BUDGET_CLASS_REAL:
                        header_lines.append(
                            f"Budget: {budget_class} "
                            "(this attempt does not count toward your plateau budget)"
                        )
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
                        print(
                            f"\n[coral] Agent eval #{agent_eval_count}: score={attempt_data.get('score', '?')}"
                        )
                        print(f"[coral] Interrupting {committing_agent_id} for {names}...\n")
                    self.handles[committing_idx] = self._interrupt_and_resume(
                        committing_idx,
                        combined_prompt,
                        prompt_source=f"heartbeat:{names}",
                    )
                    self._write_agent_pids()

            self._maybe_run_migration_cycle()

            for i, handle in enumerate(self.handles):
                if not handle.alive and self._running:
                    agent_id = handle.agent_id

                    if self._is_paused(agent_id):
                        continue

                    if agent_id in self._pending_restart_after_pause:
                        self._pending_restart_after_pause.discard(agent_id)
                        count = self._restart_counts.get(agent_id, 0) + 1
                        eval_count = self._get_eval_count()
                        latest = self._read_latest_attempt(current_attempts, agent_id=agent_id)
                        prompt = self._build_score_prompt(latest, eval_count) if latest else None
                        logger.warning(
                            f"Agent {agent_id} restarting after pause cooldown (restart #{count})"
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

                    classification = self._classify_agent_exit(agent_id, log_path, exit_code)
                    if classification != "clean":
                        self._record_crash(agent_id, exit_code, log_path, classification)
                        if self._should_pause_for_burst(agent_id):
                            self._enter_paused(agent_id, log_path)
                            self._write_agent_pids()
                            continue

                    count = self._restart_counts.get(agent_id, 0) + 1

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

            stall_threshold = self.config.agents.timeout
            if stall_threshold > 0:
                coral_dir = self.paths.coral_dir
                if (coral_dir / "islands").exists():
                    island_ids = {s.island_id for s in self.specs if s.island_id is not None}
                    attempts_cache: list = []
                    for iid in island_ids:
                        attempts_cache.extend(read_attempts(coral_dir, island_id=iid))
                else:
                    attempts_cache = read_attempts(coral_dir)
                grader_alive = self._grader_alive()

                for i, handle in enumerate(self.handles):
                    if handle.alive and self._running:
                        try:
                            age = time.time() - handle.log_path.stat().st_mtime
                        except OSError:
                            continue
                        if age <= stall_threshold:
                            continue

                        if grader_alive:
                            island_id = self._agent_island.get(handle.agent_id)
                            pending = agent_in_grader_queue(
                                self.paths.coral_dir,
                                handle.agent_id,
                                attempts_cache,
                                island_id=island_id,
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

            if self._stop_event.wait(timeout=check_interval):
                break

    def wait_for_completion(self) -> None:
        self.monitor_loop(check_interval=3)

    def _kill_old_agent_processes(self) -> None:
        if not self.paths:
            return
        agent_pids_file = self.paths.coral_dir / "public" / "agent.pids"
        if not agent_pids_file.exists():
            return

        pids = []
        for line in agent_pids_file.read_text(encoding="utf-8").strip().splitlines():
            line = line.strip()
            if line:
                pids.append(int(line))

        if not pids:
            return

        for pid in pids:
            try:
                os.kill(pid, signal.SIGINT)
                logger.info(f"Sent SIGINT to leftover agent process {pid}")
            except (ProcessLookupError, PermissionError):
                pass

        time.sleep(3)

        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
                logger.info(f"Force-killed leftover agent process {pid}")
            except (ProcessLookupError, PermissionError):
                pass

    def _write_pid_file(self) -> None:
        if self.paths:
            pid_file = self.paths.coral_dir / "public" / "manager.pid"
            pid_file.write_text(str(os.getpid()), encoding="utf-8")
            self._write_agent_pids()

    def _write_agent_pids(self) -> None:
        if self.paths:
            agent_pids_file = self.paths.coral_dir / "public" / "agent.pids"
            pids = []
            pid_map = {}
            for handle in self.handles:
                if handle.process and handle.process.pid:
                    pids.append(str(handle.process.pid))
                    pid_map[handle.agent_id] = handle.process.pid
            agent_pids_file.write_text("\n".join(pids), encoding="utf-8")
            pid_map_file = self.paths.coral_dir / "public" / "agent_pids.json"
            pid_map_file.write_text(json.dumps(pid_map), encoding="utf-8")

    def _atexit_cleanup(self) -> None:
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
    if coral_dir:
        sessions_dir = coral_dir / "public" / "sessions"
        if sessions_dir.exists():
            for project_dir in sessions_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                if (project_dir / f"{session_id}.jsonl").exists():
                    return True

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
    sessions: dict[str, str],
    coral_dir: Path | None = None,
) -> dict[str, str]:
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


def _move_agent_files(
    coral_dir: Path,
    agent_id: str,
    *,
    src: str,
    dst: str,
) -> None:
    src_root = island_root(coral_dir, src)
    dst_root = island_root(coral_dir, dst)
    for subdir, ext in (("roles", "md"), ("heartbeat", "json")):
        src_path = src_root / subdir / f"{agent_id}.{ext}"
        if not src_path.exists():
            continue
        dst_dir = dst_root / subdir
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst_path = dst_dir / f"{agent_id}.{ext}"
        _move_path_replace(src_path, dst_path)

    src_attempts = src_root / "attempts"
    if not src_attempts.exists():
        return
    for attempt_path in sorted(
        p for pattern in ("*.json", "*.jsonl") for p in src_attempts.glob(pattern)
    ):
        if not _attempt_file_belongs_to_agent(attempt_path, agent_id):
            continue
        dst_attempt = dst_root / "attempts" / attempt_path.name
        dst_attempt.parent.mkdir(parents=True, exist_ok=True)
        _move_path_replace(attempt_path, dst_attempt)
        _stamp_attempt_file_island(dst_attempt, dst)

        commit_hash = attempt_path.stem
        src_eval_log = src_root / "eval_logs" / commit_hash
        if src_eval_log.exists():
            dst_eval_log = dst_root / "eval_logs" / commit_hash
            dst_eval_log.parent.mkdir(parents=True, exist_ok=True)
            _move_path_replace(src_eval_log, dst_eval_log)


def _attempt_file_belongs_to_agent(path: Path, agent_id: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if path.suffix == ".jsonl":
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                return False
            if data.get("agent_id") != agent_id:
                return False
        return bool(text.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return False
    return data.get("agent_id") == agent_id


def _stamp_attempt_file_island(path: Path, island_id: str) -> None:
    try:
        if path.suffix == ".jsonl":
            records = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                data = json.loads(line)
                metadata = data.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                metadata["island_id"] = island_id
                data["metadata"] = metadata
                records.append(data)
            path.write_text(
                "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
            )
            return

        data = json.loads(path.read_text(encoding="utf-8"))
        metadata = data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["island_id"] = island_id
        data["metadata"] = metadata
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except (json.JSONDecodeError, OSError, TypeError) as e:
        logger.warning("Failed to stamp migrated attempt %s with island %s: %s", path, island_id, e)


def _move_path_replace(src_path: Path, dst_path: Path) -> None:
    if dst_path.exists():
        if dst_path.is_dir() and not dst_path.is_symlink():
            shutil.rmtree(dst_path)
        else:
            dst_path.unlink()
    try:
        os.replace(src_path, dst_path)
    except OSError:
        if src_path.is_dir():
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            shutil.rmtree(src_path, ignore_errors=True)
        else:
            shutil.copy2(src_path, dst_path)
            try:
                src_path.unlink()
            except OSError:
                pass


def _refresh_runtime_settings(
    worktree_path: Path,
    *,
    coral_dir: Path,
    shared_dir_name: str,
    research: bool,
    gateway_url: str | None,
    gateway_api_key: str | None,
    island_id: str,
) -> None:
    if shared_dir_name == ".claude":
        setup_claude_settings(
            worktree_path,
            coral_dir=coral_dir,
            research=research,
            gateway_url=gateway_url,
            gateway_api_key=gateway_api_key,
            island_id=island_id,
        )
    elif shared_dir_name == ".opencode":
        setup_opencode_settings(
            worktree_path,
            coral_dir=coral_dir,
            research=research,
            gateway_url=gateway_url,
            gateway_api_key=gateway_api_key,
            island_id=island_id,
        )
    elif shared_dir_name == ".codex":
        setup_codex_settings(
            worktree_path,
            coral_dir=coral_dir,
            research=research,
            gateway_url=gateway_url,
            gateway_api_key=gateway_api_key,
            island_id=island_id,
        )
    elif shared_dir_name == ".cursor":
        setup_cursor_settings(
            worktree_path,
            coral_dir=coral_dir,
            research=research,
            gateway_url=gateway_url,
            gateway_api_key=gateway_api_key,
            island_id=island_id,
        )


def _migration_state_path(coral_dir: Path) -> Path:
    return coral_dir / "public" / "migration_state.json"


def _write_last_migrated_evals(coral_dir: Path, last_migrated: dict[str, int]) -> Path:
    target = _migration_state_path(coral_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"schema_version": 1, "last_migrated_evals": last_migrated},
        indent=2,
        sort_keys=True,
    )
    fd, tmp_path = tempfile.mkstemp(
        prefix=".migration_state.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp_path, target)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise
    return target


def _read_last_migrated_evals(coral_dir: Path) -> dict[str, int]:
    target = _migration_state_path(coral_dir)
    try:
        with open(target, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    data = raw.get("last_migrated_evals", {})
    if not isinstance(data, dict):
        return {}
    out: dict[str, int] = {}
    for agent_id, evals in data.items():
        try:
            out[str(agent_id)] = int(evals)
        except (TypeError, ValueError):
            continue
    return out


def _write_arrival_note(coral_dir: Path, candidate: MigrationCandidate) -> None:
    notes_dir = island_root(coral_dir, candidate.dst_island) / "notes" / "migrations"
    notes_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    fname_ts = now.strftime("%Y%m%dT%H%M%S")
    body = (
        f"---\n"
        f"creator: coral\n"
        f"created: {now.date().isoformat()}\n"
        f"title: Migration arrival — {candidate.agent_id}\n"
        f"---\n\n"
        f"# Migration arrival: {candidate.agent_id}\n\n"
        f"`{candidate.agent_id}` migrated to this island from "
        f"island `{candidate.src_island}` with a recent best score of "
        f"`{candidate.score:.6f}` over the last several real evals.\n\n"
        f"They bring their evolved role, heartbeat cadence, attempts, "
        f"and eval logs with them; notes and skills stay on island "
        f"`{candidate.src_island}` as island-local shared knowledge.\n"
    )
    fname = f"migration_{fname_ts}_{candidate.agent_id}.md"
    (notes_dir / fname).write_text(body, encoding="utf-8")


def _reset_worktree_to_commit(worktree_path: Path, target_hash: str) -> None:
    result = subprocess.run(
        ["git", "cat-file", "-t", target_hash],
        capture_output=True,
        text=True,
        cwd=worktree_path,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Steering target commit '{target_hash}' not found")

    result = subprocess.run(
        ["git", "reset", "--hard", target_hash],
        capture_output=True,
        text=True,
        cwd=worktree_path,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Steering checkout failed for '{target_hash}': {result.stderr}")


def _discarded_commit_hashes(worktree_path: Path, target_hash: str) -> set[str]:
    result = subprocess.run(
        ["git", "rev-list", f"{target_hash}..HEAD"],
        capture_output=True,
        text=True,
        cwd=worktree_path,
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _worktree_head_descends_from(worktree_path: Path, target_hash: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", target_hash, "HEAD"],
        capture_output=True,
        text=True,
        cwd=worktree_path,
    )
    return result.returncode == 0


def _compose_resume_instruction(
    *,
    base_prompt: str | None,
    action: ContinueFromAction,
    instruction: str | None,
) -> str:
    sections: list[str] = []
    if base_prompt:
        sections.append(base_prompt)
    sections.append(
        "## Continue from Attempt "
        f"{action.hash}\n\n"
        "Your worktree has been reset to this attempt before resume. "
        "Build from this code state instead of the previous HEAD."
    )
    if action.instruction:
        sections.append(f"## Steering Instructions\n{action.instruction}")
    if instruction and (base_prompt is None or instruction not in base_prompt):
        sections.append(f"## Additional Instructions\n{instruction}")
    return "\n\n".join(sections)


def _build_migration_prompt(candidate: MigrationCandidate, *, shared_dir: str) -> str:
    return (
        f"## You have migrated to a new island\n\n"
        f"You were doing well on island `{candidate.src_island}` "
        f"(recent best `{candidate.score:.6f}`). The team selected you "
        f"to seed island `{candidate.dst_island}`. Your worktree is now "
        f"wired to that island's shared state.\n\n"
        f"What changed:\n"
        f"- `{shared_dir}/notes`, `{shared_dir}/skills`, "
        f"`{shared_dir}/attempts`, `{shared_dir}/heartbeat`, "
        f"`{shared_dir}/roles`, and `{shared_dir}/eval_logs` now resolve to island "
        f"`{candidate.dst_island}`.\n"
        f"- Your evolved role, heartbeat cadence, attempts, and eval logs "
        f"followed you here.\n"
        f"- Notes and skills stayed on island `{candidate.src_island}` as "
        f"that island's shared knowledge base.\n\n"
        f"What to do first:\n"
        f"1. `coral log -n 10` to see this island's current leaderboard.\n"
        f"2. `coral notes --recent` to read what your new teammates "
        f"have been working on.\n"
        f"3. `coral skills` to discover what tooling already exists "
        f"here so you don't reinvent it.\n\n"
        f"Then bring your strongest ideas from your previous run and "
        f"adapt them to this island's frontier."
    )


def _build_resync_prompt(op_names: str) -> str:
    return (
        "An agent migrated between islands, so your process was restarted "
        f"to refresh launch-injected state ({op_names}) against the new "
        "island roster. Your session and work are intact — continue exactly "
        "where you left off."
    )
