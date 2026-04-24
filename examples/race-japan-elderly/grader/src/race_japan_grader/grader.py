"""Strict rubric-based judge grader — spawns a Claude Code judge agent.

Evaluates an agent's written output against a fixed list of rubric criteria by
launching a single-shot judge agent (``claude_code`` by default). The judge
reads the agent's output, the reference article(s), and the rubric, then emits
a structured ``evaluation.json`` with per-criterion PASS/FAIL verdicts.

Config args (read from ``grader.args`` in task.yaml):

- ``runtime``: Agent runtime to spawn the judge in (default: ``claude_code``).
- ``judge_model``: Model id for the judge (default: ``opus``).
- ``judge_max_turns``: Max reasoning turns for the judge (default: 30).
- ``reference_files``: Reference docs the judge cross-checks claims against.
  Resolved from the grader package's ``references/`` directory first, then
  from ``.coral/private/``.
- ``rubrics``: Hidden rubrics (take precedence over ``task.rubrics``). Used by
  the baseline condition to keep criteria out of CORAL.md.
- ``files``: Agent output files to evaluate (default: all ``*.md`` in the
  codebase except ``CORAL.md``).
- ``feedback_level``: ``full`` | ``aggregate_only`` | ``score_only`` —
  controls how much detail is surfaced back to the worker agent.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from coral.config import CoralConfig, GraderConfig, RubricItem
from coral.grader.task_grader import TaskGrader
from coral.types import Score, ScoreBundle

logger = logging.getLogger(__name__)


class StrictRubricJudgeGrader(TaskGrader):
    """Static rubric grader backed by a Claude Code judge agent."""

    def __init__(self, config: GraderConfig) -> None:
        super().__init__(config)
        self._rubrics: list[RubricItem] = []
        self._task_description_from_config: str = ""

    def _load_rubrics_from_config(self) -> None:
        """Prefer ``grader.args.rubrics`` (hidden), then ``task.rubrics``."""
        if self._rubrics:
            return

        private_rubrics = self.config.args.get("rubrics") or []
        if private_rubrics:
            self._rubrics = [
                RubricItem(
                    name=r["name"],
                    description=r.get("description", ""),
                    weight=float(r.get("weight", 1.0)),
                )
                for r in private_rubrics
            ]

        config_path = Path(self.private_dir).parent / "config.yaml"
        if not config_path.exists():
            logger.warning(f"No config.yaml at {config_path}; rubrics list is empty.")
            return
        try:
            full = CoralConfig.from_yaml(config_path)
        except Exception as exc:
            logger.warning(f"Could not load {config_path}: {exc}")
            return
        if not self._rubrics:
            self._rubrics = list(full.task.rubrics)
        self._task_description_from_config = full.task.description or ""

    def evaluate(self) -> ScoreBundle:
        """Spawn the judge agent, wait for its evaluation.json, parse, redact."""
        from coral.agent.registry import get_runtime
        from coral.workspace.worktree import setup_shared_state

        self._load_rubrics_from_config()
        if not self._rubrics:
            return self.fail(
                "No rubric criteria configured",
                feedback="No rubric criteria configured in task.rubrics or grader.args.rubrics.",
            )

        runtime_name = self.config.args.get("runtime", "claude_code")
        runtime = get_runtime(runtime_name)
        model = self.config.args.get("judge_model", "opus")
        max_turns = self.config.args.get("judge_max_turns", 30)

        judge_dir = Path(self.private_dir) / "race_judge"
        workspace = judge_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        log_dir = judge_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        output_path = workspace / "evaluation.json"
        if output_path.exists():
            output_path.unlink()

        codebase_link = workspace / "codebase"
        if codebase_link.is_symlink():
            codebase_link.unlink()
        if not codebase_link.exists():
            codebase_link.symlink_to(Path(self.codebase_path).resolve())

        task_description = self.config.args.get(
            "task_description", self._task_description_from_config
        )
        reference_context = self._read_reference_documents()
        files = self.config.args.get("files", [])

        judge_md = self._build_judge_instructions(
            task_description=task_description,
            reference_context=reference_context,
            files=files,
            output_path=output_path,
        )
        instruction_path = workspace / runtime.instruction_filename
        instruction_path.write_text(judge_md)

        (workspace / ".coral_agent_id").write_text("race-judge")
        coral_dir = Path(self.private_dir).parent
        (workspace / ".coral_dir").write_text(str(coral_dir.resolve()))

        setup_shared_state(workspace, coral_dir, runtime.shared_dir_name)
        self._setup_judge_permissions(runtime, workspace)

        prompt = (
            "You are the evaluator. Read your instructions carefully — they "
            "contain the task description, the evaluation rubric, and the "
            "reference article. The worker's output files are in ./codebase/. "
            f"Score the worker's output against every criterion and write a "
            f"JSON evaluation to {output_path}."
        )

        handle = runtime.start(
            worktree_path=workspace,
            coral_md_path=instruction_path,
            model=model,
            max_turns=max_turns,
            log_dir=log_dir,
            prompt=prompt,
            prompt_source="start",
        )

        timeout = self.config.timeout or 600
        deadline = time.time() + timeout
        while handle.alive and time.time() < deadline:
            time.sleep(2)

        timed_out = handle.alive
        if timed_out:
            handle.stop()
            return self.fail(
                f"Judge agent timed out after {timeout}s",
                feedback=f"Judge agent did not complete within {timeout}s.",
            )

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

        bundle = self._parse_evaluation(data)
        return self._redact_feedback(bundle)

    def _parse_evaluation(self, data: dict) -> ScoreBundle:
        """Convert the judge's evaluation.json into a ScoreBundle."""
        criteria_data = data.get("criteria") or data.get("evaluations") or []
        criteria_by_name = {c.get("name", ""): c for c in criteria_data if isinstance(c, dict)}

        scores: dict[str, Score] = {}
        feedback_lines = ["## Rubric Evaluation Results (Strict)\n"]
        passed_count = 0
        total_weight = 0.0
        weighted_sum = 0.0

        for rubric in self._rubrics:
            entry = criteria_by_name.get(rubric.name, {})
            verdict_raw = entry.get("verdict") or entry.get("pass")
            if isinstance(verdict_raw, bool):
                verdict = "PASS" if verdict_raw else "FAIL"
            else:
                verdict = str(verdict_raw or "FAIL").upper()
                verdict = "PASS" if verdict in {"PASS", "TRUE", "YES"} else "FAIL"
            rationale = entry.get("rationale") or entry.get("explanation") or ""
            explanation = _extract_short_explanation(rationale) if rationale else (
                "No rationale returned by judge"
            )

            value = 1.0 if verdict == "PASS" else 0.0
            scores[rubric.name] = Score(
                value=value,
                name=rubric.name,
                explanation=explanation,
                metadata={"rationale": rationale} if rationale else {},
            )
            if verdict == "PASS":
                passed_count += 1
                mark = "\u2713"
            else:
                mark = "\u2717"
            feedback_lines.append(
                f"{mark} {rubric.name} ({rubric.weight}): {verdict} \u2014 {explanation}"
            )
            weighted_sum += value * rubric.weight
            total_weight += rubric.weight

        aggregated = weighted_sum / total_weight if total_weight > 0 else 0.0
        feedback_lines.append(
            f"\nScore: {passed_count}/{len(self._rubrics)} criteria passed ({aggregated:.2f})"
        )

        return ScoreBundle(
            scores=scores,
            aggregated=aggregated,
            is_public=True,
            feedback="\n".join(feedback_lines),
        )

    def _redact_feedback(self, bundle: ScoreBundle) -> ScoreBundle:
        """Redact per-criterion details based on ``feedback_level``."""
        level = self.config.args.get("feedback_level", "full")
        if level == "full":
            return bundle
        if level == "score_only":
            for score in bundle.scores.values():
                score.explanation = None
            return ScoreBundle(
                scores=bundle.scores,
                aggregated=bundle.aggregated,
                is_public=bundle.is_public,
                feedback=f"Score: {bundle.aggregated:.4f}",
            )
        if level == "aggregate_only":
            passed = sum(1 for s in bundle.scores.values() if s.value == 1.0)
            total = len(bundle.scores)
            for score in bundle.scores.values():
                score.explanation = None
            return ScoreBundle(
                scores=bundle.scores,
                aggregated=bundle.aggregated,
                is_public=bundle.is_public,
                feedback=f"Score: {passed}/{total} criteria passed ({bundle.aggregated:.2f})",
            )
        return bundle

    def _read_reference_documents(self) -> str:
        """Read reference documents. Package-local first, then ``.coral/private/``."""
        ref_files = self.config.args.get("reference_files", [])
        if not ref_files:
            return ""

        package_refs = Path(__file__).parent / "references"
        parts = []
        for filename in ref_files:
            filepath = package_refs / filename
            if not filepath.exists():
                filepath = Path(self.private_dir) / filename
            if filepath.exists():
                content = filepath.read_text()
                max_chars = 80_000
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n\n[... TRUNCATED due to size ...]"
                parts.append(f"### {filename}\n{content}")
            else:
                logger.warning(f"Reference file not found: {filename}")

        return "\n\n".join(parts) if parts else ""

    def _build_judge_instructions(
        self,
        task_description: str,
        reference_context: str,
        files: list[str],
        output_path: Path,
    ) -> str:
        """Assemble the JUDGE.md / CLAUDE.md content for the judge agent."""
        files_section = (
            "\n".join(f"- `./codebase/{f}`" for f in files)
            if files
            else "- All `*.md` files in `./codebase/` (excluding `CORAL.md`)"
        )

        rubric_lines = []
        for i, r in enumerate(self._rubrics, 1):
            rubric_lines.append(
                f"{i}. **{r.name}** (weight {r.weight}) — {r.description}"
            )
        rubric_block = "\n".join(rubric_lines)

        reference_section = (
            f"\n## Reference Article(s)\n\n{reference_context}\n"
            if reference_context
            else ""
        )

        return f"""\
# Judge Instructions

You are an expert evaluator grading an AI agent's written report against a fixed
rubric. You have read-only access to the worker's output under `./codebase/` and
(optionally) to reference articles inlined below.

## Original Task

{task_description}

## Files to Evaluate

{files_section}
{reference_section}
## Evaluation Rubric

Score the agent's output against every criterion below. Each criterion is
PASS/FAIL (binary). Be strict — partial fulfilment is FAIL. Cross-check claims
against the reference article where provided; unsupported assertions are not
sufficient evidence.

{rubric_block}

## Grading Principles

- Focus on what each criterion asks — nothing more, nothing less.
- Conjunctive requirements ("X AND Y") need every component verified.
- Match the specificity level of the criterion; a broader term does not satisfy
  a request for a specific one, and vice versa.
- Formatting differences are acceptable if substantively correct (e.g. `$153.5`
  and `$153.50`).
- If reference documents are provided and the agent's claims contradict them,
  the criterion is FAIL.

## Output Format

When you are done, write a JSON file to `{output_path}` with exactly this
schema:

```json
{{
  "criteria": [
    {{
      "name": "<criterion name exactly as listed above>",
      "verdict": "PASS" | "FAIL",
      "rationale": "<2-3 sentence explanation grounded in the agent's output>"
    }}
  ]
}}
```

Include one entry per criterion, in the same order as the rubric above. Names
must match exactly so the grader can map verdicts back to rubric entries.

Do not write any other file. Once `evaluation.json` is written, stop.
"""

    def _setup_judge_permissions(self, runtime, workspace: Path) -> None:
        """Write Claude Code settings.json allowing edits inside the workspace."""
        if runtime.shared_dir_name != ".claude":
            return
        settings_dir = workspace / ".claude"
        settings_dir.mkdir(exist_ok=True)
        workspace_str = str(workspace.resolve())
        codebase_str = str(Path(self.codebase_path).resolve())
        settings = {
            "permissions": {
                "allow": [
                    f"Read({codebase_str}/**)",
                    f"Read({workspace_str}/**)",
                    f"Write({workspace_str}/evaluation.json)",
                    f"Edit({workspace_str}/evaluation.json)",
                ],
                "deny": [
                    f"Write({codebase_str}/**)",
                    f"Edit({codebase_str}/**)",
                ],
            }
        }
        (settings_dir / "settings.json").write_text(json.dumps(settings, indent=2))


def _extract_short_explanation(rationale: str) -> str:
    """Extract a 1-2 sentence explanation from a structured rationale."""
    if not rationale:
        return "No explanation provided"
    lower = rationale.lower()
    for marker in ["## assessment", "**assessment**", "assessment:", "conclusion:"]:
        idx = lower.find(marker)
        if idx != -1:
            after = rationale[idx + len(marker):].strip()
            if after.startswith("\n"):
                after = after.lstrip("\n")
            sentences = after.split(". ")
            short = ". ".join(sentences[:2])
            if short and not short.endswith("."):
                short += "."
            return short[:300] if short else rationale[:200]
    sentences = rationale.rstrip().split(". ")
    short = ". ".join(sentences[-2:])
    return short[:300] if short else rationale[:200]


Grader = StrictRubricJudgeGrader
