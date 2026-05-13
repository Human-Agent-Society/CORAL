"""Verification script for Task 2: multi-plane focusing."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import time
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch


THIS_DIR = Path(__file__).resolve().parent
TASK_DIR = THIS_DIR.parent


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_spec(baseline_module, args: argparse.Namespace) -> dict[str, Any]:
    spec = baseline_module.make_default_spec()
    spec.update(
        {
            "roi_radius_m": 3 * spec["spacing"],
            "valid_mean_ratio_mae_max": 0.34,
            "valid_mean_efficiency_min": 0.015,
            "valid_mean_score_min": 0.18,
            "score_eff_target": 0.09,
            "score_ratio_scale": 0.12,
            "better_score_margin": 0.07,
            "better_shape_margin": 0.03,
            "reference_steps": args.reference_steps,
            "reference_lr": 0.045,
        }
    )
    spec["steps"] = args.baseline_steps
    return spec


def _cosine_similarity(a: torch.Tensor, b: torch.Tensor) -> float:
    a_f = a.flatten()
    b_f = b.flatten()
    sim = torch.dot(a_f, b_f) / (torch.norm(a_f) * torch.norm(b_f) + 1e-12)
    return float(sim.item())


def _plane_metrics(
    output_field,
    target_field,
    plane_cfg: dict[str, Any],
    roi_radius: float,
    score_eff_target: float,
    score_ratio_scale: float,
) -> dict[str, Any]:
    x, y = output_field.meshgrid()
    intensity = output_field.intensity()
    pred_norm = intensity / (intensity.sum() + 1e-12)

    target_intensity = target_field.intensity().to(intensity.device)
    target_norm = target_intensity / (target_intensity.sum() + 1e-12)

    roi_powers = []
    for cx, cy in plane_cfg["centers"]:
        mask = ((x - cx) ** 2 + (y - cy) ** 2) <= roi_radius**2
        roi_powers.append((intensity * mask.to(intensity.dtype)).sum())

    roi_powers_t = torch.stack(roi_powers)
    focus_power = roi_powers_t.sum()
    total_power = intensity.sum() + 1e-12

    pred_ratios = roi_powers_t / (focus_power + 1e-12)
    target_ratios = torch.tensor(plane_cfg["ratios"], dtype=torch.double, device=intensity.device)
    target_ratios = target_ratios / target_ratios.sum()

    ratio_mae = torch.mean(torch.abs(pred_ratios - target_ratios)).item()
    efficiency = (focus_power / total_power).item()
    ratio_score = math.exp(-ratio_mae / score_ratio_scale)
    efficiency_score = float(min(1.0, max(0.0, efficiency / score_eff_target)))
    shape_cosine = _cosine_similarity(pred_norm, target_norm)
    shape_l1 = float(torch.mean(torch.abs(pred_norm - target_norm)).item())
    score = (efficiency_score**0.50) * (ratio_score**0.35) * (shape_cosine**0.15)
    score = float(min(1.0, max(0.0, score)))

    return {
        "ratio_mae": ratio_mae,
        "efficiency": efficiency,
        "ratio_score": ratio_score,
        "efficiency_score": efficiency_score,
        "shape_cosine": shape_cosine,
        "shape_l1": shape_l1,
        "score": score,
        "pred_ratios": pred_ratios.detach().cpu().tolist(),
        "target_ratios": target_ratios.detach().cpu().tolist(),
        "intensity": intensity.detach().cpu(),
    }


def _evaluate_solution(result: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    roi_radius = float(spec["roi_radius_m"])
    score_eff_target = float(spec["score_eff_target"])
    score_ratio_scale = float(spec["score_ratio_scale"])
    per_plane = []

    for plane_cfg, target_field in zip(spec["planes"], result["target_fields"]):
        out = result["system"].measure_at_z(result["input_field"], z=plane_cfg["z"])
        per_plane.append(
            _plane_metrics(out, target_field, plane_cfg, roi_radius, score_eff_target, score_ratio_scale)
        )

    mean_ratio_mae = sum(m["ratio_mae"] for m in per_plane) / len(per_plane)
    mean_efficiency = sum(m["efficiency"] for m in per_plane) / len(per_plane)
    mean_score = sum(m["score"] for m in per_plane) / len(per_plane)
    mean_shape_cosine = sum(m["shape_cosine"] for m in per_plane) / len(per_plane)

    return {
        "per_plane": per_plane,
        "mean_ratio_mae": mean_ratio_mae,
        "mean_efficiency": mean_efficiency,
        "mean_score": mean_score,
        "mean_shape_cosine": mean_shape_cosine,
    }


def _plot_outputs(spec, baseline_eval, reference_eval, baseline_losses, ref_losses, target_fields, save_dir: Path):
    n = len(spec["planes"])

    fig, axes = plt.subplots(n, 3, figsize=(10, 3.2 * n))
    if n == 1:
        axes = [axes]

    for i, plane_cfg in enumerate(spec["planes"]):
        target_i = target_fields[i].intensity().detach().cpu()
        base_i = baseline_eval["per_plane"][i]["intensity"]
        ref_i = reference_eval["per_plane"][i]["intensity"]

        def _norm(x):
            return x / (x.max() + 1e-12)

        axes[i][0].imshow(_norm(target_i), cmap="viridis")
        axes[i][0].set_title(f"Plane z={plane_cfg['z']:.2f} Target")
        axes[i][1].imshow(_norm(base_i), cmap="viridis")
        axes[i][1].set_title("Baseline")
        axes[i][2].imshow(_norm(ref_i), cmap="viridis")
        axes[i][2].set_title("Reference")

        for j in range(3):
            axes[i][j].axis("off")

    fig.tight_layout()
    fig.savefig(save_dir / "plane_intensity_maps.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    axes[0].plot(baseline_losses, label="Baseline")
    axes[0].plot(ref_losses, label="Reference")
    axes[0].set_yscale("log")
    axes[0].set_title("Training Loss")
    axes[0].set_xlabel("Iteration")
    axes[0].legend()

    x = list(range(len(spec["planes"])))
    base_eff = [m["efficiency"] for m in baseline_eval["per_plane"]]
    ref_eff = [m["efficiency"] for m in reference_eval["per_plane"]]
    axes[1].bar([i - 0.2 for i in x], base_eff, width=0.4, label="Baseline")
    axes[1].bar([i + 0.2 for i in x], ref_eff, width=0.4, label="Reference")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([f"z={p['z']:.2f}" for p in spec["planes"]])
    axes[1].set_title("Per-Plane Efficiency")
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(save_dir / "loss_and_efficiency.png", dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--baseline-steps", type=int, default=24)
    parser.add_argument("--reference-steps", type=int, default=90)
    parser.add_argument("--artifacts-dir", default=str(THIS_DIR / "artifacts"))
    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    baseline_module = _load_module(TASK_DIR / "baseline" / "init.py", "task2_baseline_solver")
    reference_module = _load_module(THIS_DIR / "reference_solver.py", "task2_reference_solver")

    spec = _make_spec(baseline_module, args)

    t0 = time.time()
    baseline_res = baseline_module.solve(spec=spec, device=args.device, seed=args.seed)
    t1 = time.time()
    reference_res = reference_module.solve(spec=spec, device=args.device, seed=args.seed)
    t2 = time.time()

    baseline_eval = _evaluate_solution(baseline_res, spec)
    reference_eval = _evaluate_solution(reference_res, spec)

    baseline_valid = (
        baseline_eval["mean_ratio_mae"] <= spec["valid_mean_ratio_mae_max"]
        and baseline_eval["mean_efficiency"] >= spec["valid_mean_efficiency_min"]
        and baseline_eval["mean_score"] >= spec["valid_mean_score_min"]
    )
    reference_better = (
        reference_eval["mean_score"] >= baseline_eval["mean_score"] + float(spec["better_score_margin"])
        and reference_eval["mean_shape_cosine"]
        >= baseline_eval["mean_shape_cosine"] + float(spec["better_shape_margin"])
    )

    _plot_outputs(
        spec,
        baseline_eval,
        reference_eval,
        baseline_res["loss_history"],
        reference_res["loss_history"],
        baseline_res["target_fields"],
        artifacts_dir,
    )

    summary = {
        "task": "task2_multiplane_focusing",
        "spec": spec,
        "timing_seconds": {
            "baseline": round(t1 - t0, 3),
            "reference": round(t2 - t1, 3),
        },
        "baseline": {
            "valid": baseline_valid,
            "mean_ratio_mae": baseline_eval["mean_ratio_mae"],
            "mean_efficiency": baseline_eval["mean_efficiency"],
            "mean_score": baseline_eval["mean_score"],
            "mean_shape_cosine": baseline_eval["mean_shape_cosine"],
            "per_plane": [
                {k: v for k, v in p.items() if k != "intensity"}
                for p in baseline_eval["per_plane"]
            ],
        },
        "reference": {
            "oracle_backend": reference_res.get("oracle_backend", "unknown"),
            "better_than_baseline": reference_better,
            "mean_ratio_mae": reference_eval["mean_ratio_mae"],
            "mean_efficiency": reference_eval["mean_efficiency"],
            "mean_score": reference_eval["mean_score"],
            "mean_shape_cosine": reference_eval["mean_shape_cosine"],
            "per_plane": [
                {k: v for k, v in p.items() if k != "intensity"}
                for p in reference_eval["per_plane"]
            ],
        },
    }

    with open(artifacts_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
