#!/usr/bin/env python
"""Validation for Task 04.

Compares non-iterative baseline vs slmsuite WGS oracle for a large weighted spot array.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Dict, Any

import matplotlib.pyplot as plt
import numpy as np


def load_module(module_path: Path):
    spec = importlib.util.spec_from_file_location("task04_baseline", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_oracle_target(problem: Dict[str, Any], sigma_px: float = 0.9) -> np.ndarray:
    n = len(problem["x"])
    y, x = np.indices((n, n))

    target = np.full((n, n), 1e-3, dtype=float)
    for (sx, sy), w in zip(problem["spots"], problem["weights"]):
        target += np.sqrt(w) * np.exp(-((x - sx) ** 2 + (y - sy) ** 2) / (2.0 * sigma_px**2))

    target = target / (target.max() + 1e-12)
    return target


def slmsuite_wgs_oracle(problem: Dict[str, Any], iterations: int = 60, feedback_exponent: float = 0.75) -> np.ndarray:
    try:
        from slmsuite.holography.algorithms import Hologram
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "slmsuite is required for Task04 oracle. Install in env: pip install slmsuite"
        ) from exc

    target = build_oracle_target(problem)
    hologram = Hologram(target=target, amp=problem["aperture_amp"].astype(float))
    hologram.optimize(
        method="WGS-Kim",
        maxiter=int(iterations),
        verbose=False,
        feedback_exponent=float(feedback_exponent),
    )
    return np.array(hologram.get_phase())


def spot_metrics(problem: Dict[str, Any], intensity: np.ndarray, window_radius_px: int = 2) -> Dict[str, Any]:
    n = intensity.shape[0]
    energies = []

    for sx, sy in problem["spots"]:
        ix = int(np.clip(np.round(sx), 0, n - 1))
        iy = int(np.clip(np.round(sy), 0, n - 1))
        i0 = max(0, iy - window_radius_px)
        i1 = min(n, iy + window_radius_px + 1)
        j0 = max(0, ix - window_radius_px)
        j1 = min(n, ix + window_radius_px + 1)
        energies.append(float(intensity[i0:i1, j0:j1].sum()))

    energies = np.asarray(energies, dtype=float)
    ratios = energies / (energies.sum() + 1e-12)

    ratio_mae = float(np.mean(np.abs(ratios - problem["weights"])))
    cv_spots = float(energies.std() / (energies.mean() + 1e-12))
    efficiency = float(energies.sum() / (intensity.sum() + 1e-12))

    ratio_score = np.clip(1.0 - ratio_mae / 0.03, 0.0, 1.0)
    uniform_score = np.clip(1.0 - cv_spots / 1.40, 0.0, 1.0)
    efficiency_score = np.clip((efficiency - 0.40) / (0.90 - 0.40), 0.0, 1.0)
    score_pct = float(100.0 * (0.45 * ratio_score + 0.35 * uniform_score + 0.20 * efficiency_score))

    return {
        "ratio_mae": ratio_mae,
        "cv_spots": cv_spots,
        "efficiency": efficiency,
        "score_pct": score_pct,
        "spot_ratios": ratios.tolist(),
        "target_ratios": problem["weights"].tolist(),
        "spot_energies": energies.tolist(),
    }


def save_heatmap(path: Path, image: np.ndarray, spots: np.ndarray, title: str) -> None:
    plt.figure(figsize=(6, 5))
    plt.imshow(image, origin="lower", cmap="inferno")
    plt.colorbar(label="Intensity")
    plt.scatter(spots[:, 0], spots[:, 1], s=12, marker="o", edgecolors="cyan", facecolors="none", label="target spots")
    plt.title(title)
    plt.xlabel("x (pixel)")
    plt.ylabel("y (pixel)")
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def save_ratio_scatter(path: Path, target: np.ndarray, baseline: np.ndarray, oracle: np.ndarray) -> None:
    idx = np.arange(len(target))
    plt.figure(figsize=(7, 4))
    plt.plot(idx, target, "k-", lw=1.5, label="target")
    plt.plot(idx, baseline, "o", ms=3.5, alpha=0.8, label="baseline")
    plt.plot(idx, oracle, "x", ms=3.5, alpha=0.8, label="oracle(WGS)")
    plt.xlabel("Spot index")
    plt.ylabel("Normalized spot ratio")
    plt.title("Task04 weighted spot-ratio comparison")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def save_energy_hist(path: Path, energies_base: np.ndarray, energies_oracle: np.ndarray) -> None:
    plt.figure(figsize=(7, 4))
    plt.hist(energies_base / (energies_base.mean() + 1e-12), bins=20, alpha=0.65, label="baseline")
    plt.hist(energies_oracle / (energies_oracle.mean() + 1e-12), bins=20, alpha=0.65, label="oracle(WGS)")
    plt.xlabel("Per-spot energy / mean")
    plt.ylabel("Count")
    plt.title("Task04 spot-energy distribution")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Task04 validator")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "outputs",
        help="Directory to store metrics and figures",
    )
    parser.add_argument("--iters", type=int, default=60, help="slmsuite WGS iterations")
    parser.add_argument("--feedback-exponent", type=float, default=0.75, help="WGS feedback exponent")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    baseline_module = load_module(Path(__file__).resolve().parents[1] / "baseline" / "init.py")
    problem = baseline_module.build_problem()

    phase_baseline = baseline_module.solve_baseline(problem)
    I_baseline = baseline_module.forward_intensity(problem, phase_baseline)

    phase_oracle = slmsuite_wgs_oracle(problem, iterations=args.iters, feedback_exponent=args.feedback_exponent)
    I_oracle = baseline_module.forward_intensity(problem, phase_oracle)

    m_base = spot_metrics(problem, I_baseline)
    m_oracle = spot_metrics(problem, I_oracle)

    valid = (
        (m_base["score_pct"] >= 20.0)
        and (m_base["ratio_mae"] <= 0.03)
        and (m_base["cv_spots"] <= 1.40)
        and (m_base["efficiency"] >= 0.50)
    )

    summary = {
        "task": "task04_large_scale_spot_array",
        "valid": bool(valid),
        "valid_thresholds": {
            "score_pct_min": 20.0,
            "ratio_mae_max": 0.03,
            "cv_spots_max": 1.40,
            "efficiency_min": 0.50,
        },
        "baseline": m_base,
        "oracle": {
            **m_oracle,
            "method": "slmsuite WGS-Kim",
            "iterations": int(args.iters),
            "feedback_exponent": float(args.feedback_exponent),
        },
        "delta": {
            "ratio_mae_improvement": float(m_base["ratio_mae"] - m_oracle["ratio_mae"]),
            "cv_improvement": float(m_base["cv_spots"] - m_oracle["cv_spots"]),
            "efficiency_gain": float(m_oracle["efficiency"] - m_base["efficiency"]),
            "score_pct_gain": float(m_oracle["score_pct"] - m_base["score_pct"]),
        },
    }

    (args.output_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    save_heatmap(args.output_dir / "baseline_intensity.png", I_baseline, problem["spots"], "Task04 Baseline Intensity")
    save_heatmap(args.output_dir / "oracle_intensity.png", I_oracle, problem["spots"], "Task04 Oracle Intensity (slmsuite WGS)")

    save_ratio_scatter(
        args.output_dir / "spot_ratios.png",
        np.asarray(m_base["target_ratios"]),
        np.asarray(m_base["spot_ratios"]),
        np.asarray(m_oracle["spot_ratios"]),
    )
    save_energy_hist(
        args.output_dir / "spot_energy_hist.png",
        np.asarray(m_base["spot_energies"]),
        np.asarray(m_oracle["spot_energies"]),
    )

    print("[Task04] valid:", summary["valid"])
    print("[Task04] baseline score_pct={:.3f}, ratio_mae={:.6f}, cv={:.6f}, eff={:.6f}".format(
        m_base["score_pct"], m_base["ratio_mae"], m_base["cv_spots"], m_base["efficiency"]
    ))
    print("[Task04] oracle   score_pct={:.3f}, ratio_mae={:.6f}, cv={:.6f}, eff={:.6f}".format(
        m_oracle["score_pct"], m_oracle["ratio_mae"], m_oracle["cv_spots"], m_oracle["efficiency"]
    ))
    print("[Task04] outputs:", args.output_dir)


if __name__ == "__main__":
    main()
