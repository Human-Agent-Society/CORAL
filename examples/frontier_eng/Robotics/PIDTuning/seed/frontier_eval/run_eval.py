from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import traceback
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any

INVALID_COMBINED_SCORE = -1e18


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _normalize_result(result: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if hasattr(result, "metrics") and hasattr(result, "artifacts"):
        return dict(getattr(result, "metrics")), dict(getattr(result, "artifacts"))

    if isinstance(result, dict):
        raw_metrics = result.get("metrics")
        raw_artifacts = result.get("artifacts")
        if isinstance(raw_metrics, dict):
            return dict(raw_metrics), dict(raw_artifacts or {})
        return dict(result), {}

    raise TypeError(
        "Evaluator must return an EvaluationResult-like object or a dict of metrics."
    )


def _load_local_evaluator() -> Any:
    evaluator_path = Path(__file__).with_name("evaluator.py").resolve()
    spec = spec_from_file_location("_frontier_eval_local_evaluator", evaluator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load local evaluator from {evaluator_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return getattr(module, "evaluate")
    except AttributeError as exc:
        raise RuntimeError(
            f"Local evaluator does not define evaluate(): {evaluator_path}"
        ) from exc


def _find_repo_root() -> Path:
    env_root = os.environ.get("FRONTIER_ENGINEERING_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "frontier_eval").is_dir() and (parent / "benchmarks").is_dir():
            return parent
    return Path.cwd().resolve()


def _build_kwargs(evaluate_fn: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    try:
        parameters = inspect.signature(evaluate_fn).parameters
    except Exception:
        return kwargs

    if "repo_root" in parameters:
        kwargs["repo_root"] = _find_repo_root()
    if "kernel_python" in parameters:
        kwargs["kernel_python"] = sys.executable
    return kwargs


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a benchmark-local unified evaluator and export metrics/artifacts JSON."
    )
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--metrics-out", default="metrics.json")
    parser.add_argument("--artifacts-out", default="artifacts.json")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    candidate_path = Path(args.candidate).expanduser().resolve()
    metrics_out = Path(args.metrics_out).expanduser().resolve()
    artifacts_out = Path(args.artifacts_out).expanduser().resolve()

    metrics: dict[str, Any] = {
        "combined_score": INVALID_COMBINED_SCORE,
        "valid": 0.0,
    }
    artifacts: dict[str, Any] = {
        "local_evaluator_path": str(Path(__file__).with_name("evaluator.py").resolve()),
        "candidate_path": str(candidate_path),
    }

    try:
        evaluate_fn = _load_local_evaluator()
        result = evaluate_fn(str(candidate_path), **_build_kwargs(evaluate_fn))
        metrics, evaluator_artifacts = _normalize_result(result)
        artifacts.update(evaluator_artifacts)
    except Exception as exc:
        artifacts["error_message"] = str(exc)
        artifacts["traceback"] = traceback.format_exc()

    _write_json(metrics_out, metrics)
    _write_json(artifacts_out, artifacts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
