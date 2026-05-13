import math
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np

# aotools expects numpy.math, which is absent in newer NumPy releases.
if not hasattr(np, "math"):
    np.math = math

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import aotools
from aotools import fouriertransform

from reference_controller import compute_dm_commands as reference_controller


ENERGY_WEIGHT = 2.2
ACTUATOR_LAG = 0.74
SLOPE_DELAY_NOISE = 0.004
PHASE_AR = 0.80

SCORE_ANCHORS = {
    "mean_rms_good": 1.55,
    "mean_rms_bad": 2.25,
    "mean_abs_good": 0.08,
    "mean_abs_bad": 0.36,
    "sparsity_good": 0.40,
    "sparsity_bad": 0.00,
    "strehl_good": 0.22,
    "strehl_bad": 0.08,
}
SCORE_WEIGHTS = {
    "mean_rms": 0.15,
    "mean_abs": 0.60,
    "sparsity": 0.15,
    "strehl": 0.10,
}


def load_callable(module_path: Path, func_name: str):
    spec = importlib.util.spec_from_file_location("candidate_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, func_name):
        raise AttributeError(f"{module_path} missing function: {func_name}")
    return getattr(module, func_name)


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _utility_lower_better(value: float, good: float, bad: float) -> float:
    return _clip01((bad - value) / (bad - good + 1e-12))


def _utility_higher_better(value: float, good: float, bad: float) -> float:
    return _clip01((value - bad) / (good - bad + 1e-12))


def make_system(seed: int = 41):
    rng = np.random.default_rng(seed)

    n_pix = 96
    pupil = aotools.circle(40, n_pix).astype(np.float64)
    valid_mask = pupil > 0

    n_sub = 12
    sub_w = n_pix // n_sub
    active = []
    for i in range(n_sub):
        for j in range(n_sub):
            x1, x2 = i * sub_w, (i + 1) * sub_w
            y1, y2 = j * sub_w, (j + 1) * sub_w
            if pupil[x1:x2, y1:y2].mean() > 0.45:
                active.append((i, j))
    active = np.array(active)
    n_sub_active = len(active)

    def slopes_from_phase(phase):
        gx = np.gradient(phase, axis=0)
        gy = np.gradient(phase, axis=1)
        s = np.zeros((2, n_sub_active), dtype=np.float64)
        for idx, (i, j) in enumerate(active):
            x1, x2 = i * sub_w, (i + 1) * sub_w
            y1, y2 = j * sub_w, (j + 1) * sub_w
            w = pupil[x1:x2, y1:y2]
            denom = w.sum() + 1e-12
            s[0, idx] = (gx[x1:x2, y1:y2] * w).sum() / denom
            s[1, idx] = (gy[x1:x2, y1:y2] * w).sum() / denom
        return s.reshape(-1)

    coords = np.linspace(8, n_pix - 8, 9)
    actuators = [(x, y) for x in coords for y in coords if pupil[int(round(x)), int(round(y))] > 0]
    actuators = np.array(actuators)
    n_act = len(actuators)

    xg, yg = np.meshgrid(np.arange(n_pix), np.arange(n_pix), indexing="ij")
    influence = np.zeros((n_act, n_pix, n_pix), dtype=np.float64)
    for k, (x0, y0) in enumerate(actuators):
        influence[k] = np.exp(-((xg - x0) ** 2 + (yg - y0) ** 2) / (2 * 3.5**2)) * pupil

    def dm_surface(commands):
        return np.tensordot(commands, influence, axes=(0, 0))

    plant_gain = np.clip(rng.normal(1.0, 0.16, size=n_act), 0.66, 1.34)

    def dm_surface_true(commands):
        return np.tensordot(commands * plant_gain, influence, axes=(0, 0))

    h = np.zeros((2 * n_sub_active, n_act), dtype=np.float64)
    for k in range(n_act):
        h[:, k] = slopes_from_phase(influence[k])

    reg_lambda = 1e-3
    normal_matrix = h.T @ h + reg_lambda * np.eye(n_act)
    reconstructor = np.linalg.solve(normal_matrix, h.T)

    n_modes = 25
    zern = aotools.zernikeArray(list(range(2, n_modes + 2)), n_pix, norm="rms") * pupil

    i0 = np.abs(fouriertransform.ft2(pupil.astype(np.complex128), 1.0)) ** 2
    strehl_ref = float(i0.max())

    control_model = {
        "h_matrix": h,
        "lasso_alpha": 2e-4,
        "lasso_max_iter": 2500,
        "lasso_tol": 1e-5,
        "delay_comp_gain": 0.35,
        "temporal_blend": 0.24,
    }

    return {
        "rng": rng,
        "n_pix": n_pix,
        "pupil": pupil,
        "valid_mask": valid_mask,
        "zern": zern,
        "slopes_from_phase": slopes_from_phase,
        "dm_surface": dm_surface,
        "dm_surface_true": dm_surface_true,
        "reconstructor": reconstructor,
        "control_model": control_model,
        "strehl_ref": strehl_ref,
        "n_act": n_act,
    }


def run_eval(controller_fn, sys_cfg, max_voltage=0.35, n_cases=260):
    rng = sys_cfg["rng"]
    pupil = sys_cfg["pupil"]
    valid_mask = sys_cfg["valid_mask"]
    zern = sys_cfg["zern"]
    slopes_from_phase = sys_cfg["slopes_from_phase"]
    dm_surface_true = sys_cfg["dm_surface_true"]
    reconstructor = sys_cfg["reconstructor"]
    control_model = sys_cfg["control_model"]
    strehl_ref = sys_cfg["strehl_ref"]
    n_act = sys_cfg["n_act"]

    rms_list = []
    strehl_list = []
    mean_abs_u = []
    sparsity = []
    example = None

    coeff_state = rng.normal(0.0, 0.45, size=zern.shape[0])
    prev_applied = np.zeros(n_act, dtype=np.float64)
    delayed_slopes = np.zeros(reconstructor.shape[1], dtype=np.float64)

    for i in range(n_cases):
        coeff_state = PHASE_AR * coeff_state + rng.normal(0.0, 0.28, size=zern.shape[0])
        phase = np.tensordot(coeff_state, zern, axes=(0, 0))

        true_slopes = slopes_from_phase(phase)
        slopes = delayed_slopes + rng.normal(0.0, SLOPE_DELAY_NOISE, size=true_slopes.shape)
        delayed_slopes = true_slopes

        cmd = controller_fn(slopes, reconstructor, control_model, prev_applied, max_voltage=max_voltage)
        cmd = np.asarray(cmd, dtype=np.float64)

        if cmd.shape != (n_act,):
            raise ValueError(f"Invalid output shape: {cmd.shape}, expected {(n_act,)}")
        if not np.all(np.isfinite(cmd)):
            raise ValueError("Controller output contains NaN/Inf")
        if np.any(np.abs(cmd) > max_voltage + 1e-8):
            raise ValueError("Controller output violates voltage bounds")

        applied = ACTUATOR_LAG * prev_applied + (1.0 - ACTUATOR_LAG) * cmd
        residual = (phase - dm_surface_true(applied)) * pupil
        rms = float(np.sqrt(np.mean(residual[valid_mask] ** 2)))
        i_psf = np.abs(fouriertransform.ft2((pupil * np.exp(1j * residual)).astype(np.complex128), 1.0)) ** 2
        strehl = float(i_psf.max() / strehl_ref)

        rms_list.append(rms)
        strehl_list.append(strehl)
        mean_abs_u.append(float(np.mean(np.abs(cmd))))
        sparsity.append(float(np.mean(np.abs(cmd) < 1e-5)))
        prev_applied = applied

        if i == 0:
            example = {
                "phase": phase,
                "residual": residual,
                "psf": i_psf / (i_psf.sum() + 1e-12),
            }

    mean_rms = float(np.mean(rms_list))
    mean_strehl = float(np.mean(strehl_list))
    mean_abs_command = float(np.mean(mean_abs_u))
    mean_sparsity = float(np.mean(sparsity))
    raw_cost = float(mean_rms + ENERGY_WEIGHT * mean_abs_command)
    u_mean_rms = _utility_lower_better(mean_rms, SCORE_ANCHORS["mean_rms_good"], SCORE_ANCHORS["mean_rms_bad"])
    u_mean_abs = _utility_lower_better(
        mean_abs_command, SCORE_ANCHORS["mean_abs_good"], SCORE_ANCHORS["mean_abs_bad"]
    )
    u_sparsity = _utility_higher_better(
        mean_sparsity, SCORE_ANCHORS["sparsity_good"], SCORE_ANCHORS["sparsity_bad"]
    )
    u_strehl = _utility_higher_better(mean_strehl, SCORE_ANCHORS["strehl_good"], SCORE_ANCHORS["strehl_bad"])
    score_01 = float(
        SCORE_WEIGHTS["mean_rms"] * u_mean_rms
        + SCORE_WEIGHTS["mean_abs"] * u_mean_abs
        + SCORE_WEIGHTS["sparsity"] * u_sparsity
        + SCORE_WEIGHTS["strehl"] * u_strehl
    )

    return {
        "mean_rms": mean_rms,
        "mean_strehl": mean_strehl,
        "mean_abs_command": mean_abs_command,
        "mean_sparsity": mean_sparsity,
        "raw_cost_lower_is_better": raw_cost,
        "score_0_to_1_higher_is_better": score_01,
        "score_percent": 100.0 * score_01,
        "example": example,
    }


def save_plots(out_dir: Path, baseline_metrics: dict, reference_metrics: dict):
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = ["score_0_to_1_higher_is_better", "mean_rms", "mean_abs_command", "mean_sparsity"]
    bvals = [baseline_metrics[k] for k in labels]
    rvals = [reference_metrics[k] for k in labels]

    plt.figure(figsize=(10, 4))
    x = np.arange(len(labels))
    w = 0.38
    plt.bar(x - w / 2, bvals, width=w, label="baseline")
    plt.bar(x + w / 2, rvals, width=w, label="reference")
    plt.xticks(x, labels, rotation=20)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "metrics_comparison.png", dpi=140)
    plt.close()

    fig, ax = plt.subplots(2, 3, figsize=(11, 6))
    for row, data, title in [
        (0, baseline_metrics["example"], "baseline"),
        (1, reference_metrics["example"], "reference"),
    ]:
        ax[row, 0].imshow(data["phase"], cmap="coolwarm")
        ax[row, 0].set_title(f"{title} phase")
        ax[row, 1].imshow(data["residual"], cmap="coolwarm")
        ax[row, 1].set_title(f"{title} residual")
        ax[row, 2].imshow(np.log10(data["psf"] + 1e-12), cmap="magma")
        ax[row, 2].set_title(f"{title} log10 PSF")
    for a in ax.ravel():
        a.axis("off")
    fig.tight_layout()
    fig.savefig(out_dir / "example_visualization.png", dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate",
        type=str,
        default=str(Path(__file__).resolve().parents[1] / "baseline" / "init.py"),
        help="Path to candidate controller module.",
    )
    parser.add_argument("--max_voltage", type=float, default=0.35)
    parser.add_argument("--cases", type=int, default=260)
    args = parser.parse_args()

    out_dir = Path(__file__).resolve().parent / "outputs"

    candidate_fn = load_callable(Path(args.candidate), "compute_dm_commands")
    sys_cfg = make_system(seed=41)
    baseline_metrics = run_eval(candidate_fn, sys_cfg, max_voltage=args.max_voltage, n_cases=args.cases)

    sys_cfg_ref = make_system(seed=41)
    reference_metrics = run_eval(reference_controller, sys_cfg_ref, max_voltage=args.max_voltage, n_cases=args.cases)

    payload = {
        "task": "task3_energy_aware_control",
        "benchmark_profile": "v3_delay_and_model_mismatch",
        "candidate_module": str(Path(args.candidate).resolve()),
        "oracle_backend": "sklearn.linear_model.Lasso + delay compensation",
        "energy_weight": ENERGY_WEIGHT,
        "actuator_lag": ACTUATOR_LAG,
        "slope_delay_noise": SLOPE_DELAY_NOISE,
        "score_mode": "0_to_1_higher_is_better",
        "score_anchors": SCORE_ANCHORS,
        "score_weights": SCORE_WEIGHTS,
        "baseline": {k: v for k, v in baseline_metrics.items() if k != "example"},
        "reference": {k: v for k, v in reference_metrics.items() if k != "example"},
    }

    save_plots(out_dir, baseline_metrics, reference_metrics)
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(json.dumps(payload, indent=2))
    print(f"Saved figures/metrics to: {out_dir}")


if __name__ == "__main__":
    main()
