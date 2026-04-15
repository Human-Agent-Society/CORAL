"""SWE-bench grader — evaluates a solver agent via the harbor CLI.

Runs `harbor run -d swebench-verified@1.0` with the agent's solve.py as a custom
harbor agent, then parses the job result JSON for the pass rate.

Uses tiered evaluation:
  Tier 1:  5 instances → stop if pass rate < threshold
  Tier 2: 30 instances → stop if pass rate < threshold
  Tier 3: all instances
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle


class Grader(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        dataset = self.args.get("dataset", "swebench-verified@1.0")
        n_concurrent = int(self.args.get("n_concurrent", 5))
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

        # Tiered evaluation
        tiers = [
            (tier1_size, tier1_threshold, "Tier 1"),
            (tier2_size, tier2_threshold, "Tier 2"),
            (0, 0.0, "Tier 3 (full)"),  # 0 = all
        ]

        total_start = time.time()

        for n_tasks, threshold, tier_name in tiers:
            job_dir = Path(self.codebase_path) / "harbor_logs"
            job_dir.mkdir(parents=True, exist_ok=True)
            job_name = f"eval_{tier_name.lower().replace(' ', '_')}_{int(time.time())}"

            harbor_result = self._run_harbor(
                harbor_cmd=harbor_cmd,
                dataset=dataset,
                job_dir=job_dir,
                job_name=job_name,
                n_tasks=n_tasks,
                n_concurrent=n_concurrent,
                agent_timeout_multiplier=agent_timeout_multiplier,
                verifier_timeout_multiplier=verifier_timeout_multiplier,
            )

            if isinstance(harbor_result, ScoreBundle):
                # Error from _run_harbor
                return harbor_result

            pass_rate, feedback = harbor_result

            # Early stop check (skip for final tier)
            if threshold > 0 and pass_rate < threshold:
                total_time = time.time() - total_start
                explanation = (
                    f"Stopped at {tier_name}: {pass_rate:.1%} < {threshold:.0%} threshold"
                )
                return self.score(pass_rate, explanation, feedback=feedback)

        total_time = time.time() - total_start
        explanation = f"Full eval: {pass_rate:.1%} pass rate in {total_time:.0f}s"
        return self.score(pass_rate, explanation, feedback=feedback)

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
        timeout = self.timeout or 14400

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

        return self._parse_job_result(job_result, job_dir / job_name, elapsed)

    def _parse_job_result(
        self, job_result: dict, job_dir: Path, elapsed: float
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
            overall_rate = 0.0
            for eval_stats in evals.values():
                p = eval_stats.get("pass_at_k", {})
                overall_rate = p.get("1", p.get(1, 0.0))
                break

        # Build feedback
        lines = [
            f"## SWE-bench Results: {overall_rate:.1%} pass rate",
            f"Completed {n_trials} trials in {elapsed:.0f}s "
            f"({n_errors} errors)",
            "",
        ]
        for detail in reward_details:
            lines.append(f"- {detail}")

        # Per-trial failure details
        failure_lines = self._collect_trial_failures(job_dir, max_show=10)
        if failure_lines:
            lines.append("")
            lines.append("### Failed trials")
            lines.extend(failure_lines)

        # Point agent to the logs
        lines.append("")
        lines.append(f"### Logs")
        lines.append(f"Full harbor logs (agent trajectories, terminal recordings, verifier output): `{job_dir}`")

        feedback = "\n".join(lines)
        return (overall_rate, feedback)

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
        # Prefer uvx (installs/runs from PyPI in an isolated env)
        if shutil.which("uvx"):
            try:
                result = subprocess.run(
                    ["uvx", "harbor", "--version"],
                    capture_output=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    return ["uvx", "harbor"]
            except Exception:
                pass
        if shutil.which("harbor"):
            return ["harbor"]
        return None
