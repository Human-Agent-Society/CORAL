"""Evaluator for PIDTuning: 2D quadrotor hover stabilization.

Runs a cascaded PID controller (altitude, horizontal, pitch) on a 2D planar
quadrotor model across multiple flight scenarios.  Score = geometric mean of
1/ITAE across scenarios (higher is better).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """Load pid_config.json from references/."""
    cfg_path = Path(__file__).resolve().parent.parent / "references" / "pid_config.json"
    with cfg_path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 2D Quadrotor Simulation
# ---------------------------------------------------------------------------

def simulate_quadrotor_2d(
    gains: dict[str, float],
    scenario: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Simulate a 2D quadrotor with cascaded PID control.

    States: [x, z, theta, x_dot, z_dot, theta_dot]
    Actuators: total thrust T, torque tau (with 1st-order motor lag).

    Returns dict with 'itae', 'feasible', 'trajectory'.
    """
    quad = cfg["quadrotor"]
    cons = cfg["constraints"]
    sim = cfg["sim"]

    m = quad["mass"]
    I = quad["inertia"]
    g = quad["gravity"]
    drag = quad["drag"]
    angular_drag = quad.get("angular_drag", 0.0)
    tau_motor = quad["motor_time_constant"]
    dt = sim["dt"]
    switch_r = sim["waypoint_switch_radius"]

    max_pitch = cons["max_pitch_rad"]
    max_thrust = cons["max_thrust_factor"] * m * g
    min_z = cons["min_altitude"]

    duration = scenario["duration"]
    wind = np.array(scenario["wind"], dtype=float)
    waypoints = [np.array(wp, dtype=float) for wp in scenario["waypoints"]]
    start = np.array(scenario["start"], dtype=float)

    n_steps = int(duration / dt)

    # State
    x, z = float(start[0]), float(start[1])
    theta = 0.0
    x_dot, z_dot, theta_dot = 0.0, 0.0, 0.0

    # Motor commands (with lag)
    T_cmd, tau_cmd = m * g, 0.0
    T_act, tau_act = m * g, 0.0

    # PID integrators & filtered derivatives
    int_z, int_x, int_theta = 0.0, 0.0, 0.0
    df_z, df_x, df_theta = 0.0, 0.0, 0.0  # filtered derivative state

    wp_idx = 0
    target = waypoints[wp_idx]

    # Initialize previous errors to initial values (avoid derivative kick)
    prev_ez = target[1] - z
    prev_ex = target[0] - x
    prev_etheta = 0.0

    itae = 0.0
    feasible = True

    for i in range(n_steps):
        t = i * dt

        # Waypoint switching
        if wp_idx < len(waypoints) - 1:
            dist_to_wp = math.sqrt((x - target[0]) ** 2 + (z - target[1]) ** 2)
            if dist_to_wp < switch_r:
                wp_idx += 1
                target = waypoints[wp_idx]

        # --- Altitude PID ---
        ez = target[1] - z
        int_z += ez * dt
        raw_dez = (ez - prev_ez) / dt
        alpha_z = dt * gains["N_z"] / (1.0 + dt * gains["N_z"])
        df_z = alpha_z * raw_dez + (1.0 - alpha_z) * df_z
        prev_ez = ez
        thrust_offset = gains["Kp_z"] * ez + gains["Ki_z"] * int_z + gains["Kd_z"] * df_z

        cos_theta = math.cos(theta)
        if abs(cos_theta) > 1e-6:
            T_cmd = (m * g + thrust_offset) / cos_theta
        else:
            T_cmd = max_thrust

        # --- Horizontal PID ---
        ex = target[0] - x
        int_x += ex * dt
        raw_dex = (ex - prev_ex) / dt
        alpha_x = dt * gains["N_x"] / (1.0 + dt * gains["N_x"])
        df_x = alpha_x * raw_dex + (1.0 - alpha_x) * df_x
        prev_ex = ex
        desired_pitch = -(gains["Kp_x"] * ex + gains["Ki_x"] * int_x + gains["Kd_x"] * df_x)
        desired_pitch = np.clip(desired_pitch, -max_pitch, max_pitch)

        # --- Pitch PID ---
        etheta = desired_pitch - theta
        int_theta += etheta * dt
        raw_detheta = (etheta - prev_etheta) / dt
        alpha_theta = dt * gains["N_theta"] / (1.0 + dt * gains["N_theta"])
        df_theta = alpha_theta * raw_detheta + (1.0 - alpha_theta) * df_theta
        prev_etheta = etheta
        tau_cmd = gains["Kp_theta"] * etheta + gains["Ki_theta"] * int_theta + gains["Kd_theta"] * df_theta

        # Clamp thrust
        T_cmd = float(np.clip(T_cmd, 0.0, max_thrust))

        # Motor lag (1st-order)
        alpha_m = dt / (tau_motor + dt)
        T_act = T_act + alpha_m * (T_cmd - T_act)
        tau_act = tau_act + alpha_m * (tau_cmd - tau_act)

        # Physics
        ax = -(T_act / m) * math.sin(theta) - drag * x_dot + wind[0]
        az = (T_act / m) * math.cos(theta) - g - drag * z_dot + wind[1]
        atheta = tau_act / I - angular_drag * theta_dot

        x_dot += ax * dt
        z_dot += az * dt
        theta_dot += atheta * dt
        x += x_dot * dt
        z += z_dot * dt
        theta += theta_dot * dt

        # Constraints
        if abs(theta) > max_pitch:
            feasible = False
            break
        if z < min_z:
            z = min_z
            z_dot = max(z_dot, 0.0)

        # ITAE accumulation
        pos_err = math.sqrt(ex ** 2 + ez ** 2)
        itae += t * pos_err * dt

    return {"itae": itae, "feasible": feasible}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_itae(gains: dict[str, float], cfg: dict[str, Any]) -> float:
    """Run all scenarios and return combined score (geometric mean of 1/ITAE).

    Returns 0.0 if any scenario is infeasible or ITAE is non-positive.
    """
    scenarios = cfg["scenarios"]
    inv_itaes: list[float] = []

    for sc in scenarios:
        result = simulate_quadrotor_2d(gains, sc, cfg)
        if not result["feasible"]:
            return 0.0
        itae = result["itae"]
        if itae <= 0.0:
            return 0.0
        inv_itaes.append(1.0 / itae)

    # Geometric mean
    log_sum = sum(math.log(v) for v in inv_itaes)
    return float(math.exp(log_sum / len(inv_itaes)))


# ---------------------------------------------------------------------------
# Submission loading & validation
# ---------------------------------------------------------------------------

_GAIN_KEYS = [
    "Kp_z", "Ki_z", "Kd_z", "N_z",
    "Kp_x", "Ki_x", "Kd_x", "N_x",
    "Kp_theta", "Ki_theta", "Kd_theta", "N_theta",
]

_KEY_TO_GROUP = {
    "Kp_z": ("altitude", "Kp"), "Ki_z": ("altitude", "Ki"),
    "Kd_z": ("altitude", "Kd"), "N_z": ("altitude", "N"),
    "Kp_x": ("horizontal", "Kp"), "Ki_x": ("horizontal", "Ki"),
    "Kd_x": ("horizontal", "Kd"), "N_x": ("horizontal", "N"),
    "Kp_theta": ("pitch", "Kp"), "Ki_theta": ("pitch", "Ki"),
    "Kd_theta": ("pitch", "Kd"), "N_theta": ("pitch", "N"),
}


def _load_submission(path: Path) -> dict[str, float] | None:
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            raw = json.load(f)
    except Exception as exc:
        print(f"ERROR: invalid submission: {exc}")
        return None

    out: dict[str, float] = {}
    for key in _GAIN_KEYS:
        if key not in raw:
            print(f"ERROR: missing key '{key}'")
            return None
        try:
            out[key] = float(raw[key])
        except Exception:
            print(f"ERROR: key '{key}' is not numeric")
            return None
    return out


def _validate_bounds(gains: dict[str, float], cfg: dict[str, Any]) -> bool:
    gain_ranges = cfg["gains"]
    for key, val in gains.items():
        group, param = _KEY_TO_GROUP[key]
        lo, hi = gain_ranges[group][param]
        if not (lo <= val <= hi):
            print(f"ERROR: {key}={val:.6f} out of range [{lo}, {hi}]")
            return False
    return True


# ---------------------------------------------------------------------------
# Public evaluate
# ---------------------------------------------------------------------------

def evaluate(submission_path: Path) -> float:
    """Load submission, validate, run all scenarios, return combined score."""
    cfg = load_config()
    gains = _load_submission(submission_path)
    if gains is None:
        return 0.0
    if not _validate_bounds(gains, cfg):
        return 0.0

    score = compute_itae(gains, cfg)
    if score > 0.0:
        print(f"VALID combined_score={score:.6f}")
    else:
        print("INFEASIBLE: one or more scenarios failed")
    return score


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="PID tuning evaluator")
    parser.add_argument(
        "candidate",
        nargs="?",
        default=None,
        help="Path to candidate script (runs it, then evaluates submission.json)",
    )
    parser.add_argument(
        "--submission",
        default="submission.json",
        help="Path to submission JSON (used if no candidate script given)",
    )
    args = parser.parse_args()

    if args.candidate:
        import subprocess
        import sys
        import tempfile
        import shutil

        candidate = Path(args.candidate).resolve()
        work_dir = Path(tempfile.mkdtemp(prefix="pid_eval_")).resolve()
        try:
            shutil.copy2(candidate, work_dir / "init.py")
            # Copy references so the candidate can load config
            ref_src = Path(__file__).resolve().parent.parent / "references"
            ref_dst = work_dir / "references"
            shutil.copytree(ref_src, ref_dst)
            proc = subprocess.run(
                [sys.executable, str(work_dir / "init.py")],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            print(proc.stdout)
            if proc.stderr:
                print(proc.stderr)
            if proc.returncode != 0:
                print(f"ERROR: candidate exited with code {proc.returncode}")
                result = {"score": 0.0, "feasible": False}
                print(json.dumps(result))
                return
            submission_path = work_dir / "submission.json"
        except subprocess.TimeoutExpired:
            print("ERROR: candidate timed out")
            result = {"score": 0.0, "feasible": False}
            print(json.dumps(result))
            return
        finally:
            pass  # keep work_dir for evaluation
    else:
        submission_path = Path(args.submission)

    score = evaluate(submission_path)
    result = {"score": score, "feasible": bool(score > 0.0)}
    print(json.dumps(result))

    # Cleanup
    if args.candidate:
        import shutil as _sh
        _sh.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
