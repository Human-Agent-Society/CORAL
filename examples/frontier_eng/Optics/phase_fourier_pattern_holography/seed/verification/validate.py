#!/usr/bin/env python
"""Validation for Task 02.

Hard Fourier pattern holography with score in [0, 100] (higher is better).
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
    spec = importlib.util.spec_from_file_location("task02_baseline", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def slmsuite_wgs_oracle(problem: Dict[str, Any], iterations: int = 80, feedback_exponent: float = 0.78) -> np.ndarray:
    try:
        from slmsuite.holography.algorithms import Hologram
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("slmsuite is required for Task02 oracle. Install: pip install slmsuite") from exc

    target_for_opt = np.maximum(problem["target_amp"], 1e-4)

    hologram = Hologram(target=target_for_opt, amp=problem["aperture_amp"].astype(float))
    hologram.optimize(
        method="WGS-Kim",
        maxiter=int(iterations),
        verbose=False,
        feedback_exponent=float(feedback_exponent),
    )
    return np.array(hologram.get_phase())


def nmse(intensity: np.ndarray, target_amp: np.ndarray) -> float:
    target_intensity = target_amp**2
    I_n = intensity / (intensity.mean() + 1e-12)
    T_n = target_intensity / (target_intensity.mean() + 1e-12)
    return float(np.sqrt(((I_n - T_n) ** 2).mean()))


def energy_in_target(intensity: np.ndarray, target_amp: np.ndarray, threshold: float = 0.30) -> float:
    mask = target_amp > threshold
    return float(intensity[mask].sum() / (intensity.sum() + 1e-12))


def dark_suppression(intensity: np.ndarray, target_amp: np.ndarray, threshold: float = 0.03) -> float:
    mask_dark = target_amp < threshold
    leak = float(intensity[mask_dark].sum() / (intensity.sum() + 1e-12))
    return float(1.0 - leak)


def score_from_metrics(nmse_value: float, energy_target: float, dark_sup: float) -> float:
    pattern_score = np.clip(1.0 - nmse_value / 4.0, 0.0, 1.0)
    energy_score = np.clip((energy_target - 0.10) / (0.70 - 0.10), 0.0, 1.0)
    dark_score = np.clip((dark_sup - 0.35) / (0.90 - 0.35), 0.0, 1.0)

    return float(100.0 * (0.55 * pattern_score + 0.30 * energy_score + 0.15 * dark_score))


def save_image(path: Path, image: np.ndarray, title: str, cmap: str = "inferno") -> None:
    plt.figure(figsize=(6, 5))
    plt.imshow(image, origin="lower", cmap=cmap)
    plt.colorbar()
    plt.title(title)
    plt.xlabel("x (pixel)")
    plt.ylabel("y (pixel)")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Task02 validator")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "outputs",
        help="Directory to store metrics and figures",
    )
    parser.add_argument("--iters", type=int, default=80, help="slmsuite WGS iterations")
    parser.add_argument("--feedback-exponent", type=float, default=0.78, help="WGS feedback exponent")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    baseline_module = load_module(Path(__file__).resolve().parents[1] / "baseline" / "init.py")
    problem = baseline_module.build_problem()

    phase_baseline = baseline_module.solve_baseline(problem, seed=int(problem["cfg"]["seed"]))
    I_baseline = baseline_module.forward_intensity(problem, phase_baseline)

    phase_oracle = slmsuite_wgs_oracle(problem, iterations=args.iters, feedback_exponent=args.feedback_exponent)
    I_oracle = baseline_module.forward_intensity(problem, phase_oracle)

    base_nmse = nmse(I_baseline, problem["target_amp"])
    base_energy = energy_in_target(I_baseline, problem["target_amp"])
    base_dark = dark_suppression(I_baseline, problem["target_amp"])
    base_score = score_from_metrics(base_nmse, base_energy, base_dark)

    oracle_nmse = nmse(I_oracle, problem["target_amp"])
    oracle_energy = energy_in_target(I_oracle, problem["target_amp"])
    oracle_dark = dark_suppression(I_oracle, problem["target_amp"])
    oracle_score = score_from_metrics(oracle_nmse, oracle_energy, oracle_dark)

    valid = (base_score >= 20.0) and (base_energy >= 0.45) and (base_dark >= 0.60)

    summary = {
        "task": "task02_fourier_pattern_holography",
        "valid": bool(valid),
        "valid_thresholds": {
            "score_pct_min": 20.0,
            "energy_in_target_min": 0.45,
            "dark_suppression_min": 0.60,
        },
        "baseline": {
            "nmse": float(base_nmse),
            "energy_in_target": float(base_energy),
            "dark_suppression": float(base_dark),
            "score_pct": float(base_score),
        },
        "oracle": {
            "nmse": float(oracle_nmse),
            "energy_in_target": float(oracle_energy),
            "dark_suppression": float(oracle_dark),
            "score_pct": float(oracle_score),
            "method": "slmsuite WGS-Kim",
            "iterations": int(args.iters),
            "feedback_exponent": float(args.feedback_exponent),
        },
        "delta": {
            "score_pct_gain": float(oracle_score - base_score),
            "nmse_drop": float(base_nmse - oracle_nmse),
            "energy_gain": float(oracle_energy - base_energy),
            "dark_suppression_gain": float(oracle_dark - base_dark),
        },
    }

    (args.output_dir / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    target_intensity = problem["target_amp"]**2
    save_image(args.output_dir / "target_pattern.png", target_intensity, "Task02 Target Intensity", cmap="viridis")
    save_image(args.output_dir / "baseline_intensity.png", I_baseline, "Task02 Baseline Intensity")
    save_image(args.output_dir / "oracle_intensity.png", I_oracle, "Task02 Oracle Intensity (slmsuite WGS)")

    diff_base = np.abs(I_baseline / (I_baseline.mean() + 1e-12) - target_intensity / (target_intensity.mean() + 1e-12))
    diff_oracle = np.abs(I_oracle / (I_oracle.mean() + 1e-12) - target_intensity / (target_intensity.mean() + 1e-12))
    save_image(args.output_dir / "baseline_error_map.png", diff_base, "Task02 Baseline Error Map", cmap="magma")
    save_image(args.output_dir / "oracle_error_map.png", diff_oracle, "Task02 Oracle Error Map", cmap="magma")

    print("[Task02] valid:", summary["valid"])
    print("[Task02] baseline score_pct={:.3f}, nmse={:.6f}, energy={:.6f}, dark_sup={:.6f}".format(
        base_score, base_nmse, base_energy, base_dark
    ))
    print("[Task02] oracle   score_pct={:.3f}, nmse={:.6f}, energy={:.6f}, dark_sup={:.6f}".format(
        oracle_score, oracle_nmse, oracle_energy, oracle_dark
    ))
    print("[Task02] outputs:", args.output_dir)


if __name__ == "__main__":
    main()
