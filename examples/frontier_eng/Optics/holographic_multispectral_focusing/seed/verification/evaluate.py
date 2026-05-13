"""Verification script for Task 3: multi-wavelength focusing/splitting."""

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

from torchoptics.profiles import gaussian


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
            "valid_mean_target_efficiency_min": 0.004,
            "valid_mean_crosstalk_max": 0.88,
            "valid_mean_score_min": 0.12,
            "score_eff_target": 0.06,
            "score_spectral_scale": 0.10,
            "better_score_margin": 0.10,
            "better_shape_margin": 0.04,
            "reference_steps": args.reference_steps,
            "reference_lr": 0.045,
        }
    )
    spec["steps"] = args.baseline_steps
    return spec


def _roi_power(field, center: tuple[float, float], radius: float) -> torch.Tensor:
    x, y = field.meshgrid()
    intensity = field.intensity()
    mask = ((x - center[0]) ** 2 + (y - center[1]) ** 2) <= radius**2
    return (intensity * mask.to(intensity.dtype)).sum()


def _cosine_similarity(a: torch.Tensor, b: torch.Tensor) -> float:
    a_f = a.flatten()
    b_f = b.flatten()
    sim = torch.dot(a_f, b_f) / (torch.norm(a_f) * torch.norm(b_f) + 1e-12)
    return float(sim.item())


def _evaluate_solution(result: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    roi_radius = float(spec["roi_radius_m"])

    per_wavelength = []
    target_powers = []

    for idx, field in enumerate(result["input_fields"]):
        out = result["system"].measure_at_z(field, z=spec["output_z"])

        all_designated = torch.stack([_roi_power(out, c, roi_radius) for c in spec["target_centers"]])
        target_power = all_designated[idx]
        target_powers.append(target_power)

        designated_total = all_designated.sum() + 1e-12
        total_power = out.intensity().sum() + 1e-12

        target_eff = (target_power / total_power).item()
        crosstalk = ((designated_total - target_power) / designated_total).item()
        pred_norm = out.intensity() / (out.intensity().sum() + 1e-12)
        target_map = gaussian(spec["shape"], spec["waist_radius"], offset=spec["target_centers"][idx]).real.to(
            pred_norm.device
        )
        target_norm = target_map / (target_map.sum() + 1e-12)
        shape_cosine = _cosine_similarity(pred_norm, target_norm)
        shape_l1 = float(torch.mean(torch.abs(pred_norm - target_norm)).item())

        per_wavelength.append(
            {
                "wavelength": spec["wavelengths"][idx],
                "target_efficiency": target_eff,
                "designated_crosstalk": crosstalk,
                "shape_cosine": shape_cosine,
                "shape_l1": shape_l1,
                "intensity": out.intensity().detach().cpu(),
            }
        )

    target_powers_t = torch.stack(target_powers)
    pred_spectral = target_powers_t / (target_powers_t.sum() + 1e-12)
    target_spectral = torch.tensor(spec["target_spectral_ratios"], dtype=torch.double, device=pred_spectral.device)
    target_spectral = target_spectral / target_spectral.sum()

    spectral_ratio_mae = torch.mean(torch.abs(pred_spectral - target_spectral)).item()
    mean_eff = sum(x["target_efficiency"] for x in per_wavelength) / len(per_wavelength)
    mean_xt = sum(x["designated_crosstalk"] for x in per_wavelength) / len(per_wavelength)
    mean_shape_cosine = sum(x["shape_cosine"] for x in per_wavelength) / len(per_wavelength)
    efficiency_score = float(min(1.0, max(0.0, mean_eff / float(spec["score_eff_target"]))))
    isolation_score = float(min(1.0, max(0.0, 1.0 - mean_xt)))
    spectral_score = math.exp(-spectral_ratio_mae / float(spec["score_spectral_scale"]))
    score = (
        (efficiency_score**0.45)
        * (isolation_score**0.25)
        * (spectral_score**0.20)
        * (mean_shape_cosine**0.10)
    )
    score = float(min(1.0, max(0.0, score)))

    return {
        "per_wavelength": per_wavelength,
        "mean_target_efficiency": mean_eff,
        "mean_crosstalk": mean_xt,
        "mean_shape_cosine": mean_shape_cosine,
        "efficiency_score": efficiency_score,
        "isolation_score": isolation_score,
        "spectral_score": spectral_score,
        "spectral_ratio_mae": spectral_ratio_mae,
        "pred_spectral_ratios": pred_spectral.detach().cpu().tolist(),
        "target_spectral_ratios": target_spectral.detach().cpu().tolist(),
        "mean_score": score,
    }


def _plot_outputs(spec, baseline_eval, reference_eval, baseline_losses, ref_losses, save_dir: Path):
    n = len(spec["wavelengths"])

    fig, axes = plt.subplots(n, 3, figsize=(10, 3.2 * n))
    if n == 1:
        axes = [axes]

    shape = spec["shape"]
    waist = spec["waist_radius"]

    for i, wl in enumerate(spec["wavelengths"]):
        target_map = gaussian(shape, waist, offset=spec["target_centers"][i]).real.detach().cpu()
        base_img = baseline_eval["per_wavelength"][i]["intensity"]
        ref_img = reference_eval["per_wavelength"][i]["intensity"]

        def _norm(x):
            return x / (x.max() + 1e-12)

        axes[i][0].imshow(_norm(target_map), cmap="inferno")
        axes[i][0].set_title(f"{wl*1e9:.0f}nm Target")
        axes[i][1].imshow(_norm(base_img), cmap="inferno")
        axes[i][1].set_title("Baseline")
        axes[i][2].imshow(_norm(ref_img), cmap="inferno")
        axes[i][2].set_title("Reference")

        for j in range(3):
            axes[i][j].axis("off")

    fig.tight_layout()
    fig.savefig(save_dir / "spectral_intensity_maps.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    axes[0].plot(baseline_losses, label="Baseline")
    axes[0].plot(ref_losses, label="Reference")
    axes[0].set_yscale("log")
    axes[0].set_title("Training Loss")
    axes[0].set_xlabel("Iteration")
    axes[0].legend()

    idx = list(range(len(spec["wavelengths"])))
    axes[1].bar([i - 0.25 for i in idx], baseline_eval["target_spectral_ratios"], width=0.25, label="Target")
    axes[1].bar(idx, baseline_eval["pred_spectral_ratios"], width=0.25, label="Baseline")
    axes[1].bar([i + 0.25 for i in idx], reference_eval["pred_spectral_ratios"], width=0.25, label="Reference")
    axes[1].set_xticks(idx)
    axes[1].set_xticklabels([f"{wl*1e9:.0f}nm" for wl in spec["wavelengths"]])
    axes[1].set_title("Spectral Power Ratios")
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(save_dir / "loss_and_spectral_ratios.png", dpi=180)
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

    baseline_module = _load_module(TASK_DIR / "baseline" / "init.py", "task3_baseline_solver")
    reference_module = _load_module(THIS_DIR / "reference_solver.py", "task3_reference_solver")

    spec = _make_spec(baseline_module, args)

    t0 = time.time()
    baseline_res = baseline_module.solve(spec=spec, device=args.device, seed=args.seed)
    t1 = time.time()
    reference_res = reference_module.solve(spec=spec, device=args.device, seed=args.seed)
    t2 = time.time()

    baseline_eval = _evaluate_solution(baseline_res, spec)
    reference_eval = _evaluate_solution(reference_res, spec)

    baseline_valid = (
        baseline_eval["mean_target_efficiency"] >= spec["valid_mean_target_efficiency_min"]
        and baseline_eval["mean_crosstalk"] <= spec["valid_mean_crosstalk_max"]
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
        artifacts_dir,
    )

    summary = {
        "task": "task3_multispectral_focusing",
        "spec": spec,
        "timing_seconds": {
            "baseline": round(t1 - t0, 3),
            "reference": round(t2 - t1, 3),
        },
        "baseline": {
            "valid": baseline_valid,
            "mean_target_efficiency": baseline_eval["mean_target_efficiency"],
            "mean_crosstalk": baseline_eval["mean_crosstalk"],
            "mean_shape_cosine": baseline_eval["mean_shape_cosine"],
            "efficiency_score": baseline_eval["efficiency_score"],
            "isolation_score": baseline_eval["isolation_score"],
            "spectral_score": baseline_eval["spectral_score"],
            "spectral_ratio_mae": baseline_eval["spectral_ratio_mae"],
            "mean_score": baseline_eval["mean_score"],
            "pred_spectral_ratios": baseline_eval["pred_spectral_ratios"],
            "per_wavelength": [
                {k: v for k, v in x.items() if k != "intensity"}
                for x in baseline_eval["per_wavelength"]
            ],
        },
        "reference": {
            "oracle_backend": reference_res.get("oracle_backend", "unknown"),
            "better_than_baseline": reference_better,
            "mean_target_efficiency": reference_eval["mean_target_efficiency"],
            "mean_crosstalk": reference_eval["mean_crosstalk"],
            "mean_shape_cosine": reference_eval["mean_shape_cosine"],
            "efficiency_score": reference_eval["efficiency_score"],
            "isolation_score": reference_eval["isolation_score"],
            "spectral_score": reference_eval["spectral_score"],
            "spectral_ratio_mae": reference_eval["spectral_ratio_mae"],
            "mean_score": reference_eval["mean_score"],
            "pred_spectral_ratios": reference_eval["pred_spectral_ratios"],
            "per_wavelength": [
                {k: v for k, v in x.items() if k != "intensity"}
                for x in reference_eval["per_wavelength"]
            ],
        },
    }

    with open(artifacts_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
