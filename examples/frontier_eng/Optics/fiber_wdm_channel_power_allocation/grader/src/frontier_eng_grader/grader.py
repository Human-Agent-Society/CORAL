"""Generic CORAL grader for Frontier-Engineering benchmarks.

The seed is expected to mirror a single Frontier-Eng benchmark directory
(``benchmarks/<Domain>/<Task>/``), including its ``frontier_eval/`` metadata
folder. This grader reads the metadata files (``eval_command.txt``,
``candidate_destination.txt``, ``eval_cwd.txt``, ``initial_program.txt``,
``copy_files.txt``), stages the codebase into a writable sandbox, expands the
documented placeholders (``{python}``, ``{candidate}``, ``{benchmark}``,
``{sandbox}``, ``{repo_root}``, ``{benchmark_id}``, ``{benchmark_source}`` and
their ``_raw`` variants), runs the eval command, then parses ``metrics.json``
for ``combined_score`` / ``valid``.

Faithful port of ``frontier_eval/tasks/unified/evaluator/python.py`` but
adapted to CORAL's contract: the agent's commit IS the candidate, so we copy
the whole codebase (not just one file) into the sandbox.

Sandbox layout:

    <sandbox_root>/
    └── repo_root/              ← FRONTIER_ENGINEERING_ROOT
        └── benchmarks/
            └── <Domain>/<Task>/   ← seed contents land here

This mirrors the upstream repo path so tasks that look up files via
``Path(__file__).resolve().parents[N]`` (e.g. Cryptographic, JobShop) still
resolve correctly. The seed should be self-contained — parent-domain shared
files are baked into ``seed/_parent/`` and the benchmark's
``eval_command.txt`` is rewritten by ``_scripts/generate_tasks.py`` to refer
to them via ``{benchmark}/_parent/...`` rather than
``{repo_root}/benchmarks/<Domain>/...``.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from coral.grader import TaskGrader
from coral.types import ScoreBundle

INVALID_COMBINED_SCORE = -1e18
DEFAULT_METRICS_FILE = "metrics.json"
DEFAULT_METADATA_DIR = "frontier_eval"
DEFAULT_EVAL_CWD = "."
_LOG_TAIL_BYTES = 4_000


class Grader(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        try:
            return self._evaluate()
        except Exception as e:
            return self.fail(f"Grader failed: {type(e).__name__}: {e}")

    def _evaluate(self) -> ScoreBundle:
        codebase = Path(self.codebase_path).resolve()
        meta_dir_name = self.args.get("metadata_dir", DEFAULT_METADATA_DIR)
        meta_dir = codebase / meta_dir_name
        if not meta_dir.is_dir():
            return self.fail(f"metadata directory missing: {meta_dir_name}/ not found in seed")

        eval_cmd_template = _read_text(meta_dir / "eval_command.txt")
        if not eval_cmd_template:
            return self.fail(f"{meta_dir_name}/eval_command.txt missing or empty")

        eval_cwd_rel = (
            _read_text(meta_dir / "eval_cwd.txt") or DEFAULT_EVAL_CWD
        ).strip() or DEFAULT_EVAL_CWD
        candidate_dest_rel = (
            _read_text(meta_dir / "candidate_destination.txt")
            or _read_text(meta_dir / "initial_program.txt")
            or ""
        ).strip()
        metrics_filename = self.args.get("metrics_json", DEFAULT_METRICS_FILE)
        benchmark_id = str(self.args.get("benchmark_id", codebase.name))

        sandbox_root = Path(tempfile.mkdtemp(prefix=f"frontier_eng_{_safe_slug(benchmark_id)}_"))
        try:
            fake_repo_root = sandbox_root / "repo_root"
            sandbox_benchmark = fake_repo_root / "benchmarks" / benchmark_id
            sandbox_benchmark.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                codebase,
                sandbox_benchmark,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            # Some tasks (e.g. ComputerSystems/DuckDBWorkloadOptimization)
            # discover the repo via `_is_repo_root(p) := (p/"benchmarks").is_dir()
            # and (p/"frontier_eval").is_dir()`. Drop an empty marker so the
            # synthetic repo_root looks like upstream's checkout.
            (fake_repo_root / "frontier_eval").mkdir(exist_ok=True)

            python_cmd_str = _make_python_wrapper(sandbox_root, self.get_python_command())
            effective_benchmark = sandbox_benchmark
            candidate_path = (
                (effective_benchmark / candidate_dest_rel).resolve()
                if candidate_dest_rel
                else effective_benchmark
            )

            placeholders = _build_placeholders(
                python_cmd=python_cmd_str,
                candidate_path=candidate_path,
                sandbox_benchmark=effective_benchmark,
                sandbox_root=sandbox_root,
                fake_repo_root=fake_repo_root,
                benchmark_id=benchmark_id,
            )

            try:
                eval_cmd_str = eval_cmd_template.format(**placeholders).strip()
            except KeyError as e:
                missing = str(e).strip("'")
                return self.fail(
                    f"Unknown placeholder in eval_command.txt: {{{missing}}}. "
                    f"Supported: {sorted(placeholders.keys())}"
                )

            cwd = (
                effective_benchmark if eval_cwd_rel == "." else (effective_benchmark / eval_cwd_rel)
            )
            cwd.mkdir(parents=True, exist_ok=True)

            log_dir = self.eval_logs_dir
            stdout_path = log_dir / "eval.stdout.txt"
            stderr_path = log_dir / "eval.stderr.txt"

            env = os.environ.copy()
            env.setdefault("FRONTIER_EVAL_UNIFIED_CANDIDATE_PATH", str(candidate_path))
            env.setdefault("FRONTIER_EVAL_UNIFIED_BENCHMARK", benchmark_id)
            env.setdefault("FRONTIER_EVAL_UNIFIED_BENCHMARK_DIR", str(effective_benchmark))
            env.setdefault("FRONTIER_EVAL_UNIFIED_SOURCE_BENCHMARK_DIR", str(effective_benchmark))
            env["FRONTIER_ENGINEERING_ROOT"] = str(fake_repo_root)
            extra_env = self.args.get("env") or {}
            if isinstance(extra_env, dict):
                for k, v in extra_env.items():
                    env[str(k)] = str(v)

            shell_cmd = ["bash", "-c", eval_cmd_str]
            start = time.time()
            try:
                proc = subprocess.run(
                    shell_cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env=env,
                )
            except subprocess.TimeoutExpired as e:
                stdout_path.write_text(_text_or_empty(e.stdout), errors="replace")
                stderr_path.write_text(_text_or_empty(e.stderr), errors="replace")
                runtime_s = time.time() - start
                return self.fail(
                    f"Eval timed out after {self.timeout}s (ran {runtime_s:.1f}s). "
                    f"stderr tail:\n{_tail(_text_or_empty(e.stderr))}"
                )

            runtime_s = time.time() - start
            stdout_path.write_text(proc.stdout, errors="replace")
            stderr_path.write_text(proc.stderr, errors="replace")

            inner_stderr = ""
            inner_stdout = ""
            for inner_name in ("eval.stderr.txt",):
                inner_path = effective_benchmark / inner_name
                if inner_path.is_file():
                    inner_stderr = inner_path.read_text(encoding="utf-8", errors="replace")
                    (log_dir / "eval.inner.stderr.txt").write_text(inner_stderr, errors="replace")
                    break
            for inner_name in ("eval.stdout.txt",):
                inner_path = effective_benchmark / inner_name
                if inner_path.is_file():
                    inner_stdout = inner_path.read_text(encoding="utf-8", errors="replace")
                    (log_dir / "eval.inner.stdout.txt").write_text(inner_stdout, errors="replace")
                    break

            metrics_path = effective_benchmark / metrics_filename
            metrics = _read_json(metrics_path) or {}

            artifacts_path = effective_benchmark / "artifacts.json"
            artifacts_data = _read_json(artifacts_path) or {}
            artifact_msg = ""
            if artifacts_data:
                err_keys = (
                    "error_message",
                    "traceback",
                    "compile_evaluate_stderr",
                    "compile_validate_stderr",
                    "evaluate_stderr",
                    "validate_stderr",
                )
                err_parts = []
                for k in err_keys:
                    v = artifacts_data.get(k)
                    if v:
                        snippet = str(v)
                        if len(snippet) > 1500:
                            snippet = snippet[:1500] + "...[truncated]"
                        err_parts.append(f"{k}: {snippet}")
                if err_parts:
                    artifact_msg = "\nartifacts.json:\n" + "\n".join(err_parts)
                try:
                    (log_dir / "artifacts.json").write_text(
                        json.dumps(artifacts_data, indent=2, default=str), errors="replace"
                    )
                except Exception:
                    pass

            valid_raw = metrics.get("valid", 0.0 if not metrics_path.is_file() else 1.0)
            valid = _maybe_float(valid_raw) or 0.0
            combined = _maybe_float(metrics.get("combined_score"))

            extras = []
            for key in (
                "candidate_score",
                "reference_score",
                "gap_to_reference",
                "eval_returncode",
                "runtime_s",
            ):
                if key in metrics:
                    extras.append(f"{key}={metrics[key]}")
            extras_str = " ".join(extras)

            if not metrics_path.is_file():
                merged_stderr = inner_stderr or proc.stderr
                return self.fail(
                    f"metrics.json not produced by eval (returncode={proc.returncode}, "
                    f"runtime={runtime_s:.1f}s).\n"
                    f"stdout tail:\n{_tail(proc.stdout)}\n"
                    f"stderr tail:\n{_tail(merged_stderr)}"
                )

            if combined is None or combined <= INVALID_COMBINED_SCORE / 2.0:
                merged_stderr = inner_stderr or proc.stderr
                return self.fail(
                    f"combined_score missing or invalid in metrics.json. "
                    f"valid={valid}, returncode={proc.returncode}. {extras_str}{artifact_msg}\n"
                    f"stderr tail:\n{_tail(merged_stderr)}"
                )

            if valid < 1.0:
                merged_stderr = inner_stderr or proc.stderr
                merged_stdout = inner_stdout or proc.stdout
                return self.fail(
                    f"Eval reported valid=0 (combined_score={combined}). {extras_str}{artifact_msg}\n"
                    f"stdout tail:\n{_tail(merged_stdout)}\n"
                    f"stderr tail:\n{_tail(merged_stderr)}"
                )

            explanation = f"combined_score={combined:.6f} valid=1 {extras_str} runtime={runtime_s:.1f}s".strip()
            return self.score(combined, explanation=explanation)
        finally:
            shutil.rmtree(sandbox_root, ignore_errors=True)


def _build_placeholders(
    *,
    python_cmd: str,
    candidate_path: Path,
    sandbox_benchmark: Path,
    sandbox_root: Path,
    fake_repo_root: Path,
    benchmark_id: str,
) -> dict[str, str]:
    raw = {
        "python": python_cmd,
        "candidate": str(candidate_path),
        "benchmark": str(sandbox_benchmark),
        "sandbox": str(sandbox_root),
        "repo_root": str(fake_repo_root),
        "benchmark_source": str(sandbox_benchmark),
        "benchmark_id": benchmark_id,
    }
    out: dict[str, str] = {}
    for key, value in raw.items():
        out[key] = shlex.quote(value)
        out[f"{key}_raw"] = value
    return out


def _make_python_wrapper(sandbox_root: Path, python_cmd: list[str]) -> str:
    # Some benchmarks pass {python} as a positional argument to a shell wrapper
    # (e.g. Optics' ``bash run_eval.sh {python} {benchmark} {candidate}``), so
    # expanding to a multi-word ``uv run --project X python`` would split into
    # several args and break the script's positional indexing. Write a tiny
    # exec'ing wrapper into the sandbox so {python} is always one shell word
    # whether it leads the command or sits in an argument slot.
    wrapper = sandbox_root / "python_cmd.sh"
    body = "#!/usr/bin/env bash\nexec " + " ".join(shlex.quote(p) for p in python_cmd) + ' "$@"\n'
    wrapper.write_text(body)
    wrapper.chmod(0o755)
    return str(wrapper)


def _safe_slug(value: str) -> str:
    safe_chars = []
    for ch in value:
        if ch.isalnum() or ch in "._-":
            safe_chars.append(ch)
        else:
            safe_chars.append("_")
    return ("".join(safe_chars).strip("._-")) or "benchmark"


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _maybe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            return None
    return None


def _tail(text: str, limit: int = _LOG_TAIL_BYTES) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[-limit:]


def _text_or_empty(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)
