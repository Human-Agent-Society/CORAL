"""Terminal-bench grader — evaluates a solver agent via the harbor CLI.

Runs `harbor run -d terminal-bench@2.0` with the agent's solve.py as a custom
harbor agent, then parses the job result JSON for the pass rate.

Uses tiered evaluation — each `coral eval` runs ONE tier based on the best
raw pass rate seen so far:
  - best < tier1_threshold (0.3) → Tier 1 (5 instances), weight 1
  - best < tier2_threshold (0.7) → Tier 2 (30 instances), weight 10
  - best ≥ tier2_threshold       → Tier 3 (all instances), weight 100

The score returned is `tier_weight * pass_rate`, so higher-tier results
naturally dominate the leaderboard regardless of pass rate. The raw pass
rate is preserved in metadata for tier promotion decisions.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from coral.grader import TaskGrader
from coral.hub.attempts import read_attempts
from coral.types import ScoreBundle


class Grader(TaskGrader):
    def _get_best_raw_score(self) -> float | None:
        """Best raw pass rate from previous attempts (drives tier promotion).

        Reads `metadata.raw_score` rather than `score`, since `score` is
        weighted by tier and cannot be compared against the raw thresholds.
        """
        coral_dir = Path(self.private_dir).parent
        best = None
        for a in read_attempts(coral_dir):
            raw = a.metadata.get("raw_score")
            if raw is not None and (best is None or raw > best):
                best = raw
        return best

    def evaluate(self) -> ScoreBundle:
        dataset = self.args.get("dataset", "terminal-bench@2.0")
        n_concurrent = int(self.args.get("n_concurrent", 4))
        tier1_size = int(self.args.get("tier1_size", 5))
        tier1_threshold = float(self.args.get("tier1_threshold", 0.3))
        tier2_size = int(self.args.get("tier2_size", 30))
        tier2_threshold = float(self.args.get("tier2_threshold", 0.7))
        agent_timeout_multiplier = float(self.args.get("agent_timeout_multiplier", 1.0))
        verifier_timeout_multiplier = float(self.args.get("verifier_timeout_multiplier", 1.0))

        # Verify solve.py exists
        solver_path = Path(self.codebase_path) / "solve.py"
        if not solver_path.exists():
            return self.fail(
                "solve.py not found in codebase",
                feedback="Your codebase must contain a solve.py with a SolverAgent class.",
            )

        # Syntax check
        try:
            compile(solver_path.read_text(), str(solver_path), "exec")
        except SyntaxError as e:
            return self.fail(
                f"solve.py has syntax error: {e}",
                feedback=f"Fix the syntax error in solve.py: {e}",
            )

        # Find harbor CLI
        harbor_cmd = self._find_harbor_cmd()
        if not harbor_cmd:
            return self.fail(
                "harbor CLI not found",
                feedback="Install harbor (`uvx harbor --version` to verify) or ensure `uvx` is available.",
            )

        # Determine which tier to run based on best previous raw score
        best_score = self._get_best_raw_score()
        if best_score is None or best_score < tier1_threshold:
            n_tasks, tier_name, tier_weight = tier1_size, "Tier 1", 1
        elif best_score < tier2_threshold:
            n_tasks, tier_name, tier_weight = tier2_size, "Tier 2", 10
        else:
            n_tasks, tier_name, tier_weight = 0, "Tier 3 (full)", 100

        # Persist harbor logs in the per-attempt eval_logs dir so they survive
        # the grader-checkout cleanup (coral/grader/daemon.py:_remove_worktree).
        # Symlinked into each agent worktree at `<shared_dir>/eval_logs/<hash>/harbor_logs/`.
        job_dir = self.eval_logs_dir / "harbor_logs"
        job_dir.mkdir(parents=True, exist_ok=True)
        job_name = f"eval_{tier_name.lower().replace(' ', '_')}_{int(time.time())}"

        start = time.time()
        harbor_result = self._run_harbor(
            harbor_cmd=harbor_cmd,
            dataset=dataset,
            job_dir=job_dir,
            job_name=job_name,
            n_tasks=n_tasks,
            n_concurrent=n_concurrent,
            agent_timeout_multiplier=agent_timeout_multiplier,
            verifier_timeout_multiplier=verifier_timeout_multiplier,
            tier_name=tier_name,
        )

        if isinstance(harbor_result, ScoreBundle):
            return harbor_result

        pass_rate, feedback = harbor_result
        elapsed = time.time() - start
        weighted_score = tier_weight * pass_rate
        explanation = (
            f"{tier_name}: {pass_rate:.1%} pass rate in {elapsed:.0f}s (score={weighted_score:.2f})"
        )
        return self.score(
            weighted_score, explanation, feedback=feedback,
            metadata={"tier_weight": tier_weight, "raw_score": pass_rate},
        )

    def _run_harbor(
        self,
        harbor_cmd: list[str],
        dataset: str,
        job_dir: Path,
        job_name: str,
        n_tasks: int,
        n_concurrent: int,
        agent_timeout_multiplier: float,
        verifier_timeout_multiplier: float,
        tier_name: str = "",
    ) -> tuple[float, str] | ScoreBundle:
        """Run harbor and return (pass_rate, feedback) or a ScoreBundle on error."""
        import os

        cmd = [
            *harbor_cmd,
            "run",
            "-d", dataset,
            "--agent-import-path", "solve:SolverAgent",
            "-o", str(job_dir),
            "--job-name", job_name,
            "-n", str(n_concurrent),
            "--yes",
            "--agent-timeout-multiplier", str(agent_timeout_multiplier),
            "--verifier-timeout-multiplier", str(verifier_timeout_multiplier),
        ]
        if n_tasks > 0:
            cmd.extend(["-l", str(n_tasks)])

        env = {**os.environ, "PYTHONPATH": self.codebase_path}
        timeout = self.timeout or 7200

        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=self.codebase_path,
            )
        except subprocess.TimeoutExpired:
            return self.fail(
                f"Harbor run timed out after {timeout}s",
                feedback=f"Evaluation timed out after {timeout}s.",
            )

        elapsed = time.time() - start
        # Parse results
        result_path = job_dir / job_name / "result.json"
        if not result_path.exists():
            stderr_tail = result.stderr.strip()[-1000:] if result.stderr else ""
            stdout_tail = result.stdout.strip()[-1000:] if result.stdout else ""
            return self.fail(
                f"Harbor run produced no result.json (exit code {result.returncode})",
                feedback=f"Harbor failed.\nstderr: {stderr_tail}\nstdout: {stdout_tail}",
            )

        try:
            job_result = json.loads(result_path.read_text())
        except json.JSONDecodeError as e:
            return self.fail(f"Failed to parse result.json: {e}")

        return self._parse_job_result(job_result, job_dir / job_name, elapsed, tier_name)

    def _parse_job_result(
        self, job_result: dict, job_dir: Path, elapsed: float, tier_name: str = "",
    ) -> tuple[float, str]:
        """Parse harbor job result.json and return (pass_rate, feedback)."""
        n_trials = job_result.get("n_trials", 0)
        n_errors = job_result.get("n_errors", 0)

        if n_trials == 0:
            return (0.0, "No trials completed")

        # Aggregate pass rate from evals
        evals = job_result.get("evals", {})
        total_passed = 0
        total_trials = 0
        reward_details = []

        for eval_key, eval_stats in evals.items():
            eval_n = eval_stats.get("n_trials", 0)
            eval_errors = eval_stats.get("n_errors", 0)
            pass_at_k = eval_stats.get("pass_at_k", {})

            # pass@1 is the primary metric
            pass_rate = pass_at_k.get("1", pass_at_k.get(1, 0.0))

            # Count passed from reward_stats
            reward_stats = eval_stats.get("reward_stats", {})
            for reward_key, value_map in reward_stats.items():
                for value, trial_names in value_map.items():
                    val = float(value)
                    if val > 0:
                        total_passed += len(trial_names)
                    total_trials += len(trial_names)

            reward_details.append(
                f"{eval_key}: pass@1={pass_rate:.1%}, "
                f"trials={eval_n}, errors={eval_errors}"
            )

        # Compute overall pass rate
        if total_trials > 0:
            overall_rate = total_passed / total_trials
        else:
            # Fall back to pass@1 from first eval
            overall_rate = 0.0
            for eval_stats in evals.values():
                p = eval_stats.get("pass_at_k", {})
                overall_rate = p.get("1", p.get(1, 0.0))
                break

        # Build feedback
        lines = [
            f"## Terminal-bench Results ({tier_name}): {overall_rate:.1%} pass rate",
            f"Completed {n_trials} trials in {elapsed:.0f}s "
            f"({n_errors} errors)",
            "",
        ]
        for detail in reward_details:
            lines.append(f"- {detail}")

        # Per-task results
        task_results = self._collect_task_results(job_dir)
        if task_results:
            lines.append("")
            lines.append("### Per-task results")
            for task_name, passed in task_results:
                status = "PASS" if passed else "FAIL"
                lines.append(f"- `{task_name}`: {status}")

        # Per-trial failure details from trial result files
        failure_lines = self._collect_trial_failures(job_dir, max_show=10)
        if failure_lines:
            lines.append("")
            lines.append("### Failure details")
            lines.extend(failure_lines)

        # Point agent to the logs (no shared-dir prefix — runtime-agnostic).
        # eval_logs/ is symlinked into each worktree's shared state dir
        # (.claude/, .codex/, .opencode/, .kiro/) by setup_shared_state, so
        # the agent prepends their own shared-dir to access via Read.
        logs_path = self.eval_logs_worktree_path(job_dir)
        lines.append("")
        lines.append("### Logs")
        lines.append(f"Full harbor logs (agent trajectories, terminal recordings, verifier output): `{logs_path}/` (under your shared state dir)")

        feedback = "\n".join(lines)
        return (overall_rate, feedback)

    def _collect_task_results(self, job_dir: Path) -> list[tuple[str, bool]]:
        """Collect per-task pass/fail results from trial result files."""
        results = []
        for trial_dir in sorted(job_dir.iterdir()):
            if not trial_dir.is_dir():
                continue
            result_file = trial_dir / "result.json"
            if not result_file.exists():
                continue
            try:
                trial_result = json.loads(result_file.read_text())
                task_name = trial_result.get("task_name", trial_dir.name)
                exception = trial_result.get("exception_info")
                if exception:
                    results.append((task_name, False))
                    continue
                verifier = trial_result.get("verifier_result")
                if verifier and verifier.get("rewards"):
                    passed = any(float(v) > 0 for v in verifier["rewards"].values())
                    results.append((task_name, passed))
                else:
                    results.append((task_name, False))
            except (json.JSONDecodeError, OSError):
                continue
        return results

    def _collect_trial_failures(self, job_dir: Path, max_show: int = 10) -> list[str]:
        """Collect failure details from individual trial result files."""
        lines = []
        count = 0
        for trial_dir in sorted(job_dir.iterdir()):
            if not trial_dir.is_dir():
                continue
            result_file = trial_dir / "result.json"
            if not result_file.exists():
                continue
            try:
                trial_result = json.loads(result_file.read_text())
                verifier = trial_result.get("verifier_result")
                exception = trial_result.get("exception_info")

                # Check if this trial failed
                is_failure = False
                if exception:
                    is_failure = True
                elif verifier and verifier.get("rewards"):
                    rewards = verifier["rewards"]
                    if all(float(v) == 0 for v in rewards.values()):
                        is_failure = True

                if is_failure and count < max_show:
                    task_name = trial_result.get("task_name", trial_dir.name)
                    if exception:
                        exc_type = exception.get("exception_type", "Error")
                        exc_msg = exception.get("message", "")[:100]
                        lines.append(f"- `{task_name}`: {exc_type}: {exc_msg}")
                    else:
                        lines.append(f"- `{task_name}`: tests failed")
                    count += 1
            except (json.JSONDecodeError, OSError):
                continue

        if count >= max_show:
            lines.append(f"- ... and more")
        return lines

    def _find_harbor_cmd(self) -> list[str] | None:
        """Find how to invoke the harbor CLI."""
        # try to see if docker requires sudo
        prefix = []
        try:
            result = subprocess.run(
                ["docker", "ps"],
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                # docker needs sudo to run
                prefix.append("sudo")
        except Exception:
            pass
        # Prefer uvx (installs/runs from PyPI in an isolated env)
        uvx_path = shutil.which("uvx")
        if uvx_path:
            try:
                result = subprocess.run(
                    [uvx_path, "harbor", "--version"],
                    capture_output=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    return [*prefix, uvx_path, "harbor"]
            except Exception:
                pass
        harbor_path = shutil.which("harbor")
        if harbor_path:
            return [*prefix, harbor_path]
        return None
