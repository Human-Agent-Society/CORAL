from __future__ import annotations

import inspect
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any


def _load_verification_module() -> Any:
    evaluator_path = (
        Path(__file__).resolve().parents[1] / "verification" / "evaluator.py"
    ).resolve()
    spec = spec_from_file_location("_frontier_eval_verification_evaluator", evaluator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load verification evaluator from {evaluator_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(program_path: str, *, repo_root: Path | None = None) -> Any:
    module = _load_verification_module()
    evaluate_fn = getattr(module, "evaluate")
    kwargs: dict[str, Any] = {}
    if "repo_root" in inspect.signature(evaluate_fn).parameters and repo_root is not None:
        kwargs["repo_root"] = repo_root
    return evaluate_fn(program_path, **kwargs)
