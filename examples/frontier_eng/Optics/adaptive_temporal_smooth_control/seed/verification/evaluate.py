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


SLEW_WEIGHT = 5.2
ACTUATOR_LAG = 0.76
SLOPE_DELAY_NOISE = 0.004
ACTUATOR_RATE_LIMIT = 0.055

SCORE_ANCHORS = {
    "mean_rms_good": 1.45,
    "mean_rms_bad": 2.10,
    "mean_slew_good": 0.045,
    "mean_slew_bad": 0.19,
    "strehl_good": 0.24,
    "strehl_bad": 0.10,
}
SCORE_WEIGHTS = {
    "mean_rms": 0.20,
    "mean_slew": 0.65,
    "strehl": 0.15,
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


def make_system(seed: int = 29):
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

    # Plant mismatch: true actuator gains differ from nominal reconstructor model.
    plant_gain = np.clip(rng.normal(1.0, 0.16, size=n_act), 0.66, 1.34)

    def dm_surface_true(commands):
        return np.tensordot(commands * plant_gain, influence, axes=(0, 0))

    h = np.zeros((2 * n_sub_active, n_act), dtype=np.float64)
    for k in range(n_act):
        h[:, k] = slopes_from_phase(influence[k])

    reg_lambda = 1e-3
    g = h.T @ h
    reconstructor = np.linalg.solve(g + reg_lambda * np.eye(n_act), h.T)

    smooth_beta = 18.0
    inv_smooth = np.linalg.inv(g + smooth_beta * np.eye(n_act))
    smooth_reconstructor = inv_smooth @ h.T
    prev_blend = inv_smooth @ (smooth_beta * np.eye(n_act))

    n_modes = 25
    zern = aotools.zernikeArray(list(range(2, n_modes + 2)), n_pix, norm="rms") * pupil
    ar_alpha = np.linspace(0.65, 0.40, n_modes)

    i0 = np.abs(fouriertransform.ft2(pupil.astype(np.complex128), 1.0)) ** 2
    strehl_ref = float(i0.max())

    return {
        "rng": rng,
        "n_pix": n_pix,
        "pupil": pupil,
        "valid_mask": valid_mask,
        "zern": zern,
        "ar_alpha": ar_alpha,
        "slopes_from_phase": slopes_from_phase,
        "dm_surface": dm_surface,
        "dm_surface_true": dm_surface_true,
        "reconstructor": reconstructor,
        "strehl_ref": strehl_ref,
        "n_act": n_act,
        "control_model": {
            "smooth_reconstructor": smooth_reconstructor,
            "prev_blend": prev_blend,
            "reconstructor": reconstructor,
            "delay_prediction_gain": 0.55,
            "command_lowpass": 0.88,
        },
    }


def run_eval(controller_fn, sys_cfg, max_voltage=0.25, episodes=36, steps=70):
    rng = sys_cfg["rng"]
    pupil = sys_cfg["pupil"]
    valid_mask = sys_cfg["valid_mask"]
    zern = sys_cfg["zern"]
    alpha = sys_cfg["ar_alpha"]
    slopes_from_phase = sys_cfg["slopes_from_phase"]
    dm_surface_true = sys_cfg["dm_surface_true"]
    reconstructor = sys_cfg["reconstructor"]
    control_model = sys_cfg["control_model"]
    strehl_ref = sys_cfg["strehl_ref"]
    n_act = sys_cfg["n_act"]

    rms_list = []
    strehl_list = []
    slew_list = []
    example = None

    for ep in range(episodes):
        coeff = rng.normal(0.0, 0.6, size=zern.shape[0])
        prev_applied = np.zeros(n_act, dtype=np.float64)
        prev_cmd = np.zeros(n_act, dtype=np.float64)
        delayed_slopes = np.zeros(reconstructor.shape[1], dtype=np.float64)

        for t in range(steps):
            coeff = alpha * coeff + rng.normal(0.0, 0.35, size=coeff.shape)
            phase = np.tensordot(coeff, zern, axes=(0, 0))

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

            delta_cmd = np.clip(cmd - prev_applied, -ACTUATOR_RATE_LIMIT, ACTUATOR_RATE_LIMIT)
            limited_cmd = prev_applied + delta_cmd
            applied = ACTUATOR_LAG * prev_applied + (1.0 - ACTUATOR_LAG) * limited_cmd
            residual = (phase - dm_surface_true(applied)) * pupil
            rms = float(np.sqrt(np.mean(residual[valid_mask] ** 2)))
            i_psf = np.abs(fouriertransform.ft2((pupil * np.exp(1j * residual)).astype(np.complex128), 1.0)) ** 2
            strehl = float(i_psf.max() / strehl_ref)
            slew = float(np.mean(np.abs(cmd - prev_cmd)))

            rms_list.append(rms)
            strehl_list.append(strehl)
            slew_list.append(slew)

            if ep == 0 and t == 0:
                example = {
                    "phase": phase,
                    "residual": residual,
                    "psf": i_psf / (i_psf.sum() + 1e-12),
                }

            prev_cmd = cmd
            prev_applied = applied

    mean_rms = float(np.mean(rms_list))
    mean_strehl = float(np.mean(strehl_list))
    mean_slew = float(np.mean(slew_list))
    raw_cost = float(mean_rms + SLEW_WEIGHT * mean_slew)
    u_mean_rms = _utility_lower_better(mean_rms, SCORE_ANCHORS["mean_rms_good"], SCORE_ANCHORS["mean_rms_bad"])
    u_mean_slew = _utility_lower_better(
        mean_slew, SCORE_ANCHORS["mean_slew_good"], SCORE_ANCHORS["mean_slew_bad"]
    )
    u_strehl = _utility_higher_better(mean_strehl, SCORE_ANCHORS["strehl_good"], SCORE_ANCHORS["strehl_bad"])
    score_01 = float(
        SCORE_WEIGHTS["mean_rms"] * u_mean_rms
        + SCORE_WEIGHTS["mean_slew"] * u_mean_slew
        + SCORE_WEIGHTS["strehl"] * u_strehl
    )

    return {
        "mean_rms": mean_rms,
        "mean_strehl": mean_strehl,
        "mean_slew": mean_slew,
        "raw_cost_lower_is_better": raw_cost,
        "score_0_to_1_higher_is_better": score_01,
        "score_percent": 100.0 * score_01,
        "example": example,
    }


def save_plots(out_dir: Path, baseline_metrics: dict, reference_metrics: dict):
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = ["score_0_to_1_higher_is_better", "mean_rms", "mean_slew", "mean_strehl"]
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
    parser.add_argument("--max_voltage", type=float, default=0.25)
    parser.add_argument("--episodes", type=int, default=36)
    parser.add_argument("--steps", type=int, default=70)
    args = parser.parse_args()

    out_dir = Path(__file__).resolve().parent / "outputs"

    candidate_fn = load_callable(Path(args.candidate), "compute_dm_commands")
    sys_cfg = make_system(seed=29)
    baseline_metrics = run_eval(
        candidate_fn,
        sys_cfg,
        max_voltage=args.max_voltage,
        episodes=args.episodes,
        steps=args.steps,
    )

    sys_cfg_ref = make_system(seed=29)
    reference_metrics = run_eval(
        reference_controller,
        sys_cfg_ref,
        max_voltage=args.max_voltage,
        episodes=args.episodes,
        steps=args.steps,
    )

    payload = {
        "task": "task2_temporal_smooth_control",
        "benchmark_profile": "v3_delay_and_model_mismatch",
        "candidate_module": str(Path(args.candidate).resolve()),
        "oracle_backend": "delay-compensated analytical smooth controller",
        "slew_weight": SLEW_WEIGHT,
        "actuator_lag": ACTUATOR_LAG,
        "actuator_rate_limit": ACTUATOR_RATE_LIMIT,
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
