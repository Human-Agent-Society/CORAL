from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import runpy
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

TASK_IDS: tuple[str, ...] = (
    "AM_02",
    "AM_03",
    "CY_03",
    "WJ_01",
    "XY_05",
    "YJ_02",
    "YJ_03",
)


def _tail(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return float(text)
        except Exception:
            return default
    return default


def _parse_last_json_dict(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    if not stripped:
        return None

    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    for raw in reversed(stripped.splitlines()):
        line = raw.strip()
        if not line.startswith("{") or not line.endswith("}"):
            continue
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _resolve_output_path(base_dir: Path, value: str) -> Path:
    p = Path(value).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (base_dir / p).resolve()


def _resolve_candidate_path(base_dir: Path, value: str) -> Path:
    p = Path(value).expanduser()
    if p.is_absolute():
        return p.resolve()
    cwd_path = p.resolve()
    if cwd_path.exists():
        return cwd_path
    return (base_dir / p).resolve()


@contextlib.contextmanager
def _pushd(path: Path):
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _load_module(module_name: str, module_path: Path, extra_paths: list[Path]) -> Any:
    original_sys_path = list(sys.path)
    previous_module = sys.modules.get(module_name)
    try:
        sys.path = [str(p) for p in extra_paths] + original_sys_path
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module spec from: {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = original_sys_path
        if previous_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_module


def _load_submission(candidate_path: Path) -> dict[str, Any]:
    scope = runpy.run_path(str(candidate_path))
    for key in ("SUBMISSION", "submission", "ENGDESIGN_SUBMISSION"):
        value = scope.get(key)
        if isinstance(value, dict):
            return value

    derived = {task_id: scope.get(task_id) for task_id in TASK_IDS if task_id in scope}
    if len(derived) == len(TASK_IDS):
        return derived

    raise ValueError(
        "Candidate must define a dict variable named `SUBMISSION` "
        "that contains all EngDesign task payloads."
    )


def _normalize_payload(task_id: str, section: Any) -> dict[str, Any]:
    if not isinstance(section, dict):
        raise TypeError(f"`SUBMISSION[{task_id}]` must be a dict")

    if "config" in section and isinstance(section.get("config"), dict):
        payload = dict(section)
    else:
        config = {k: v for k, v in section.items() if k != "reasoning"}
        payload = {
            "reasoning": str(section.get("reasoning", "")),
            "config": config,
        }

    payload.setdefault("reasoning", "")
    config = payload.get("config")
    if not isinstance(config, dict):
        raise TypeError(f"`SUBMISSION[{task_id}].config` must be a dict")

    if task_id == "CY_03":
        if "vioblk_read" not in config and "vioblk_read_code" in config:
            config["vioblk_read"] = config["vioblk_read_code"]
        if "vioblk_write" not in config and "vioblk_write_code" in config:
            config["vioblk_write"] = config["vioblk_write_code"]
        read_code = str(config.get("vioblk_read", "") or "")
        write_code = str(config.get("vioblk_write", "") or "")
        banned_tokens = (
            "gold_vioblk_read",
            "gold_vioblk_write",
            "globals()[\"gold_vioblk_read\"]",
            "globals()[\"gold_vioblk_write\"]",
            "globals()['gold_vioblk_read']",
            "globals()['gold_vioblk_write']",
        )
        joined = f"{read_code}\n{write_code}"
        for token in banned_tokens:
            if token in joined:
                raise ValueError(
                    "CY_03 submission references forbidden gold helper functions."
                )

    payload["config"] = config
    return payload


def _evaluate_single_task(
    *,
    task_id: str,
    benchmark_dir: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    start = time.time()
    task_dir = (benchmark_dir / task_id).resolve()
    result: dict[str, Any] = {
        "task_id": task_id,
        "passed": False,
        "score": 0.0,
        "confidence": 0.0,
        "task_valid": 0.0,
        "details": {},
        "error": "",
    }

    try:
        if not task_dir.is_dir():
            raise FileNotFoundError(f"Task directory not found: {task_dir}")
        if not candidate_path.is_file():
            raise FileNotFoundError(f"Candidate file not found: {candidate_path}")

        submission = _load_submission(candidate_path)
        if task_id not in submission:
            raise KeyError(f"Missing task key in SUBMISSION: {task_id}")
        payload = _normalize_payload(task_id, submission[task_id])

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            output_module = _load_module(
                module_name=f"engdesign_{task_id.lower()}_output",
                module_path=task_dir / "output_structure.py",
                extra_paths=[task_dir, benchmark_dir],
            )
            evaluate_module = _load_module(
                module_name=f"engdesign_{task_id.lower()}_evaluate",
                module_path=task_dir / "evaluate.py",
                extra_paths=[task_dir, benchmark_dir],
            )

            if not hasattr(output_module, "Response_structure"):
                raise AttributeError(f"{task_id}/output_structure.py has no Response_structure")
            if not hasattr(evaluate_module, "evaluate_llm_response"):
                raise AttributeError(f"{task_id}/evaluate.py has no evaluate_llm_response")

            response = output_module.Response_structure(**payload)
            with _pushd(task_dir):
                passed, details, score, confidence = evaluate_module.evaluate_llm_response(response)

        result["passed"] = bool(passed)
        result["score"] = _safe_float(score, default=0.0)
        result["confidence"] = _safe_float(confidence, default=0.0)
        result["task_valid"] = 1.0
        result["details"] = details if details is not None else {}
        result["eval_stdout"] = _tail(stdout_buf.getvalue(), limit=12000)
        result["eval_stderr"] = _tail(stderr_buf.getvalue(), limit=12000)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = _tail(traceback.format_exc(), limit=12000)

    result["runtime_s"] = float(time.time() - start)
    return result


def _default_failed_task_result(task_id: str, reason: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "passed": False,
        "score": 0.0,
        "confidence": 0.0,
        "task_valid": 0.0,
        "details": {},
        "error": reason,
    }


def _run_full_evaluation(
    *,
    benchmark_dir: Path,
    candidate_path: Path,
    metrics_out: Path,
    artifacts_out: Path,
    task_timeout_s: float,
) -> None:
    start = time.time()
    hard_failures: list[str] = []
    task_results: dict[str, dict[str, Any]] = {}

    try:
        _load_submission(candidate_path)
    except Exception as exc:
        metrics = {
            "combined_score": 0.0,
            "avg_score": 0.0,
            "valid": 0.0,
            "pass_rate": 0.0,
            "passed_tasks": 0.0,
            "total_tasks": float(len(TASK_IDS)),
            "task_valid_rate": 0.0,
            "hard_failures": 1.0,
            "runtime_s": float(time.time() - start),
        }
        artifacts = {
            "candidate_path": str(candidate_path),
            "benchmark_dir": str(benchmark_dir),
            "error_message": f"Failed to load candidate submission: {exc}",
            "traceback": _tail(traceback.format_exc(), limit=12000),
        }
        _write_json(metrics_out, metrics)
        _write_json(artifacts_out, artifacts)
        print(json.dumps({"combined_score": 0.0, "valid": 0.0, "error": str(exc)}, ensure_ascii=False))
        return

    self_path = Path(__file__).resolve()
    for task_id in TASK_IDS:
        cmd = [
            sys.executable,
            str(self_path),
            "--single-task",
            task_id,
            "--candidate",
            str(candidate_path),
            "--benchmark-dir",
            str(benchmark_dir),
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max(5.0, float(task_timeout_s)),
            )
        except subprocess.TimeoutExpired as exc:
            reason = f"TimeoutExpired: {exc}"
            hard_failures.append(f"{task_id}: {reason}")
            task_results[task_id] = _default_failed_task_result(task_id, reason)
            continue
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            hard_failures.append(f"{task_id}: {reason}")
            task_results[task_id] = _default_failed_task_result(task_id, reason)
            continue

        parsed = _parse_last_json_dict(proc.stdout or "")
        if proc.returncode != 0 or not isinstance(parsed, dict):
            reason = (
                f"single-task process failed (rc={proc.returncode}). "
                f"stdout_tail={_tail(proc.stdout or '', 1500)!r} "
                f"stderr_tail={_tail(proc.stderr or '', 1500)!r}"
            )
            hard_failures.append(f"{task_id}: {reason}")
            task_results[task_id] = _default_failed_task_result(task_id, reason)
            continue

        parsed.setdefault("task_id", task_id)
        parsed.setdefault("passed", False)
        parsed.setdefault("score", 0.0)
        parsed.setdefault("confidence", 0.0)
        parsed.setdefault("task_valid", 0.0)
        if proc.stderr:
            parsed["runner_stderr"] = _tail(proc.stderr, limit=4000)
        task_results[task_id] = parsed

    metrics: dict[str, float] = {}
    score_sum = 0.0
    passed_sum = 0.0
    task_valid_sum = 0.0
    total_tasks = float(len(TASK_IDS))

    for task_id in TASK_IDS:
        result = task_results.get(task_id)
        if not isinstance(result, dict):
            result = _default_failed_task_result(task_id, "missing task result")
            task_results[task_id] = result

        score_v = _safe_float(result.get("score"), default=0.0)
        passed_v = 1.0 if bool(result.get("passed")) else 0.0
        task_valid_v = _safe_float(result.get("task_valid"), default=0.0)

        score_sum += score_v
        passed_sum += passed_v
        task_valid_sum += task_valid_v

        key = task_id.lower()
        metrics[f"{key}_score"] = score_v
        metrics[f"{key}_passed"] = passed_v
        metrics[f"{key}_valid"] = task_valid_v

    combined_score = score_sum / total_tasks if total_tasks > 0 else 0.0
    pass_rate = passed_sum / total_tasks if total_tasks > 0 else 0.0
    task_valid_rate = task_valid_sum / total_tasks if total_tasks > 0 else 0.0

    metrics.update(
        {
            "combined_score": combined_score,
            "avg_score": combined_score,
            "valid": 1.0 if (not hard_failures and task_valid_rate > 0.0) else 0.0,
            "pass_rate": pass_rate,
            "passed_tasks": passed_sum,
            "total_tasks": total_tasks,
            "task_valid_rate": task_valid_rate,
            "hard_failures": float(len(hard_failures)),
            "runtime_s": float(time.time() - start),
        }
    )

    if hard_failures:
        metrics["combined_score"] = 0.0
        metrics["avg_score"] = 0.0

    artifacts = {
        "candidate_path": str(candidate_path),
        "benchmark_dir": str(benchmark_dir),
        "task_order": list(TASK_IDS),
        "task_timeout_s": float(task_timeout_s),
        "hard_failures": hard_failures,
        "task_results": task_results,
    }

    _write_json(metrics_out, metrics)
    _write_json(artifacts_out, artifacts)
    print(
        json.dumps(
            {
                "combined_score": metrics["combined_score"],
                "valid": metrics["valid"],
                "pass_rate": metrics["pass_rate"],
                "hard_failures": metrics["hard_failures"],
            },
            ensure_ascii=False,
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate EngDesign unified submission.")
    parser.add_argument("--candidate", required=True, type=str)
    parser.add_argument("--benchmark-dir", default=".", type=str)
    parser.add_argument("--metrics-out", default="metrics.json", type=str)
    parser.add_argument("--artifacts-out", default="artifacts.json", type=str)
    parser.add_argument("--task-timeout-s", default=180.0, type=float)
    parser.add_argument("--single-task", choices=TASK_IDS, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    benchmark_dir = Path(args.benchmark_dir).expanduser().resolve()
    candidate_path = _resolve_candidate_path(benchmark_dir, args.candidate)

    if args.single_task:
        result = _evaluate_single_task(
            task_id=str(args.single_task),
            benchmark_dir=benchmark_dir,
            candidate_path=candidate_path,
        )
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 0

    metrics_out = _resolve_output_path(benchmark_dir, args.metrics_out)
    artifacts_out = _resolve_output_path(benchmark_dir, args.artifacts_out)
    _run_full_evaluation(
        benchmark_dir=benchmark_dir,
        candidate_path=candidate_path,
        metrics_out=metrics_out,
        artifacts_out=artifacts_out,
        task_timeout_s=float(args.task_timeout_s),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
