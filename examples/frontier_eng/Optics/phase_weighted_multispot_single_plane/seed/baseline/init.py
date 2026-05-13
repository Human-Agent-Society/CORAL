#!/usr/bin/env python
# EVOLVE-BLOCK-START
"""Baseline solver for Task 01: hard weighted multi-spot Fourier DOE."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Any, Tuple

import numpy as np


DEFAULT_CONFIG: Dict[str, Any] = {
    "slm_pixels": 128,
    "aperture_radius_px": 56,
    "grid_rows": 7,
    "grid_cols": 7,
    "spot_x_min": 18.0,
    "spot_x_max": 110.0,
    "spot_y_min": 18.0,
    "spot_y_max": 110.0,
}


def circular_aperture(n: int, radius_px: float) -> np.ndarray:
    y, x = np.indices((n, n))
    c = (n - 1) / 2.0
    return (((x - c) ** 2 + (y - c) ** 2) <= radius_px**2).astype(float)


def build_spots_and_weights(cfg: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    xs = np.linspace(float(cfg["spot_x_min"]), float(cfg["spot_x_max"]), int(cfg["grid_cols"]))
    ys = np.linspace(float(cfg["spot_y_min"]), float(cfg["spot_y_max"]), int(cfg["grid_rows"]))

    spots = []
    weights = []
    for j, yy in enumerate(ys):
        for i, xx in enumerate(xs):
            # Hard nonuniform target distribution to increase optimization difficulty.
            w = 0.12 + 0.88 * (0.5 + 0.5 * np.sin(0.9 * i + 1.25 * j))
            if (i + j) % 2 == 0:
                w *= 0.25
            if (i * j) % 3 == 0:
                w *= 0.60
            spots.append([xx, yy])
            weights.append(w)

    weights_arr = np.asarray(weights, dtype=float)
    weights_arr = weights_arr / (weights_arr.sum() + 1e-12)
    return np.asarray(spots, dtype=float), weights_arr


def build_problem(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)

    n = int(cfg["slm_pixels"])
    x = np.arange(n, dtype=float)
    y = np.arange(n, dtype=float)

    spots, weights = build_spots_and_weights(cfg)
    aperture_amp = circular_aperture(n, float(cfg["aperture_radius_px"]))

    return {
        "cfg": cfg,
        "x": x,
        "y": y,
        "spots": spots,
        "weights": weights,
        "aperture_amp": aperture_amp,
    }


def solve_baseline(problem: Dict[str, Any]) -> np.ndarray:
    """Direct non-iterative superposition baseline."""
    x = problem["x"]
    y = problem["y"]
    n = len(x)
    c = (n - 1) / 2.0
    X, Y = np.meshgrid(x, y)

    U = np.zeros_like(X, dtype=complex)
    for (sx, sy), w in zip(problem["spots"], problem["weights"]):
        fx = (sx - c) / n
        fy = (sy - c) / n
        U += np.sqrt(w) * np.exp(-1j * 2.0 * np.pi * (fx * (X - c) + fy * (Y - c)))

    return np.angle(U)


def forward_intensity(problem: Dict[str, Any], phase: np.ndarray) -> np.ndarray:
    near = problem["aperture_amp"] * np.exp(1j * phase)
    far = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(near), norm="ortho"))
    return np.abs(far) ** 2


def save_solution(path: Path, problem: Dict[str, Any], phase: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        phase=phase.astype(np.float32),
        spots=problem["spots"].astype(np.float32),
        weights=problem["weights"].astype(np.float32),
        aperture_amp=problem["aperture_amp"].astype(np.float32),
        x=problem["x"].astype(np.float32),
        y=problem["y"].astype(np.float32),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Task01 baseline solver")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "baseline_solution.npz",
        help="Output NPZ path",
    )
    parser.add_argument(
        "--config-json",
        type=Path,
        default=None,
        help="Optional JSON config overriding defaults",
    )
    args = parser.parse_args()

    config = None
    if args.config_json is not None:
        config = json.loads(args.config_json.read_text(encoding="utf-8"))

    problem = build_problem(config)
    phase = solve_baseline(problem)
    save_solution(args.output, problem, phase)

    I = forward_intensity(problem, phase)
    print("[Task01/Baseline] solution saved:", args.output)
    print("[Task01/Baseline] intensity stats: min={:.6g}, max={:.6g}, mean={:.6g}".format(I.min(), I.max(), I.mean()))


if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
