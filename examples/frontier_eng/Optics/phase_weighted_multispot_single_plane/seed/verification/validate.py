#!/usr/bin/env python
"""Validation for Task 01.

Hard weighted multi-spot task with score in [0, 1] (higher is better).
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
    spec = importlib.util.spec_from_file_location("task01_baseline", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def slmsuite_wgs_oracle(problem: Dict[str, Any], iterations: int = 70, feedback_exponent: float = 0.78) -> np.ndarray:
    try:
        from slmsuite.holography.algorithms import Hologram
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("slmsuite is required for Task01 oracle. Install: pip install slmsuite") from exc

    n = len(problem["x"])
    y, x = np.indices((n, n))

    target = np.full((n, n), 0.002, dtype=float)
    for (sx, sy), w in zip(problem["spots"], problem["weights"]):
        target += np.sqrt(w) * np.exp(-((x - sx) ** 2 + (y - sy) ** 2) / (2.0 * 1.0**2))
    target = target / (target.max() + 1e-12)

    hologram = Hologram(target=target, amp=problem["aperture_amp"].astype(float))
    hologram.optimize(
        method="WGS-Kim",
        maxiter=int(iterations),
        verbose=False,
        feedback_exponent=float(feedback_exponent),
    )
    return np.array(hologram.get_phase())


def score_from_metrics(ratio_mae: float, cv_spots: float, efficiency: float, min_peak_ratio: float) -> float:
    ratio_score = np.clip(1.0 - ratio_mae / 0.07, 0.0, 1.0)
    uniform_score = 1.0 / (1.0 + (cv_spots / 0.85) ** 2)
    efficiency_score = np.clip((efficiency - 0.15) / (0.80 - 0.15), 0.0, 1.0)
    peak_score = np.clip((min_peak_ratio - 0.003) / (0.20 - 0.003), 0.0, 1.0)

    return float(0.25 * ratio_score + 0.45 * uniform_score + 0.20 * efficiency_score + 0.10 * peak_score)


def spot_metrics(problem: Dict[str, Any], intensity: np.ndarray, window_radius_px: int = 1) -> Dict[str, Any]:
    n = intensity.shape[0]
    spot_energies = []
    spot_peaks = []

    for sx, sy in problem["spots"]:
        ix = int(np.clip(np.round(sx), 0, n - 1))
        iy = int(np.clip(np.round(sy), 0, n - 1))

        i0 = max(0, iy - window_radius_px)
        i1 = min(n, iy + window_radius_px + 1)
        j0 = max(0, ix - window_radius_px)
        j1 = min(n, ix + window_radius_px + 1)

        spot_energies.append(float(intensity[i0:i1, j0:j1].sum()))
        spot_peaks.append(float(intensity[iy, ix]))

    spot_energies = np.asarray(spot_energies, dtype=float)
    spot_peaks = np.asarray(spot_peaks, dtype=float)

    ratios = spot_energies / (spot_energies.sum() + 1e-12)
    target = problem["weights"]

    ratio_mae = float(np.mean(np.abs(ratios - target)))
    cv_spots = float(spot_energies.std() / (spot_energies.mean() + 1e-12))
    efficiency = float(spot_energies.sum() / (intensity.sum() + 1e-12))
    min_peak_ratio = float(spot_peaks.min() / (spot_peaks.max() + 1e-12))

    score = score_from_metrics(ratio_mae, cv_spots, efficiency, min_peak_ratio)
    score_pct = float(100.0 * score)

    return {
        "ratio_mae": ratio_mae,
        "cv_spots": cv_spots,
        "efficiency": efficiency,
        "min_peak_ratio": min_peak_ratio,
        "score": score,
        "score_pct": score_pct,
        "spot_ratios": ratios.tolist(),
        "target_ratios": target.tolist(),
        "spot_peaks": spot_peaks.tolist(),
    }


def save_heatmap(path: Path, image: np.ndarray, spots: np.ndarray, title: str) -> None:
    plt.figure(figsize=(6.3, 5.4))
    plt.imshow(image, origin="lower", cmap="inferno")
    plt.colorbar(label="Intensity")
    plt.scatter(spots[:, 0], spots[:, 1], s=14, marker="o", facecolors="none", edgecolors="cyan", label="targets")
    plt.title(title)
    plt.xlabel("x (pixel)")
    plt.ylabel("y (pixel)")
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def save_ratio_scatter(path: Path, target: np.ndarray, baseline: np.ndarray, oracle: np.ndarray) -> None:
    idx = np.arange(len(target))
    plt.figure(figsize=(7.2, 4.2))
    plt.plot(idx, target, "k-", lw=1.4, label="target")
    plt.plot(idx, baseline, "o", ms=2.8, alpha=0.8, label="baseline")
    plt.plot(idx, oracle, "x", ms=2.8, alpha=0.8, label="oracle(WGS)")
    plt.xlabel("Spot index")
    plt.ylabel("Normalized spot ratio")
    plt.title("Task01 ratio distribution over dense targets")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Task01 validator")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "outputs",
        help="Directory to store metrics and figures",
    )
    parser.add_argument("--iters", type=int, default=70, help="slmsuite WGS iterations")
    parser.add_argument("--feedback-exponent", type=float, default=0.78, help="WGS feedback exponent")
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
        (m_base["score"] >= 0.20)
        and (m_base["efficiency"] >= 0.45)
        and (m_base["min_peak_ratio"] > 0.0)
    )

    summary = {
        "task": "task01_weighted_multispot_single_plane",
        "valid": bool(valid),
        "valid_thresholds": {
            "score_min": 0.20,
            "score_pct_min": 20.0,
            "efficiency_min": 0.45,
            "min_peak_ratio_min": 0.0,
        },
        "baseline": m_base,
        "oracle": {
            **m_oracle,
            "method": "slmsuite WGS-Kim",
            "iterations": int(args.iters),
            "feedback_exponent": float(args.feedback_exponent),
        },
        "delta": {
            "score_gain": float(m_oracle["score"] - m_base["score"]),
            "score_pct_gain": float(m_oracle["score_pct"] - m_base["score_pct"]),
            "efficiency_gain": float(m_oracle["efficiency"] - m_base["efficiency"]),
            "ratio_mae_drop": float(m_base["ratio_mae"] - m_oracle["ratio_mae"]),
            "cv_drop": float(m_base["cv_spots"] - m_oracle["cv_spots"]),
        },
    }

    (args.output_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    save_heatmap(args.output_dir / "baseline_intensity.png", I_baseline, problem["spots"], "Task01 Baseline Intensity")
    save_heatmap(args.output_dir / "oracle_intensity.png", I_oracle, problem["spots"], "Task01 Oracle Intensity (slmsuite WGS)")
    save_ratio_scatter(
        args.output_dir / "spot_ratios.png",
        np.asarray(m_base["target_ratios"]),
        np.asarray(m_base["spot_ratios"]),
        np.asarray(m_oracle["spot_ratios"]),
    )

    print("[Task01] valid:", summary["valid"])
    print("[Task01] baseline score={:.4f}, ratio_mae={:.6f}, cv={:.6f}, eff={:.6f}".format(
        m_base["score"], m_base["ratio_mae"], m_base["cv_spots"], m_base["efficiency"]
    ))
    print("[Task01] oracle   score={:.4f}, ratio_mae={:.6f}, cv={:.6f}, eff={:.6f}".format(
        m_oracle["score"], m_oracle["ratio_mae"], m_oracle["cv_spots"], m_oracle["efficiency"]
    ))
    print("[Task01] outputs:", args.output_dir)


if __name__ == "__main__":
    main()
