"""Agent-based judge grader — a persistent evaluator agent for worker output.

The judge agent runs in its own isolated workspace with tool access, enabling
it to open spreadsheets, parse PDFs, run scripts, and perform iterative
reasoning.  The worker's codebase is symlinked into the workspace as
``./codebase/`` (read-only).  The judge writes structured evaluation results
to ``evaluation.json`` inside its workspace, and the grader parses it into a
ScoreBundle.

The judge is **persistent** across evaluations — it maintains a session that
is resumed on each ``coral eval`` call.  On the first evaluation it reads source
materials, forms an independent understanding of the task, and generates an
initial rubric.  On subsequent evaluations it resumes its session with the new
worker output, preserving its accumulated knowledge and reasoning context.

Config args (read from ``grader.args`` in task.yaml):

- ``model``: LLM model for the judge agent (default: claude-sonnet-4-20250514)
- ``runtime``: Agent runtime to use (default: claude_code)
- ``judge_max_turns``: Max reasoning turns for the judge (default: 30)
- ``max_criteria``: Maximum active criteria (default: 10)
- ``min_criteria``: Minimum criteria (default: 3)
- ``reference_files``: Optional reference docs for fact-checking
- ``files``: Optional list of expected output file names (informs judge instructions)
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from coral.config import CoralConfig, GraderConfig

from apex_judge.rubric_item import RubricItem
from coral.grader.task_grader import TaskGrader
from coral.types import Score, ScoreBundle

from apex_judge.dynamic_rubric_state import RubricStateManager, RubricVersion
from apex_judge.judge_md import generate_judge_md

logger = logging.getLogger(__name__)


class AgentJudgeGrader(TaskGrader):
    """Grader that spawns a judge agent to evaluate worker output."""

    def __init__(self, config: GraderConfig) -> None:
        super().__init__(config)

    def _load_coral_config(self) -> CoralConfig:
        """Load the full CoralConfig from .coral/config.yaml."""
        config_path = Path(self.private_dir).parent / "config.yaml"
        if config_path.exists():
            return CoralConfig.from_yaml(config_path)

        # Minimal fallback; lets the judge still run even without config.yaml on disk.
        from coral.config import AgentConfig, SharingConfig, TaskConfig, WorkspaceConfig

        return CoralConfig(
            task=TaskConfig(
                name=self.config.args.get("task_name", ""),
                description=self.config.args.get("task_description", ""),
            ),
            grader=self.config,
            agents=AgentConfig(),
            sharing=SharingConfig(),
            workspace=WorkspaceConfig(),
        )

    def evaluate(self) -> ScoreBundle:
        """Run the persistent judge agent to evaluate worker output."""
        from coral.agent.registry import get_runtime
        from coral.workspace.worktree import setup_shared_state

        full_config = self._load_coral_config()

        state = RubricStateManager(self.private_dir)
        runtime_name = self.config.args.get("runtime", "claude_code")
        runtime = get_runtime(runtime_name)
        model = self.config.args.get("model", "claude-sonnet-4-20250514")
        max_turns = self.config.args.get("judge_max_turns", 30)

        # 1. Prepare isolated judge workspace
        judge_dir = Path(self.private_dir) / "judge"
        workspace = judge_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        log_dir = judge_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        scratch_dir = workspace / "scratch"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        output_path = workspace / "evaluation.json"

        if output_path.exists():
            output_path.unlink()

        # 2. Symlink worker's codebase into judge workspace (read-only access)
        codebase_link = workspace / "codebase"
        if codebase_link.is_symlink():
            codebase_link.unlink()
        if not codebase_link.exists():
            codebase_link.symlink_to(Path(self.codebase_path).resolve())

        # 3. Generate and write judge instructions
        judge_md_content = self._generate_judge_instructions(
            full_config, state, str(output_path), str(scratch_dir)
        )
        instruction_path = workspace / runtime.instruction_filename
        instruction_path.write_text(judge_md_content)

        # 4. Write metadata files
        (workspace / ".coral_agent_id").write_text("judge")
        coral_dir = Path(self.private_dir).parent
        (workspace / ".coral_dir").write_text(str(coral_dir.resolve()))

        # 5. Set up shared state symlinks (rubrics, notes, guidance, etc.)
        setup_shared_state(workspace, coral_dir, runtime.shared_dir_name)

        # 6. Set up permissions (Claude Code only; no-op for OpenCode/Codex)
        self._setup_judge_permissions(runtime, workspace)

        # 7. Load or create judge session
        session_id_path = judge_dir / "session_id"
        resume_session_id = self._load_session_id(session_id_path)

        if resume_session_id:
            prompt = (
                "The worker agent has submitted a new version for evaluation. "
                "Re-read your instructions (they have been updated with the latest "
                "rubric state and agent notes). Then evaluate the worker's current "
                f"output and write your evaluation to {output_path}. "
                "The worker's files are in ./codebase/."
            )
            prompt_source = "resume"
            logger.info(f"Resuming persistent judge session {resume_session_id}")
        else:
            prompt = (
                "You are the evaluator. Read your instructions carefully — they "
                "contain the task description, evaluation protocol, and rubric. "
                "Start by reading the source materials in ./codebase/ to build "
                "your own understanding of the task. Then evaluate the worker's "
                f"output and write your evaluation to {output_path}."
            )
            prompt_source = "start"
            logger.info("Starting new judge session (first evaluation)")

        handle = runtime.start(
            worktree_path=workspace,
            coral_md_path=instruction_path,
            model=model,
            max_turns=max_turns,
            log_dir=log_dir,
            prompt=prompt,
            prompt_source=prompt_source,
            resume_session_id=resume_session_id,
        )

        # 8. Wait for completion with timeout
        timeout = self.config.timeout or 600
        deadline = time.time() + timeout
        while handle.alive and time.time() < deadline:
            time.sleep(2)

        timed_out = handle.alive
        if timed_out:
            handle.stop()

        # 9. Save session ID for next eval
        new_session_id = runtime.extract_session_id(handle.log_path)
        if new_session_id:
            self._save_session_id(session_id_path, new_session_id)
            logger.info(f"Saved judge session ID: {new_session_id}")
        elif resume_session_id:
            logger.debug("Could not extract new session ID, keeping previous")

        if timed_out:
            return self.fail(
                f"Judge agent timed out after {timeout}s",
                feedback=f"Judge agent did not complete within {timeout}s.",
            )

        # 10. Parse evaluation.json → ScoreBundle
        if not output_path.exists():
            return self.fail(
                "Judge agent did not write evaluation.json",
                feedback="The judge agent completed but did not produce an evaluation output file.",
            )

        try:
            data = json.loads(output_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            return self.fail(
                f"Failed to parse evaluation.json: {e}",
                feedback=f"Judge output was not valid JSON: {e}",
            )

        bundle = self._parse_evaluation(data, state, full_config)

        # 11. Cleanup scratch files (but keep workspace for session persistence)
        shutil.rmtree(scratch_dir, ignore_errors=True)

        return bundle

    def _generate_judge_instructions(
        self,
        full_config: CoralConfig,
        state: RubricStateManager,
        output_path: str,
        scratch_dir: str,
    ) -> str:
        """Generate the JUDGE.md content."""
        reference_context = self._read_reference_documents()
        files = self.config.args.get("files", [])

        return generate_judge_md(
            config=full_config,
            state=state,
            output_path=output_path,
            scratch_dir=scratch_dir,
            files=files,
            reference_context=reference_context,
            codebase_path=self.codebase_path,
        )

    def _setup_judge_permissions(self, runtime: Any, workspace: Path) -> None:
        """Write settings.json for runtimes that use it (Claude Code)."""
        shared_dir_name = runtime.shared_dir_name

        if shared_dir_name != ".claude":
            return

        settings_dir = workspace / shared_dir_name
        settings_dir.mkdir(exist_ok=True)

        workspace_str = str(workspace.resolve())
        codebase_str = str(Path(self.codebase_path).resolve())

        settings = {
            "permissions": {
                "allow": [
                    "Bash",
                    f"Read({workspace_str}/**)",
                    f"Read({codebase_str}/**)",
                    f"Edit({workspace_str}/**)",
                    f"Write({workspace_str}/**)",
                    "WebSearch",
                    "WebFetch",
                ],
                "deny": [
                    "Bash(git *)",
                    "Bash(coral eval*)",
                    f"Edit({codebase_str}/**)",
                    f"Write({codebase_str}/**)",
                ],
            },
        }

        settings_path = settings_dir / "settings.json"
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")

    @staticmethod
    def _load_session_id(path: Path) -> str | None:
        """Load the judge's session ID from disk for session resume."""
        if path.exists():
            sid = path.read_text().strip()
            if sid:
                return sid
        return None

    @staticmethod
    def _save_session_id(path: Path, session_id: str) -> None:
        """Save the judge's session ID to disk for next evaluation."""
        path.write_text(session_id)

    def _read_reference_documents(self) -> str:
        """Read reference documents from .coral/private/."""
        ref_files = self.config.args.get("reference_files", [])
        if not ref_files:
            return ""

        parts = []
        for filename in ref_files:
            filepath = Path(self.private_dir) / filename
            if not filepath.exists():
                filepath = Path(self.codebase_path) / filename
            if filepath.exists():
                content = filepath.read_text()
                if len(content) > 80_000:
                    content = content[:80_000] + "\n\n[... TRUNCATED ...]"
                parts.append(f"### {filename}\n{content}")
            else:
                logger.warning(f"Reference file not found: {filename}")

        return "\n\n".join(parts)

    def _parse_evaluation(
        self,
        data: dict[str, Any],
        state: RubricStateManager,
        full_config: CoralConfig,
    ) -> ScoreBundle:
        """Parse evaluation.json into a ScoreBundle with weighted binary scoring."""
        criteria_scores_raw = data.get("criteria_scores", [])
        if not criteria_scores_raw:
            return self.fail(
                "No criteria scores in evaluation output",
                feedback="Judge produced evaluation.json but it contained no criteria_scores.",
            )

        scores: dict[str, Score] = {}
        feedback_lines: list[str] = []
        total_weight = 0.0
        passed_weight = 0.0
        pass_count = 0
        total_count = len(criteria_scores_raw)

        criterion_history: dict[str, dict[str, Any]] = {}

        for entry in criteria_scores_raw:
            name = entry.get("name", "Unknown")
            verdict = str(entry.get("verdict", "FAIL")).upper()
            weight = float(entry.get("weight", 1.0))
            rationale = entry.get("rationale", "")

            is_pass = verdict == "PASS"
            value = 1.0 if is_pass else 0.0

            scores[name] = Score(
                value=value,
                name=name,
                explanation=rationale,
            )

            criterion_history[name] = {
                "verdict": verdict,
                "rationale": rationale,
            }

            icon = "PASS" if is_pass else "FAIL"
            feedback_lines.append(f"{icon}  {name} (weight: {weight}) — {rationale}")

            total_weight += weight
            if is_pass:
                passed_weight += weight
                pass_count += 1

        aggregated = passed_weight / total_weight if total_weight > 0 else 0.0

        # Handle rubric evolution
        current = state.get_current_version()
        rubric_version = current.version if current else 0
        evolution = data.get("rubric_evolution")
        version_note = ""
        all_passed = pass_count == total_count and total_count > 0

        if evolution is not None:
            rubric_version = self._apply_evolution(evolution, state, current)
            prev_version = current.version if current else 0
            new_version = state.get_current_version()
            if new_version:
                version_note = f"  |  Rubric evolved: v{prev_version} -> v{new_version.version}"
                public_dir = Path(self.private_dir).parent / "public"
                state.publish_rubric(public_dir)
        elif current is not None:
            public_rubric = Path(self.private_dir).parent / "public" / "rubrics" / "current.md"
            if not public_rubric.exists():
                public_dir = Path(self.private_dir).parent / "public"
                state.publish_rubric(public_dir)

        # Safety net: all-pass but no evolution → cap at 0.99
        if all_passed and evolution is None:
            aggregated = min(aggregated, 0.99)
            feedback_lines.append(
                "\nNOTE: All criteria passed but the rubric was not evolved. "
                "Score capped at 0.99. The judge should raise the bar by adding "
                "harder criteria on the next evaluation. Check .claude/rubrics/current.md "
                "for the latest criteria."
            )
            logger.warning(
                "Judge returned perfect score without evolving rubric — "
                "capped at 0.99 to prevent premature stopping"
            )

        state.record_criterion_scores(
            attempt_hash="pending",
            rubric_version=rubric_version,
            criteria_scores=criterion_history,
        )

        header = (
            f"## Evaluation (Rubric v{rubric_version}) — "
            f"{pass_count}/{total_count} criteria passed ({aggregated:.2f} weighted)"
        )
        footer = (
            f"\nWeighted: {aggregated:.2f}  |  Rubric v{rubric_version} "
            f"({total_count} criteria){version_note}"
        )

        feedback = "\n".join([header, ""] + feedback_lines + [footer])

        return ScoreBundle(
            scores=scores,
            aggregated=aggregated,
            is_public=True,
            feedback=feedback,
            metadata={
                "rubric_version": rubric_version,
                "criteria_count": total_count,
            },
        )

    def _apply_evolution(
        self,
        evolution: dict[str, Any],
        state: RubricStateManager,
        current: RubricVersion | None,
    ) -> int:
        """Apply rubric evolution from judge output. Returns the new version number."""
        new_criteria_raw = evolution.get("new_criteria", [])
        refined_raw = evolution.get("refined", [])
        retired_raw = evolution.get("retired", [])
        notes = evolution.get("notes", "")

        active: list[RubricItem] = list(current.rubrics) if current else []
        retired: list[RubricItem] = list(current.retired) if current else []
        version_num = (current.version + 1) if current else 1

        refined_names = set()
        for item in refined_raw:
            name = item.get("name", "")
            if not name or name.startswith("[USER]"):
                continue
            refined_names.add(name)
            for i, r in enumerate(active):
                if r.name == name:
                    active[i] = RubricItem(
                        name=name,
                        description=item.get("description", r.description),
                        weight=float(item.get("weight", r.weight)),
                    )
                    break

        retired_names = {r.get("name", "") for r in retired_raw}
        user_names = {r.name for r in active if r.name.startswith("[USER]")}
        retired_names -= user_names
        newly_retired = [r for r in active if r.name in retired_names]
        active = [r for r in active if r.name not in retired_names]
        retired.extend(newly_retired)

        for item in new_criteria_raw:
            name = item.get("name", "")
            desc = item.get("description", "")
            if name and desc:
                active.append(
                    RubricItem(
                        name=name,
                        description=desc,
                        weight=float(item.get("weight", 1.0)),
                    )
                )

        max_criteria = self.config.args.get("max_criteria", 10)
        active = active[:max_criteria]

        new_version = RubricVersion(
            version=version_num,
            rubrics=active,
            retired=retired,
            trigger="judge",
            evolution_notes=notes,
        )

        task_name = self.config.args.get("task_name", "")
        state.save_version(new_version, task_name=task_name)
        state.record_attempt_version("evolution", version_num)

        return version_num


Grader = AgentJudgeGrader
