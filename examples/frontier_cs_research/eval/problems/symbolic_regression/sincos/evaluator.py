#!/usr/bin/env python3
"""
Symbolic regression evaluator.

Loads CSV datasets, executes a contestant Solution implementation, computes
per-dataset metrics (MSE, complexity, score), and writes a JSON report.
The final numeric score (mean across datasets) is printed to stdout.
"""

import argparse
import importlib.util
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
import sympy as sp

# ---------------------------------------------------------------------------
# Data containers


@dataclass
class ReferenceMetrics:
    m_base: float
    m_ref: float
    c_ref: int
    reference_expression: str


# ---------------------------------------------------------------------------
# Utility helpers


def load_solution_module(solution_path: Path) -> ModuleType:
    if not solution_path.is_file():
        raise FileNotFoundError(f"solution.py not found at {solution_path}")
    spec = importlib.util.spec_from_file_location("submitted_solution", solution_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module spec from {solution_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # Register before exec for self-referential imports
    spec.loader.exec_module(module)
    if not hasattr(module, "Solution"):
        raise AttributeError("Submitted solution module must define a Solution class")
    return module


def load_reference_metrics(path: Path) -> Dict[str, ReferenceMetrics]:
    data = json.loads(path.read_text(encoding="utf-8"))
    metrics: Dict[str, ReferenceMetrics] = {}
    for name, payload in data.items():
        metrics[name] = ReferenceMetrics(
            m_base=float(payload["m_base"]),
            m_ref=float(payload["m_ref"]),
            c_ref=int(payload["C_ref"]),
            reference_expression=str(payload["reference_expression"]),
        )
    return metrics


def mse(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    y_true = np.asarray(list(y_true), dtype=float).ravel()
    y_pred = np.asarray(list(y_pred), dtype=float).ravel()
    if y_true.shape != y_pred.shape:
        raise ValueError(
            f"Mismatched prediction shape: {y_pred.shape}, expected {y_true.shape}"
        )
    return float(np.mean((y_true - y_pred) ** 2))


def parse_expression(expr: str, n_features: int) -> sp.Expr:
    if not isinstance(expr, str) or not expr.strip():
        raise ValueError("Expression must be a non-empty string.")
    symbols = sp.symbols(" ".join(f"x{i + 1}" for i in range(n_features)))
    locals_dict = {f"x{i + 1}": symbols[i] for i in range(n_features)}
    allowed_funcs = {"sin": sp.sin, "cos": sp.cos, "exp": sp.exp, "log": sp.log}
    locals_dict.update(allowed_funcs)
    try:
        parsed = sp.sympify(expr, locals=locals_dict)
    except Exception as exc:  # pragma: no cover - validation
        raise ValueError(f"Failed to parse expression '{expr}': {exc}") from exc
    return parsed


def expression_complexity(expr: sp.Expr) -> int:
    """Compute complexity as 2*(#binary ops) + (#unary ops)."""

    def walk(node: sp.Expr) -> Tuple[int, int]:
        if node.is_Atom:
            return 0, 0
        binary_ops = 0
        unary_ops = 0
        func = node.func
        args = node.args

        if func in (sp.Add, sp.Mul):
            binary_ops += max(len(args) - 1, 0)
        elif func is sp.Pow:
            binary_ops += 1
        elif func in (sp.sin, sp.cos, sp.exp, sp.log):
            unary_ops += 1

        for arg in args:
            b_child, u_child = walk(arg)
            binary_ops += b_child
            unary_ops += u_child
        return binary_ops, unary_ops

    b, u = walk(expr)
    return int(2 * b + u)


def ensure_predictions(
    raw_predictions: Iterable[float] | None,
    expression: sp.Expr,
    X: np.ndarray,
    feature_symbols: Tuple[sp.Symbol, ...],
) -> List[float]:
    if raw_predictions is not None:
        values = np.asarray(list(raw_predictions), dtype=float).ravel()
        if values.shape == (X.shape[0],):
            return values.tolist()
    # Fallback: evaluate expression via lambdify
    fn = sp.lambdify(
        feature_symbols,
        expression,
        modules={"sin": np.sin, "cos": np.cos, "exp": np.exp, "log": np.log},
    )
    try:
        evaluated = fn(*[X[:, i] for i in range(X.shape[1])])
    except Exception as exc:
        raise RuntimeError(f"Failed to evaluate expression on data: {exc}") from exc
    return np.asarray(evaluated, dtype=float).ravel().tolist()


def compute_score(mse_value: float, complexity: int, ref: ReferenceMetrics) -> tuple[float, float]:
    if math.isnan(mse_value):
        return 0.0, 0.0
    # Handle degenerate denominator per specification
    denom = ref.m_base - ref.m_ref
    if abs(denom) < 1e-12:
        base_component_unbounded = 1.0 if mse_value <= ref.m_ref else 0.0
    else:
        base_component_unbounded = (ref.m_base - mse_value) / denom
    base_component = max(0.0, min(1.0, base_component_unbounded))
    complexity_penalty = 0.99 ** max(complexity - ref.c_ref, 0)
    score_unbounded = 100.0 * base_component_unbounded * complexity_penalty
    score = max(0.0, min(100.0, score_unbounded))
    return score, score_unbounded


# ---------------------------------------------------------------------------
# Main evaluation routine


def evaluate(
    solution_module: ModuleType,
    datasets: Dict[str, Path],
    references: Dict[str, ReferenceMetrics],
) -> Dict[str, Dict[str, float | int | str]]:
    SolutionCls = getattr(solution_module, "Solution")
    results: Dict[str, Dict[str, float | int | str]] = {}

    for name, data_path in datasets.items():
        df = pd.read_csv(data_path)
        if "y" not in df.columns:
            raise ValueError(f"Dataset {name} is missing 'y' column")
        y = df["y"].to_numpy(dtype=float)
        X = df.drop(columns=["y"]).to_numpy(dtype=float)

        ref_metrics = references.get(name)
        if ref_metrics is None:
            raise KeyError(f"Reference metrics missing for dataset {name}")

        # Instantiate fresh solution for each dataset
        solution = SolutionCls()
        output = solution.solve(X, y)
        if not isinstance(output, dict):
            raise TypeError(
                f"Solution.solve must return dict, got {type(output).__name__}"
            )

        expr_raw = output.get("expression", "")
        predictions_raw = output.get("predictions")
        details = output.get("details") or {}

        parsed_expr = parse_expression(expr_raw, X.shape[1])
        symbols = sp.symbols(" ".join(f"x{i + 1}" for i in range(X.shape[1])))
        preds = ensure_predictions(predictions_raw, parsed_expr, X, symbols)
        mse_value = mse(y, preds)

        complexity = details.get("complexity")
        if complexity is None:
            complexity = expression_complexity(parsed_expr)
        else:
            complexity = int(complexity)

        score, score_unbounded = compute_score(mse_value, complexity, ref_metrics)

        results[name] = {
            "mse": mse_value,
            "expression": str(expr_raw),
            "complexity": complexity,
            "score": score,
            "score_unbounded": score_unbounded,
            "m_base": ref_metrics.m_base,
            "m_ref": ref_metrics.m_ref,
            "C_ref": ref_metrics.c_ref,
            "reference_expression": ref_metrics.reference_expression,
        }
    return results


def main(argv: List[str] | None = None) -> float:
    parser = argparse.ArgumentParser(
        description="Evaluate symbolic regression solution."
    )
    parser.add_argument(
        "--solution-path",
        type=Path,
        required=True,
        help="Path to contestant solution.py",
    )
    parser.add_argument(
        "--data-dir", type=Path, required=True, help="Directory containing CSV datasets"
    )
    parser.add_argument(
        "--reference-path", type=Path, required=True, help="Reference metrics JSON path"
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        required=True,
        help="Where to write evaluation report JSON",
    )
    args = parser.parse_args(argv)

    references = load_reference_metrics(args.reference_path)
    if not args.data_dir.is_dir():
        raise FileNotFoundError(f"Data directory not found: {args.data_dir}")

    data_files = sorted(p for p in args.data_dir.glob("*.csv"))
    if not data_files:
        raise FileNotFoundError(f"No CSV datasets found in {args.data_dir}")

    datasets = {p.name: p for p in data_files if p.name in references}
    if not datasets:
        raise ValueError(
            "No datasets matched the reference metrics; check dataset names."
        )

    missing_reference = sorted(set(references.keys()) - set(datasets.keys()))
    if missing_reference:
        raise ValueError(
            f"Reference metrics provided for missing datasets: {missing_reference}"
        )

    ignored = sorted(set(p.name for p in data_files) - set(datasets.keys()))
    for name in ignored:
        print(
            f"[symbolic_regression evaluator] Skipping unreferenced dataset {name}",
            file=sys.stderr,
        )

    solution_module = load_solution_module(args.solution_path)
    results = evaluate(solution_module, datasets, references)

    scores = [entry["score"] for entry in results.values()]
    scores_unbounded = [entry["score_unbounded"] for entry in results.values()]
    mean_score = float(sum(scores) / len(scores))
    mean_score_unbounded = float(sum(scores_unbounded) / len(scores_unbounded))
    mean_mse = float(sum(entry["mse"] for entry in results.values()) / len(results))

    report = {
        "by_dataset": results,
        "summary": {
            "mean_score": mean_score,
            "mean_score_unbounded": mean_score_unbounded,
            "mean_mse": mean_mse,
            "num_datasets": len(results),
        },
    }

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Format: "score score_unbounded" (space-separated)
    print(f"{mean_score:.6f} {mean_score_unbounded:.6f}")
    return mean_score


if __name__ == "__main__":  # pragma: no cover - CLI entry
    try:
        main()
    except Exception as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        sys.exit(1)
