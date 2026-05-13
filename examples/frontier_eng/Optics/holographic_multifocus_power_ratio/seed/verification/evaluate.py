"""Verification script for Task 1: multifocus power-ratio control."""

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
            "valid_ratio_mae_max": 0.30,
            "valid_efficiency_min": 0.040,
            "valid_score_min": 0.16,
            "score_eff_target": 0.20,
            "score_ratio_scale": 0.10,
            "better_score_margin": 0.06,
            "better_shape_margin": 0.03,
            "reference_steps": args.reference_steps,
            "reference_lr": 0.05,
        }
    )
    spec["steps"] = args.baseline_steps
    return spec


def _cosine_similarity(a: torch.Tensor, b: torch.Tensor) -> float:
    a_f = a.flatten()
    b_f = b.flatten()
    sim = torch.dot(a_f, b_f) / (torch.norm(a_f) * torch.norm(b_f) + 1e-12)
    return float(sim.item())


def _compute_metrics(output_field, target_field, spec: dict[str, Any]) -> dict[str, Any]:
    x, y = output_field.meshgrid()
    intensity = output_field.intensity()
    pred_norm = intensity / (intensity.sum() + 1e-12)

    target_intensity = target_field.intensity().to(intensity.device)
    target_norm = target_intensity / (target_intensity.sum() + 1e-12)

    roi_radius = float(spec["roi_radius_m"])
    roi_powers = []
    for cx, cy in spec["focus_centers"]:
        mask = ((x - cx) ** 2 + (y - cy) ** 2) <= roi_radius**2
        roi_powers.append((intensity * mask.to(intensity.dtype)).sum())

    roi_powers_t = torch.stack(roi_powers)
    focus_power = roi_powers_t.sum()
    total_power = intensity.sum() + 1e-12

    target_ratios = torch.tensor(spec["focus_ratios"], dtype=torch.double, device=intensity.device)
    target_ratios = target_ratios / target_ratios.sum()
    pred_ratios = roi_powers_t / (focus_power + 1e-12)

    ratio_mae = torch.mean(torch.abs(pred_ratios - target_ratios)).item()
    efficiency = (focus_power / total_power).item()
    leakage = 1.0 - efficiency
    ratio_score = math.exp(-ratio_mae / float(spec["score_ratio_scale"]))
    efficiency_score = float(min(1.0, max(0.0, efficiency / float(spec["score_eff_target"]))))
    shape_cosine = _cosine_similarity(pred_norm, target_norm)
    shape_l1 = float(torch.mean(torch.abs(pred_norm - target_norm)).item())
    score = (efficiency_score**0.58) * (ratio_score**0.22) * (shape_cosine**0.20)
    score = float(min(1.0, max(0.0, score)))

    return {
        "ratio_mae": ratio_mae,
        "efficiency": efficiency,
        "leakage": leakage,
        "ratio_score": ratio_score,
        "efficiency_score": efficiency_score,
        "shape_cosine": shape_cosine,
        "shape_l1": shape_l1,
        "score": score,
        "pred_ratios": pred_ratios.detach().cpu().tolist(),
        "target_ratios": target_ratios.detach().cpu().tolist(),
        "intensity": intensity.detach().cpu(),
    }


def _plot_outputs(spec, target_field, baseline_metrics, ref_metrics, baseline_losses, ref_losses, save_dir: Path):
    target_intensity = target_field.intensity().detach().cpu()
    base_img = baseline_metrics["intensity"]
    ref_img = ref_metrics["intensity"]

    def _norm(x):
        x = x / (x.max() + 1e-12)
        return x

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    axes[0].imshow(_norm(target_intensity), cmap="magma")
    axes[0].set_title("Target Intensity")
    axes[1].imshow(_norm(base_img), cmap="magma")
    axes[1].set_title("Baseline Output")
    axes[2].imshow(_norm(ref_img), cmap="magma")
    axes[2].set_title("Reference Output")
    for ax in axes:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(save_dir / "intensity_maps.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    idx = list(range(len(spec["focus_ratios"])))
    axes[0].bar([i - 0.25 for i in idx], baseline_metrics["target_ratios"], width=0.25, label="Target")
    axes[0].bar(idx, baseline_metrics["pred_ratios"], width=0.25, label="Baseline")
    axes[0].bar([i + 0.25 for i in idx], ref_metrics["pred_ratios"], width=0.25, label="Reference")
    axes[0].set_title("Focus Power Ratios")
    axes[0].set_xlabel("Focus Index")
    axes[0].legend()

    axes[1].plot(baseline_losses, label="Baseline")
    axes[1].plot(ref_losses, label="Reference")
    axes[1].set_yscale("log")
    axes[1].set_title("Training Loss")
    axes[1].set_xlabel("Iteration")
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(save_dir / "ratios_and_losses.png", dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default=None, help="cpu/cuda, default: auto")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--baseline-steps", type=int, default=24)
    parser.add_argument("--reference-steps", type=int, default=80)
    parser.add_argument("--artifacts-dir", default=str(THIS_DIR / "artifacts"))
    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    baseline_module = _load_module(TASK_DIR / "baseline" / "init.py", "task1_baseline_solver")
    reference_module = _load_module(THIS_DIR / "reference_solver.py", "task1_reference_solver")

    spec = _make_spec(baseline_module, args)

    t0 = time.time()
    baseline_res = baseline_module.solve(spec=spec, device=args.device, seed=args.seed)
    t1 = time.time()
    ref_res = reference_module.solve(spec=spec, device=args.device, seed=args.seed)
    t2 = time.time()

    baseline_output = baseline_res["system"].measure_at_z(baseline_res["input_field"], spec["output_z"])
    ref_output = ref_res["system"].measure_at_z(ref_res["input_field"], spec["output_z"])

    baseline_metrics = _compute_metrics(baseline_output, baseline_res["target_field"], spec)
    ref_metrics = _compute_metrics(ref_output, ref_res["target_field"], spec)

    baseline_valid = (
        baseline_metrics["ratio_mae"] <= spec["valid_ratio_mae_max"]
        and baseline_metrics["efficiency"] >= spec["valid_efficiency_min"]
        and baseline_metrics["score"] >= spec["valid_score_min"]
    )

    reference_better = (
        ref_metrics["score"] >= baseline_metrics["score"] + float(spec["better_score_margin"])
        and ref_metrics["shape_cosine"] >= baseline_metrics["shape_cosine"] + float(spec["better_shape_margin"])
    )

    _plot_outputs(
        spec,
        baseline_res["target_field"],
        baseline_metrics,
        ref_metrics,
        baseline_res["loss_history"],
        ref_res["loss_history"],
        artifacts_dir,
    )

    summary = {
        "task": "task1_multifocus_power_ratio",
        "spec": spec,
        "timing_seconds": {
            "baseline": round(t1 - t0, 3),
            "reference": round(t2 - t1, 3),
        },
        "baseline": {
            "metrics": {k: v for k, v in baseline_metrics.items() if k != "intensity"},
            "valid": baseline_valid,
        },
        "reference": {
            "oracle_backend": ref_res.get("oracle_backend", "unknown"),
            "metrics": {k: v for k, v in ref_metrics.items() if k != "intensity"},
            "better_than_baseline": reference_better,
        },
    }

    with open(artifacts_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
