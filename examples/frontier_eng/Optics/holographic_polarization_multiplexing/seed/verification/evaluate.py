"""Verification script for Task 4: polarization multiplexing."""

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
            "valid_match_min": 0.32,
            "valid_separation_min": 0.42,
            "valid_score_min": 0.16,
            "score_eff_target": 0.20,
            "score_ratio_scale": 0.10,
            "better_score_margin": 0.10,
            "better_sep_margin": 0.10,
            "reference_steps": args.reference_steps,
            "reference_lr": 0.04,
        }
    )
    spec["steps"] = args.baseline_steps
    return spec


def _sum_on_masks(map_intensity: torch.Tensor, masks: list[torch.Tensor]) -> torch.Tensor:
    return torch.stack([(map_intensity * m).sum() for m in masks]).sum()


def _powers_on_masks(map_intensity: torch.Tensor, masks: list[torch.Tensor]) -> torch.Tensor:
    return torch.stack([(map_intensity * m).sum() for m in masks])


def _cosine_similarity(a: torch.Tensor, b: torch.Tensor) -> float:
    a_f = a.flatten()
    b_f = b.flatten()
    sim = torch.dot(a_f, b_f) / (torch.norm(a_f) * torch.norm(b_f) + 1e-12)
    return float(sim.item())


def _evaluate_solution(result: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    out_x = result["output_field_x"]
    out_y = result["output_field_y"]

    map_x = out_x.intensity().sum(dim=-3)
    map_y = out_y.intensity().sum(dim=-3)

    map_x_norm = map_x / (map_x.sum() + 1e-12)
    map_y_norm = map_y / (map_y.sum() + 1e-12)

    target_x = result["target_map_x"].to(map_x_norm.device)
    target_y = result["target_map_y"].to(map_y_norm.device)

    match_x = _cosine_similarity(map_x_norm.detach().cpu(), target_x.detach().cpu())
    match_y = _cosine_similarity(map_y_norm.detach().cpu(), target_y.detach().cpu())
    mean_match = 0.5 * (match_x + match_y)

    xg, yg = out_x.meshgrid()
    radius = float(spec["roi_radius_m"])

    masks_pattern_x = [(((xg - cx) ** 2 + (yg - cy) ** 2) <= radius**2).to(map_x.dtype) for cx, cy in spec["pattern_x_centers"]]
    masks_pattern_y = [(((xg - cx) ** 2 + (yg - cy) ** 2) <= radius**2).to(map_x.dtype) for cx, cy in spec["pattern_y_centers"]]

    p_x_on_x = _sum_on_masks(map_x, masks_pattern_x)
    p_x_on_y = _sum_on_masks(map_x, masks_pattern_y)
    p_y_on_x = _sum_on_masks(map_y, masks_pattern_x)
    p_y_on_y = _sum_on_masks(map_y, masks_pattern_y)
    p_x_focus = _powers_on_masks(map_x, masks_pattern_x)
    p_y_focus = _powers_on_masks(map_y, masks_pattern_y)

    sep_x = float((p_x_on_x / (p_x_on_x + p_x_on_y + 1e-12)).item())
    sep_y = float((p_y_on_y / (p_y_on_x + p_y_on_y + 1e-12)).item())
    separation = 0.5 * (sep_x + sep_y)
    own_eff_x = float((p_x_on_x / (map_x.sum() + 1e-12)).item())
    own_eff_y = float((p_y_on_y / (map_y.sum() + 1e-12)).item())
    own_efficiency = 0.5 * (own_eff_x + own_eff_y)

    ratio_x = p_x_focus / (p_x_focus.sum() + 1e-12)
    ratio_y = p_y_focus / (p_y_focus.sum() + 1e-12)
    target_ratio_x = torch.tensor(spec["pattern_x_ratios"], dtype=torch.double, device=ratio_x.device)
    target_ratio_x = target_ratio_x / target_ratio_x.sum()
    target_ratio_y = torch.tensor(spec["pattern_y_ratios"], dtype=torch.double, device=ratio_y.device)
    target_ratio_y = target_ratio_y / target_ratio_y.sum()

    ratio_mae_x = float(torch.mean(torch.abs(ratio_x - target_ratio_x)).item())
    ratio_mae_y = float(torch.mean(torch.abs(ratio_y - target_ratio_y)).item())
    mean_ratio_mae = 0.5 * (ratio_mae_x + ratio_mae_y)
    ratio_score = math.exp(-mean_ratio_mae / float(spec["score_ratio_scale"]))
    efficiency_score = float(min(1.0, max(0.0, own_efficiency / float(spec["score_eff_target"]))))
    score = (
        (separation**0.55)
        * (ratio_score**0.20)
        * (efficiency_score**0.25)
        * (mean_match**0.05)
    )
    score = float(min(1.0, max(0.0, score)))

    return {
        "match_x": match_x,
        "match_y": match_y,
        "mean_match": mean_match,
        "separation_x": sep_x,
        "separation_y": sep_y,
        "separation": separation,
        "own_efficiency": own_efficiency,
        "efficiency_score": efficiency_score,
        "ratio_mae_x": ratio_mae_x,
        "ratio_mae_y": ratio_mae_y,
        "mean_ratio_mae": mean_ratio_mae,
        "ratio_score": ratio_score,
        "pred_ratio_x": ratio_x.detach().cpu().tolist(),
        "pred_ratio_y": ratio_y.detach().cpu().tolist(),
        "target_ratio_x": target_ratio_x.detach().cpu().tolist(),
        "target_ratio_y": target_ratio_y.detach().cpu().tolist(),
        "score": score,
        "output_map_x": map_x.detach().cpu(),
        "output_map_y": map_y.detach().cpu(),
        "target_map_x": target_x.detach().cpu(),
        "target_map_y": target_y.detach().cpu(),
    }


def _plot_outputs(base_eval, ref_eval, baseline_losses, ref_losses, save_dir: Path):
    def _norm(x):
        return x / (x.max() + 1e-12)

    fig, axes = plt.subplots(2, 3, figsize=(11, 6.5))

    axes[0][0].imshow(_norm(base_eval["target_map_x"]), cmap="magma")
    axes[0][0].set_title("Target (X-pol input)")
    axes[0][1].imshow(_norm(base_eval["output_map_x"]), cmap="magma")
    axes[0][1].set_title("Baseline Output")
    axes[0][2].imshow(_norm(ref_eval["output_map_x"]), cmap="magma")
    axes[0][2].set_title("Reference Output")

    axes[1][0].imshow(_norm(base_eval["target_map_y"]), cmap="magma")
    axes[1][0].set_title("Target (Y-pol input)")
    axes[1][1].imshow(_norm(base_eval["output_map_y"]), cmap="magma")
    axes[1][1].set_title("Baseline Output")
    axes[1][2].imshow(_norm(ref_eval["output_map_y"]), cmap="magma")
    axes[1][2].set_title("Reference Output")

    for i in range(2):
        for j in range(3):
            axes[i][j].axis("off")

    fig.tight_layout()
    fig.savefig(save_dir / "polarization_maps.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    axes[0].plot(baseline_losses, label="Baseline")
    axes[0].plot(ref_losses, label="Reference")
    axes[0].set_yscale("log")
    axes[0].set_title("Training Loss")
    axes[0].set_xlabel("Iteration")
    axes[0].legend()

    labels = ["Match", "Separation", "RatioScore", "Score"]
    base_vals = [base_eval["mean_match"], base_eval["separation"], base_eval["ratio_score"], base_eval["score"]]
    ref_vals = [ref_eval["mean_match"], ref_eval["separation"], ref_eval["ratio_score"], ref_eval["score"]]
    x = list(range(len(labels)))

    axes[1].bar([i - 0.2 for i in x], base_vals, width=0.4, label="Baseline")
    axes[1].bar([i + 0.2 for i in x], ref_vals, width=0.4, label="Reference")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels)
    axes[1].set_ylim(0.0, 1.05)
    axes[1].set_title("Key Metrics")
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(save_dir / "loss_and_metrics.png", dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--baseline-steps", type=int, default=24)
    parser.add_argument("--reference-steps", type=int, default=60)
    parser.add_argument("--artifacts-dir", default=str(THIS_DIR / "artifacts"))
    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    baseline_module = _load_module(TASK_DIR / "baseline" / "init.py", "task4_baseline_solver")
    reference_module = _load_module(THIS_DIR / "reference_solver.py", "task4_reference_solver")

    spec = _make_spec(baseline_module, args)

    t0 = time.time()
    baseline_res = baseline_module.solve(spec=spec, device=args.device, seed=args.seed)
    t1 = time.time()
    reference_res = reference_module.solve(spec=spec, device=args.device, seed=args.seed)
    t2 = time.time()

    baseline_eval = _evaluate_solution(baseline_res, spec)
    reference_eval = _evaluate_solution(reference_res, spec)

    baseline_valid = (
        baseline_eval["mean_match"] >= spec["valid_match_min"]
        and baseline_eval["separation"] >= spec["valid_separation_min"]
        and baseline_eval["score"] >= spec["valid_score_min"]
    )
    reference_better = (
        reference_eval["score"] >= baseline_eval["score"] + float(spec["better_score_margin"])
        and reference_eval["separation"] >= baseline_eval["separation"] + float(spec["better_sep_margin"])
    )

    _plot_outputs(
        baseline_eval,
        reference_eval,
        baseline_res["loss_history"],
        reference_res["loss_history"],
        artifacts_dir,
    )

    summary = {
        "task": "task4_polarization_multiplexing",
        "spec": spec,
        "timing_seconds": {
            "baseline": round(t1 - t0, 3),
            "reference": round(t2 - t1, 3),
        },
        "baseline": {
            "valid": baseline_valid,
            **{k: v for k, v in baseline_eval.items() if not k.startswith("output_") and not k.startswith("target_")},
        },
        "reference": {
            "oracle_backend": reference_res.get("oracle_backend", "unknown"),
            "better_than_baseline": reference_better,
            **{k: v for k, v in reference_eval.items() if not k.startswith("output_") and not k.startswith("target_")},
        },
    }

    with open(artifacts_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
