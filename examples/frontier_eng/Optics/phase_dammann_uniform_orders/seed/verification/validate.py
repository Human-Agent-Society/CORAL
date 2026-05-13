#!/usr/bin/env python
"""Validation for Task 03.

Compares naive baseline against:
1) literature transition set,
2) SciPy differential-evolution optimized transition set,
and reports oracle as the better one.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Dict, Any, Tuple

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import differential_evolution


def load_module(module_path: Path):
    spec = importlib.util.spec_from_file_location("task03_baseline", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def literature_transitions(period_size: float) -> np.ndarray:
    """Known good transitions from diffractio advanced Dammann example."""
    x_norm = np.array(
        [
            0.0,
            0.201181,
            0.250978,
            0.326167,
            0.370555,
            0.372996,
            0.396478,
            0.453128,
            0.594731,
            0.670591,
            0.717718,
            0.890632,
            0.919921,
            0.935546,
        ],
        dtype=float,
    )
    return (x_norm - 0.5) * period_size


def loss(metrics: Dict[str, Any]) -> float:
    """Lower-is-better surrogate used internally by DE optimization."""
    return float(metrics["cv_orders"] + 0.2 * (1.0 - metrics["efficiency"]))


def score_pct(metrics: Dict[str, Any]) -> float:
    """User-facing score in [0, 100], higher is better."""
    uniform_score = np.clip(1.0 - metrics["cv_orders"] / 0.9, 0.0, 1.0)
    efficiency_score = np.clip((metrics["efficiency"] - 0.003) / (0.18 - 0.003), 0.0, 1.0)
    balance_score = np.clip((metrics["min_to_max"] - 0.15) / (0.90 - 0.15), 0.0, 1.0)
    return float(100.0 * (0.60 * uniform_score + 0.30 * efficiency_score + 0.10 * balance_score))


def evaluate_transitions(baseline_module, problem: Dict[str, Any], transitions: np.ndarray) -> Tuple[Dict[str, Any], np.ndarray, np.ndarray]:
    field = baseline_module.build_incident_field(problem, transitions)
    focus = field.RS(z=problem["cfg"]["focal"], new_field=True, verbose=False)
    intensity = np.abs(focus.u) ** 2
    metrics = baseline_module.evaluate_orders(problem, intensity, focus.x)
    return metrics, focus.x, intensity


def optimize_transitions_de(
    baseline_module,
    problem: Dict[str, Any],
    maxiter: int = 35,
    popsize: int = 8,
    seed: int = 0,
) -> Tuple[np.ndarray, Dict[str, Any], np.ndarray, np.ndarray, float]:
    cfg = problem["cfg"]
    period_size = float(cfg["period_size"])
    n_trans = int(cfg["num_transitions"])
    n_half = n_trans // 2

    def decode(z: np.ndarray) -> np.ndarray:
        # Symmetric transition parameterization around period center.
        s = np.sort(np.clip(z, 1e-3, 1.0 - 1e-3))
        pos = 0.5 + 0.46 * s
        neg = 1.0 - pos[::-1]
        x_norm = np.concatenate([neg, pos])
        return (x_norm - 0.5) * period_size

    def objective(z: np.ndarray) -> float:
        transitions = decode(z)
        m, _, _ = evaluate_transitions(baseline_module, problem, transitions)
        base = loss(m)

        # Penalize too-close transitions to keep manufacturable spacing.
        min_spacing = 0.015 * period_size
        d = np.diff(np.sort(transitions))
        penalty = 100.0 * np.sum(np.clip(min_spacing - d, 0.0, None) ** 2)
        return float(base + penalty)

    bounds = [(0.02, 0.98)] * n_half
    result = differential_evolution(
        objective,
        bounds,
        maxiter=int(maxiter),
        popsize=int(popsize),
        seed=int(seed),
        polish=True,
        workers=1,
        updating="deferred",
    )

    transitions = decode(result.x)
    metrics, x_focus, intensity = evaluate_transitions(baseline_module, problem, transitions)
    return transitions, metrics, x_focus, intensity, float(result.fun)


def save_focus_plot(path: Path, x: np.ndarray, I_base: np.ndarray, I_lit: np.ndarray, I_de: np.ndarray, order_positions: np.ndarray) -> None:
    plt.figure(figsize=(8, 4))
    plt.plot(x, I_base / (I_base.max() + 1e-12), label="baseline", lw=1.8)
    plt.plot(x, I_lit / (I_lit.max() + 1e-12), label="literature", lw=1.2)
    plt.plot(x, I_de / (I_de.max() + 1e-12), label="scipy-DE", lw=1.2)
    for xp in order_positions:
        plt.axvline(xp, color="gray", ls="--", lw=0.6, alpha=0.6)
    plt.xlim(order_positions.min() - 20, order_positions.max() + 20)
    plt.xlabel("x at focus (um)")
    plt.ylabel("Normalized intensity")
    plt.title("Task03 focus profile around target diffraction orders")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def save_order_bar(path: Path, orders: np.ndarray, base_norm: np.ndarray, lit_norm: np.ndarray, de_norm: np.ndarray) -> None:
    w = 0.25
    x = np.arange(len(orders))
    plt.figure(figsize=(8, 4))
    plt.bar(x - w, base_norm, width=w, label="baseline")
    plt.bar(x, lit_norm, width=w, label="literature")
    plt.bar(x + w, de_norm, width=w, label="scipy-DE")
    plt.xticks(x, orders)
    plt.xlabel("Diffraction order m")
    plt.ylabel("Normalized order energy")
    plt.title("Task03 order energy uniformity")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def save_transition_plot(path: Path, trans_base: np.ndarray, trans_lit: np.ndarray, trans_de: np.ndarray) -> None:
    plt.figure(figsize=(8, 3.8))
    plt.plot(trans_base, np.zeros_like(trans_base), "o", label="baseline")
    plt.plot(trans_lit, np.ones_like(trans_lit), "x", label="literature")
    plt.plot(trans_de, np.full_like(trans_de, 2.0), "+", label="scipy-DE")
    plt.yticks([0, 1, 2], ["baseline", "literature", "scipy-DE"])
    plt.xlabel("Transition position in one period (um)")
    plt.title("Task03 transition comparison")
    plt.grid(True, axis="x", alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Task03 validator")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "outputs",
        help="Directory to store metrics and figures",
    )
    parser.add_argument("--de-maxiter", type=int, default=35, help="Differential evolution maxiter")
    parser.add_argument("--de-popsize", type=int, default=8, help="Differential evolution popsize")
    parser.add_argument("--de-seed", type=int, default=0, help="Differential evolution seed")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    baseline_module = load_module(Path(__file__).resolve().parents[1] / "baseline" / "init.py")
    problem = baseline_module.build_problem()

    baseline_sol = baseline_module.solve_baseline(problem)
    metrics_base = baseline_sol["metrics"]
    score_base = score_pct(metrics_base)

    trans_lit = literature_transitions(problem["cfg"]["period_size"])
    metrics_lit, x_lit, I_lit = evaluate_transitions(baseline_module, problem, trans_lit)
    score_lit = score_pct(metrics_lit)

    trans_de, metrics_de, x_de, I_de, de_fun = optimize_transitions_de(
        baseline_module,
        problem,
        maxiter=args.de_maxiter,
        popsize=args.de_popsize,
        seed=args.de_seed,
    )
    score_de = score_pct(metrics_de)

    loss_lit = loss(metrics_lit)
    loss_de = loss(metrics_de)

    if score_de >= score_lit:
        oracle_name = "scipy_differential_evolution"
        metrics_oracle = metrics_de
        score_oracle = score_de
        transitions_oracle = trans_de
    else:
        oracle_name = "literature_transition_table"
        metrics_oracle = metrics_lit
        score_oracle = score_lit
        transitions_oracle = trans_lit

    valid = (
        (metrics_base["cv_orders"] <= 0.8)
        and (metrics_base["efficiency"] >= 0.003)
        and (metrics_base["min_to_max"] >= 0.15)
    )

    summary = {
        "task": "task03_dammann_uniform_orders",
        "valid": bool(valid),
        "valid_thresholds": {
            "cv_orders_max": 0.8,
            "efficiency_min": 0.003,
            "min_to_max_min": 0.15,
        },
        "baseline": {
            **metrics_base,
            "score_pct": score_base,
            "transitions": baseline_sol["transitions"].tolist(),
        },
        "literature": {
            **metrics_lit,
            "score_pct": score_lit,
            "loss": loss_lit,
            "transitions": trans_lit.tolist(),
            "source": "diffractio docs/source/examples_advanced/scalar/dammann.ipynb",
        },
        "scipy_de": {
            **metrics_de,
            "score_pct": score_de,
            "loss": loss_de,
            "transitions": trans_de.tolist(),
            "objective_with_penalty": de_fun,
            "maxiter": int(args.de_maxiter),
            "popsize": int(args.de_popsize),
            "seed": int(args.de_seed),
        },
        "oracle": {
            **metrics_oracle,
            "score_pct": score_oracle,
            "method": "best_of_literature_and_scipy_de",
            "selected_candidate": oracle_name,
            "transitions": transitions_oracle.tolist(),
        },
        "delta": {
            "cv_improvement": float(metrics_base["cv_orders"] - metrics_oracle["cv_orders"]),
            "efficiency_gain": float(metrics_oracle["efficiency"] - metrics_base["efficiency"]),
            "score_pct_gain": float(score_oracle - score_base),
        },
    }

    (args.output_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    orders = np.asarray(metrics_base["orders"], dtype=int)
    order_pos = np.asarray(metrics_base["order_positions"], dtype=float)
    base_norm = np.asarray(metrics_base["order_energies_norm"], dtype=float)
    lit_norm = np.asarray(metrics_lit["order_energies_norm"], dtype=float)
    de_norm = np.asarray(metrics_de["order_energies_norm"], dtype=float)

    save_focus_plot(
        args.output_dir / "focus_profile.png",
        baseline_sol["x_focus"],
        baseline_sol["intensity_focus"],
        I_lit,
        I_de,
        order_pos,
    )
    save_order_bar(args.output_dir / "order_energies.png", orders, base_norm, lit_norm, de_norm)
    save_transition_plot(args.output_dir / "transitions.png", baseline_sol["transitions"], trans_lit, trans_de)

    print("[Task03] valid:", summary["valid"])
    print("[Task03] baseline cv={:.6f}, eff={:.6f}, score_pct={:.3f}".format(
        metrics_base["cv_orders"], metrics_base["efficiency"], score_base
    ))
    print("[Task03] literature cv={:.6f}, eff={:.6f}, score_pct={:.3f}".format(
        metrics_lit["cv_orders"], metrics_lit["efficiency"], score_lit
    ))
    print("[Task03] scipy-DE cv={:.6f}, eff={:.6f}, score_pct={:.3f}".format(
        metrics_de["cv_orders"], metrics_de["efficiency"], score_de
    ))
    print("[Task03] oracle method: best_of_literature_and_scipy_de")
    print("[Task03] oracle selected candidate:", oracle_name)
    print("[Task03] outputs:", args.output_dir)


if __name__ == "__main__":
    main()
