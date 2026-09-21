"""AgenticEvaluator: a persistent evaluator agent with Playwright MCP for
scoring generator output against task-configurable criteria.

Architecture mirrors `apex_judge`:

1. Spawn a Claude Code subprocess in an isolated workspace
2. Symlink the worker's codebase read-only at `./codebase/`
3. Serve the codebase over HTTP so the evaluator can browse it via Playwright
4. Pass a `.mcp.json` to the runtime so the evaluator gets the Playwright server
5. Evaluator writes per-criterion numeric scores + critique to `evaluation.json`
6. Grader parses, returns ScoreBundle with weighted aggregate

Differs from `apex_judge` in three ways:
- Numeric 0.0-1.0 scoring per criterion (not PASS/FAIL) so the generator has a gradient
- Adds Playwright MCP + a live HTTP server for the frontend under evaluation
- No rubric evolution — the criteria come from `task.yaml` and stay fixed

Config args (`grader.args` in task.yaml):

- `evaluator_model`: model for the evaluator (default: "sonnet" — the bare
  alias, matching CORAL's own runtime-registry convention, so this tracks
  whatever Sonnet currently resolves to instead of going stale the way a
  dated model ID does; the `claude` CLI resolves the alias itself)
- `evaluator_max_turns`: max turns (default: 30)
- `serve_port`: HTTP port (0 = ephemeral, default 0)
- `criteria`: list of {name, weight, description, fail_examples?}
- `evaluation_instructions`: optional task-specific protocol text (templated with `{url}`)
- `mcp_servers`: optional dict overriding the default {playwright: ...}
- `evolution.evidence_max_screenshots`: screenshots retained per attempt (default 20)
- `evolution.evidence_max_source_files`: artifact text files retained (default 120)
- `evolution.evidence_max_source_bytes`: total artifact text bytes retained (default 750000)
- `session_persistent`: bool, default True. When True the evaluator resumes
  its session across evals (apex_judge-style memory). For fixed-criteria
  tasks this causes the evaluator to anchor on prior scores — set to False
  for a fresh evaluator per eval (a persistent one anchors on its own prior scores).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from agentic_evaluator.evaluator_md import generate_evaluator_md
from agentic_evaluator.http_server import serve_codebase
from coral.config import GraderConfig
from coral.grader.task_grader import TaskGrader
from coral.types import Score, ScoreBundle

#: Pinned so every evaluation in a run, and every run in a comparison, drives the
#: same browser tooling. Bump deliberately, never through @latest.
PLAYWRIGHT_MCP_VERSION = "0.0.80"

logger = logging.getLogger(__name__)

_MIN_NODE_MAJOR = 20


def _find_npx() -> str:
    """Return a path to an `npx` whose `node` is >=20.

    Current Playwright refuses to run on Node <20 ("Playwright requires
    Node.js 20 or higher"); this used to be 18 but Playwright's own minimum
    has since moved. A stale threshold here is a real failure mode, not a
    theoretical one: on a machine with a Node 18 install earlier in PATH than
    a working Node 20+ (e.g. a homebrew-managed /usr/local/bin/node next to
    an nvm-managed one), the old `>= 18` check happily accepted the Node 18
    binary, the MCP server then failed to start, and the evaluator's own
    error handling made this look like intermittent flakiness rather than a
    deterministic version mismatch. The user may have an older Node first
    in PATH (e.g. nvm's default, or homebrew's), so we probe candidates and
    return the absolute path. Falls back to bare ``npx`` if no candidate
    found — the grader will surface a clear error if MCP fails to start.
    """
    candidates: list[Path] = []
    if path_env := os.environ.get("PATH"):
        for d in path_env.split(os.pathsep):
            candidate = Path(d) / "npx"
            if candidate.exists():
                candidates.append(candidate)
    nvm_dir = Path.home() / ".nvm" / "versions" / "node"
    if nvm_dir.is_dir():
        # newest first
        for d in sorted(nvm_dir.iterdir(), reverse=True):
            candidate = d / "bin" / "npx"
            if candidate.exists():
                candidates.append(candidate)

    seen: set[str] = set()
    for npx in candidates:
        key = str(npx.resolve())
        if key in seen:
            continue
        seen.add(key)
        node = npx.parent / "node"
        if not node.exists():
            continue
        try:
            out = subprocess.run(
                [str(node), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        m = re.match(r"v(\d+)", out.stdout.strip())
        if not m:
            continue
        if int(m.group(1)) >= _MIN_NODE_MAJOR:
            logger.info(f"agentic_evaluator: using npx at {npx} (node {out.stdout.strip()})")
            return str(npx)

    logger.warning(
        f"agentic_evaluator: could not find npx with node>={_MIN_NODE_MAJOR}; "
        "falling back to bare 'npx'. Playwright MCP will likely fail."
    )
    return "npx"


def _default_mcp_servers() -> dict[str, Any]:
    npx = _find_npx()
    node_bin_dir = str(Path(npx).parent)
    return {
        "playwright": {
            "command": npx,
            "args": ["-y", f"@playwright/mcp@{PLAYWRIGHT_MCP_VERSION}"],
            # Ensure the spawned MCP server resolves the same node binary
            "env": {
                "PATH": f"{node_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            },
        },
    }


class AgenticEvaluator(TaskGrader):
    """Grader that spawns an evaluator agent with Playwright MCP."""

    def __init__(self, config: GraderConfig) -> None:
        super().__init__(config)

    # ---- optional hooks for coral.grader.evolution.EvolvingTaskGrader --------
    # These keep evaluator-specific knowledge (where this grader writes its
    # transcript, what its own failure messages mean) out of the generic
    # evolution module.

    def evaluator_log_path(self, attempt_id: str) -> Path:
        return Path(self.private_dir) / "evaluator" / attempt_id / "logs" / "evaluator.0.log"

    def evolution_evidence_dir(self, attempt_id: str) -> Path:
        """Persistent artifact/evaluation evidence for rubric evolution.

        This is deliberately private: generator agents must not see hidden
        evaluator state, while the framework-owned proposer may receive it as
        its treatment input.
        """
        return Path(self.private_dir) / "evaluator" / attempt_id / "evidence"

    def classify_failure(self, bundle: ScoreBundle, log_info: dict[str, Any]):
        """Map this grader's own self.fail() messages to a FailureCode.
        Returns None to defer to the generic classifier."""
        from coral.grader.evolution.failures import FailureCode

        text = " ".join(
            [bundle.feedback or ""] + [s.explanation or "" for s in (bundle.scores or {}).values()]
        ).casefold()
        if "playwright" in text and (
            "unavailable" in text or "could not connect" in text or "could not use" in text
        ):
            return FailureCode.PLAYWRIGHT_UNAVAILABLE
        if any(
            k in text
            for k in (
                "did not write",
                "did not produce an evaluation",
                "not valid json",
                "invalid evaluation.json",
                "no criteria scores",
                "no criteria entries",
                "no criteria configured",
            )
        ):
            return FailureCode.INVALID_OUTPUT
        return None

    # ---- TaskGrader API -------------------------------------------------

    def evaluate(self) -> ScoreBundle:
        from coral.agent.registry import get_runtime

        runtime_name = self.args.get("runtime", "claude_code")
        runtime = get_runtime(runtime_name)
        model = self.args.get("evaluator_model", "sonnet")
        max_turns = int(self.args.get("evaluator_max_turns", 30))
        serve_port = int(self.args.get("serve_port", 0))
        # session_persistent: when True (default for apex_judge compatibility),
        # the evaluator agent's session is resumed across evals. Useful for
        # rubric-evolution tasks where the judge accumulates context. For
        # fixed-criteria tasks (like frontend evaluation) this causes the
        # evaluator to anchor on prior scores — set to False for a fresh
        # evaluator per attempt: a persistent one anchors on its own prior scores.
        session_persistent = bool(self.args.get("session_persistent", True))

        criteria = self.args.get("criteria") or []
        if not criteria:
            return self.fail(
                "No criteria configured",
                feedback="grader.args.criteria must be a non-empty list.",
            )

        # 1. Prepare evaluator workspace
        # Keyed by commit hash, not shared across attempts: grader.parallel.
        # max_workers > 1 grades multiple attempts concurrently (each in its
        # own subprocess, but all handed the same self.private_dir), so a
        # fixed "evaluator/workspace" here meant concurrent evaluator agents
        # raced on the same evaluation.json/.mcp.json/workspace dir and
        # clobbered each other — caught via a real 4-agent, max_workers=4 run
        # where 3 of 6 attempts came back "did not write evaluation.json".
        # session_id_path below stays un-keyed: session_persistent=True is a
        # serial-only feature (resuming one evaluator conversation across
        # sequential attempts) and isn't meaningful under concurrent grading.
        evaluator_dir = Path(self.private_dir) / "evaluator"
        commit_hash = self.tasks[0].metadata.get("commit_hash") if self.tasks else None
        attempt_dir = evaluator_dir / (commit_hash or "shared")
        workspace = attempt_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        log_dir = attempt_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        scratch_dir = workspace / "scratch"
        scratch_dir.mkdir(parents=True, exist_ok=True)
        output_path = workspace / "evaluation.json"

        if output_path.exists():
            output_path.unlink()

        # 2. Symlink codebase read-only at ./codebase/
        codebase_link = workspace / "codebase"
        if codebase_link.is_symlink():
            codebase_link.unlink()
        if not codebase_link.exists():
            codebase_link.symlink_to(Path(self.codebase_path).resolve())

        # 3. Serve the generated frontend on a local port
        port, stop_server = serve_codebase(
            Path(self.codebase_path).resolve(),
            port=serve_port,
        )
        url = f"http://127.0.0.1:{port}/"

        try:
            # 4. Generate EVALUATOR.md (written as CLAUDE.md for the runtime)
            task_name, task_description = self._read_task_metadata()
            evaluation_instructions = self._format_evaluation_instructions(url, scratch_dir)
            md_content = generate_evaluator_md(
                task_name=task_name,
                task_description=task_description,
                url=url,
                criteria=criteria,
                output_path=str(output_path),
                scratch_dir=str(scratch_dir),
                evaluation_instructions=evaluation_instructions,
            )
            instruction_path = workspace / runtime.instruction_filename
            instruction_path.write_text(md_content)

            # 5. Metadata for the runtime
            (workspace / ".coral_agent_id").write_text("evaluator")
            coral_dir = Path(self.private_dir).parent
            (workspace / ".coral_dir").write_text(str(coral_dir.resolve()))

            # 6. .mcp.json with Playwright (or user-overridden servers)
            mcp_servers = self.args.get("mcp_servers") or _default_mcp_servers()
            mcp_config_path = workspace / ".mcp.json"
            mcp_config_path.write_text(
                json.dumps({"mcpServers": mcp_servers}, indent=2) + "\n",
            )

            # 7. Permissions (Claude Code uses .claude/settings.local.json)
            self._setup_permissions(runtime, workspace)

            # 8. Session persistence (gated by session_persistent flag)
            session_id_path = evaluator_dir / "session_id"
            resume_session_id = (
                self._load_session_id(session_id_path) if session_persistent else None
            )
            prompt, prompt_source = self._build_prompt(
                output_path,
                url,
                resume_session_id is not None,
            )

            # 9. Spawn the evaluator agent
            handle = runtime.start(
                worktree_path=workspace,
                coral_md_path=instruction_path,
                model=model,
                max_turns=max_turns,
                log_dir=log_dir,
                prompt=prompt,
                prompt_source=prompt_source,
                resume_session_id=resume_session_id,
                runtime_options={
                    "add_dirs": [str(Path(self.codebase_path).resolve())],
                    "mcp_config": str(mcp_config_path),
                },
            )

            # 10. Wait for completion
            timeout = self.config.timeout or 900
            deadline = time.time() + timeout
            while handle.alive and time.time() < deadline:
                time.sleep(2)

            timed_out = handle.alive
            if timed_out:
                handle.stop()

            # 11. Save new session ID (only when persistence is enabled)
            if session_persistent:
                new_session_id = runtime.extract_session_id(handle.log_path)
                if new_session_id:
                    self._save_session_id(session_id_path, new_session_id)

            if timed_out:
                return self.fail(
                    f"Evaluator timed out after {timeout}s",
                    feedback=f"Evaluator did not complete within {timeout}s.",
                )

            # 12. Parse evaluation.json
            if not output_path.exists():
                return self.fail(
                    "Evaluator did not write evaluation.json",
                    feedback=(
                        "The evaluator agent completed but did not produce an "
                        "evaluation output file. Check evaluator logs."
                    ),
                )

            try:
                data = json.loads(output_path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                return self.fail(
                    f"Invalid evaluation.json: {e}",
                    feedback=f"Evaluator output was not valid JSON: {e}",
                )

            # If the evaluator couldn't get Playwright working, it now reports
            # that explicitly instead of silently scoring from source alone (a
            # degraded critique that looked like a normal score but was quietly
            # missing signal on Craft/Functionality — see evaluator.md.template).
            # Fail loudly the same way a missing/invalid output file does,
            # rather than recording a real-looking score built on a blind read.
            if data.get("error") == "playwright_unavailable":
                return self.fail(
                    "Evaluator could not connect to Playwright",
                    feedback=(
                        "The evaluator reported it could not use Playwright and "
                        "declined to score from source alone: "
                        f"{data.get('detail', 'no detail given')}"
                    ),
                )

            bundle = self._build_score_bundle(data, criteria)
            if bundle.aggregated is not None:
                self._persist_evolution_evidence(
                    data=data,
                    workspace_dir=workspace,
                    attempt_dir=attempt_dir,
                )
            return bundle

        finally:
            # 13. Tear down HTTP server + scratch (keep workspace for next eval)
            stop_server()
            shutil.rmtree(scratch_dir, ignore_errors=True)
            scratch_dir.mkdir(parents=True, exist_ok=True)

    # ---- helpers --------------------------------------------------------

    def _persist_evolution_evidence(
        self,
        *,
        data: dict[str, Any],
        workspace_dir: Path,
        attempt_dir: Path,
    ) -> Path:
        """Preserve a bounded, deterministic view of the evaluated artifact.

        The evaluator workspace's scratch directory is intentionally deleted
        after each grade, and the daemon later removes the submitted checkout.
        Without this copy, screenshots and source evidence no longer exist by
        the time an adaptive trigger fires on a later attempt.

        Called before the scratch teardown in the caller's ``finally`` block,
        so anything the evaluator did leave in scratch is still present.
        """
        evidence_dir = attempt_dir / "evidence"
        if evidence_dir.exists():
            shutil.rmtree(evidence_dir)
        evaluation_dir = evidence_dir / "evaluation"
        screenshots_dir = evidence_dir / "screenshots"
        artifact_dir = evidence_dir / "artifact"
        for directory in (evaluation_dir, screenshots_dir, artifact_dir):
            directory.mkdir(parents=True, exist_ok=True)

        evaluation_path = evaluation_dir / "evaluation.json"
        evaluation_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

        evo_cfg = self.args.get("evolution") or {}
        max_screenshots = int(evo_cfg.get("evidence_max_screenshots", 20))
        max_source_files = int(evo_cfg.get("evidence_max_source_files", 120))
        max_source_bytes = int(evo_cfg.get("evidence_max_source_bytes", 750_000))
        source_suffixes = {
            ".css",
            ".html",
            ".js",
            ".json",
            ".jsx",
            ".md",
            ".svg",
            ".ts",
            ".tsx",
            ".txt",
            ".yaml",
            ".yml",
        }
        excluded_parts = {
            ".git",
            ".next",
            ".venv",
            "build",
            "coverage",
            "dist",
            "node_modules",
        }

        captured: list[dict[str, Any]] = []

        def record(path: Path, kind: str) -> None:
            captured.append(
                {
                    "path": path.relative_to(evidence_dir).as_posix(),
                    "kind": kind,
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )

        record(evaluation_path, "evaluation")

        # Search the whole evaluator workspace, not just scratch/. The
        # instructions offer scratch_dir as a save location but do not enforce
        # it, and in practice the evaluator writes screenshots into its cwd --
        # the workspace root -- so a scratch-only scan captured zero images on
        # every attempt of the pilot. `codebase` is a symlink to the submitted
        # checkout: its images are the artifact's own assets, not evaluation
        # evidence, and following it would also escape the workspace.
        screenshot_candidates = sorted(
            p
            for p in workspace_dir.rglob("*")
            if p.is_file()
            and not p.is_symlink()
            and p.suffix.casefold() in {".jpeg", ".jpg", ".png", ".webp"}
            and "codebase" not in p.relative_to(workspace_dir).parts
        )
        for index, source in enumerate(screenshot_candidates[:max_screenshots]):
            # Prefixing the relative path avoids collisions between tools that
            # create the same basename in different workspace subdirectories.
            rel = source.relative_to(workspace_dir)
            safe_name = "__".join(rel.parts)
            target = screenshots_dir / f"{index:02d}-{safe_name}"
            shutil.copy2(source, target)
            record(target, "screenshot")

        source_candidates = sorted(
            p
            for p in Path(self.codebase_path).rglob("*")
            if p.is_file()
            and not p.is_symlink()
            and p.suffix.casefold() in source_suffixes
            and not excluded_parts.intersection(p.relative_to(self.codebase_path).parts)
            and p.name not in {"package-lock.json", "pnpm-lock.yaml"}
        )
        source_bytes = 0
        source_count = 0
        omitted_for_budget = 0
        for source in source_candidates:
            size = source.stat().st_size
            if source_count >= max_source_files or source_bytes + size > max_source_bytes:
                omitted_for_budget += 1
                continue
            rel = source.relative_to(self.codebase_path)
            target = artifact_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            record(target, "artifact_source")
            source_count += 1
            source_bytes += size

        manifest = {
            "schema": 1,
            "attempt_id": attempt_dir.name,
            "files": captured,
            "capture": {
                "screenshots_found": len(screenshot_candidates),
                "screenshots_saved": min(len(screenshot_candidates), max_screenshots),
                "source_candidates": len(source_candidates),
                "source_files_saved": source_count,
                "source_bytes_saved": source_bytes,
                "source_files_omitted_for_budget": omitted_for_budget,
                "limits": {
                    "max_screenshots": max_screenshots,
                    "max_source_files": max_source_files,
                    "max_source_bytes": max_source_bytes,
                },
            },
        }
        (evidence_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        return evidence_dir

    def _read_task_metadata(self) -> tuple[str, str]:
        """Pull task name/description from the CORAL config on disk."""
        config_path = Path(self.private_dir).parent / "config.yaml"
        name = self.args.get("task_name", "")
        desc = self.args.get("task_description", "")
        if config_path.exists():
            from coral.config import CoralConfig

            try:
                cfg = CoralConfig.from_yaml(config_path)
                name = name or cfg.task.name
                desc = desc or cfg.task.description
            except Exception:
                pass
        return name, desc

    def _format_evaluation_instructions(self, url: str, scratch_dir: Path | None = None) -> str:
        raw = self.args.get("evaluation_instructions") or ""
        try:
            return raw.format(url=url, scratch_dir=str(scratch_dir) if scratch_dir else "")
        except (KeyError, IndexError):
            # If the task author used braces in non-format-safe ways, return as-is.
            return raw

    def _build_prompt(
        self,
        output_path: Path,
        url: str,
        resuming: bool,
    ) -> tuple[str, str]:
        if resuming:
            return (
                (
                    "A new version of the worker's frontend is available at "
                    f"{url}. Your instructions in CLAUDE.md have been updated. "
                    "Re-read them, browse the new page with Playwright, and "
                    f"write your evaluation to {output_path}."
                ),
                "resume",
            )
        return (
            (
                "You are the evaluator. Read CLAUDE.md for the task description, "
                "criteria, and protocol. Then use the Playwright MCP tools to "
                f"navigate the live page at {url}, take screenshots, interact "
                "with the UI, and score each criterion. Write your evaluation "
                f"to {output_path}."
            ),
            "start",
        )

    def _setup_permissions(self, runtime: Any, workspace: Path) -> None:
        """Write .claude/settings.local.json for Claude Code.

        Must be settings.local.json, not settings.json: CORAL's own worktree
        setup (coral/workspace/worktree.py) writes required, always-honored
        permission scoping to settings.local.json and reserves settings.json
        for user-supplied config that Claude Code merges on top. A plain
        settings.json here does not get the same trust — its allow-list
        (in particular the `mcp__playwright__*` wildcard) was silently not
        being applied, so the evaluator would ask permission for every
        Playwright tool call and fail after the retry budget ran out. That
        looked exactly like a Playwright connection failure from the
        outside, which is why it took a repro harness to tell the two apart.
        """
        if runtime.shared_dir_name != ".claude":
            return

        settings_dir = workspace / runtime.shared_dir_name
        settings_dir.mkdir(exist_ok=True)

        workspace_str = str(workspace.resolve())
        codebase_str = str(Path(self.codebase_path).resolve())

        settings = {
            "permissions": {
                "defaultMode": "auto",
                "allow": [
                    "Bash",
                    f"Read({workspace_str}/**)",
                    f"Read({codebase_str}/**)",
                    f"Edit({workspace_str}/**)",
                    f"Write({workspace_str}/**)",
                    # MCP tools: Playwright exposes mcp__playwright__*
                    "mcp__playwright__*",
                    # Allow agent to fetch screenshots etc. if needed
                    "WebFetch",
                ],
                "deny": [
                    "Bash(git *)",
                    "Bash(coral eval*)",
                    f"Edit({codebase_str}/**)",
                    f"Write({codebase_str}/**)",
                ],
            },
            "enableAllProjectMcpServers": True,
        }

        (settings_dir / "settings.local.json").write_text(
            json.dumps(settings, indent=2) + "\n",
        )

    @staticmethod
    def _load_session_id(path: Path) -> str | None:
        if path.exists():
            sid = path.read_text().strip()
            if sid:
                return sid
        return None

    @staticmethod
    def _save_session_id(path: Path, session_id: str) -> None:
        path.write_text(session_id)

    def _build_score_bundle(
        self,
        data: dict[str, Any],
        configured_criteria: list[dict[str, Any]],
    ) -> ScoreBundle:
        """Parse evaluation.json into a ScoreBundle with weighted numeric scoring.

        **Fail-closed.** The evaluator is an LLM writing JSON; every deviation
        from the configured rubric is rejected rather than repaired, and the
        caller's same-snapshot retry gets a chance to produce a valid one. The
        previous lenient version silently accepted all of the following, each
        of which produces a number that is not the score the rubric defines:

        * an output containing only an *unknown* criterion scored 1.0
          aggregated to **1.0** — a perfect score for answering a question
          nobody asked;
        * a *missing* criterion was dropped and the rest renormalised, so
          scoring well on one criterion and skipping the rest also gave 1.0;
        * a *duplicated* criterion was counted twice in the aggregate while
          only the last copy appeared in ``scores``, so the reported breakdown
          did not reconcile with the reported total;
        * an *evaluator-supplied* ``weight`` overrode the configured one, so
          the evaluator could re-weight its own rubric (weight 999 on one
          criterion moved the aggregate to 0.999);
        * a string, ``NaN``, or out-of-range score was coerced or clamped into
          a plausible-looking number instead of being reported as broken.

        Silently-wrong scores are worse than missing ones: a failed evaluation
        is visible in the failure taxonomy, whereas a coerced 0.0 enters the
        rubric's own evidence base as if it were a real observation.
        """
        entries = data.get("criteria") or data.get("criteria_scores") or []
        if not entries:
            return self.fail(
                "No criteria scores in evaluator output",
                feedback="Evaluator produced evaluation.json but it contained no criteria entries.",
            )

        # Validate the *configured* rubric first: a duplicated name or a
        # non-positive weight would make any aggregate meaningless, and that is
        # a task-authoring bug, not an evaluator failure.
        configured_weight: dict[str, float] = {}
        for c in configured_criteria:
            name = c.get("name")
            if not name or name in configured_weight:
                return self.fail(
                    "Invalid rubric configuration",
                    feedback=f"Configured criteria must have unique, non-empty names; saw {name!r}.",
                )
            try:
                w = float(c.get("weight", 1.0))
            except (TypeError, ValueError):
                w = float("nan")
            if not math.isfinite(w) or w <= 0:
                return self.fail(
                    "Invalid rubric configuration",
                    feedback=f"Criterion {name!r} has weight {c.get('weight')!r}; "
                    "weights must be finite and positive.",
                )
            configured_weight[name] = w

        # Exact coverage: every configured criterion once, and nothing else.
        seen: list[str] = [e.get("name") for e in entries]
        duplicates = sorted({n for n in seen if seen.count(n) > 1})
        unknown = sorted({n for n in seen if n not in configured_weight})
        missing = sorted(n for n in configured_weight if n not in seen)
        if duplicates or unknown or missing:
            parts = []
            if missing:
                parts.append(f"missing {missing}")
            if unknown:
                parts.append(f"unknown {unknown}")
            if duplicates:
                parts.append(f"duplicated {duplicates}")
            return self.fail(
                "Evaluator output does not match the configured criteria",
                feedback=(
                    "Evaluator must score every configured criterion exactly once. "
                    + "; ".join(parts)
                    + f". Configured: {sorted(configured_weight)}."
                ),
            )

        scores: dict[str, Score] = {}
        feedback_lines: list[str] = []
        total_weight = 0.0
        earned_weight = 0.0

        for entry in entries:
            name = entry["name"]
            raw_score = entry.get("score")
            # Reject rather than coerce. bool is a subclass of int, so an
            # explicit check keeps `true` from silently becoming 1.0.
            if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
                return self.fail(
                    "Invalid criterion score",
                    feedback=f"Criterion {name!r} has score {raw_score!r}; "
                    "scores must be numbers in [0, 1].",
                )
            value = float(raw_score)
            if not math.isfinite(value) or not (0.0 <= value <= 1.0):
                return self.fail(
                    "Invalid criterion score",
                    feedback=f"Criterion {name!r} has score {raw_score!r}; "
                    "scores must be finite and within [0, 1].",
                )

            # Configured weight only. The evaluator does not get to re-weight
            # the rubric it is being asked to apply.
            weight = configured_weight[name]
            rationale = (entry.get("rationale") or "").strip()
            evidence = entry.get("evidence") or []

            scores[name] = Score(
                value=value,
                name=name,
                explanation=rationale or None,
            )

            total_weight += weight
            earned_weight += value * weight

            evidence_str = f" [{', '.join(evidence)}]" if evidence else ""
            feedback_lines.append(
                f"- **{name}** (weight {weight}): **{value:.2f}**{evidence_str}\n  {rationale}"
            )

        aggregated = earned_weight / total_weight
        overall_critique = (data.get("overall_critique") or "").strip()

        header = (
            f"## Evaluator Score: **{aggregated:.3f}**  ({len(entries)} criteria, weighted avg)"
        )
        sections = [header, ""]
        sections.extend(feedback_lines)
        if overall_critique:
            sections.append("")
            sections.append("### Overall Critique")
            sections.append(overall_critique)

        return ScoreBundle(
            scores=scores,
            aggregated=aggregated,
            is_public=True,
            feedback="\n".join(sections),
            metadata={
                "criteria_count": len(entries),
                "screenshots_dir": data.get("screenshots_dir"),
            },
        )
