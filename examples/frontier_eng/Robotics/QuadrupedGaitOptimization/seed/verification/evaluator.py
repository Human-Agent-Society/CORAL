"""MuJoCo evaluator for QuadrupedGaitOptimization.

This evaluator uses MuJoCo's Ant model as a compact quadruped proxy.
Score is forward speed over a fixed simulation horizon, with hard safety checks.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np


def _quat_to_roll_pitch(qw: float, qx: float, qy: float, qz: float) -> tuple[float, float]:
    sinr_cosp = 2.0 * (qw * qx + qy * qz)
    cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll = np.arctan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (qw * qy - qz * qx)
    pitch = np.arcsin(np.clip(sinp, -1.0, 1.0))
    return float(roll), float(pitch)


def _leg_phase(t: float, freq: float, offset: float) -> float:
    return (t * freq + offset) % 1.0


def _in_range(v: float, lo: float, hi: float, inclusive_hi: bool = True) -> bool:
    if inclusive_hi:
        return lo <= v <= hi
    return lo <= v < hi


def _load_submission(path: Path) -> dict[str, float] | None:
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            raw = json.load(f)
    except Exception as exc:
        print(f"ERROR: invalid submission: {exc}")
        return None

    keys = [
        "step_frequency",
        "duty_factor",
        "step_length",
        "step_height",
        "phase_FR",
        "phase_RL",
        "phase_RR",
        "lateral_distance",
    ]
    out: dict[str, float] = {}
    for key in keys:
        if key not in raw:
            print(f"ERROR: missing key '{key}'")
            return None
        try:
            out[key] = float(raw[key])
        except Exception:
            print(f"ERROR: key '{key}' is not numeric")
            return None
    return out


def evaluate(submission_path: Path) -> float:
    this_dir = Path(__file__).resolve().parent
    task_root = this_dir.parent
    cfg_path = task_root / "references" / "gait_config.json"

    with cfg_path.open("r", encoding="utf-8-sig") as f:
        cfg = json.load(f)

    params = _load_submission(submission_path)
    if params is None:
        return 0.0

    ranges = cfg["ranges"]
    for key, bounds in ranges.items():
        lo, hi = float(bounds[0]), float(bounds[1])
        inclusive_hi = key not in {"phase_FR", "phase_RL", "phase_RR"}
        if not _in_range(params[key], lo, hi, inclusive_hi=inclusive_hi):
            print(f"ERROR: {key}={params[key]:.4f} out of range [{lo}, {hi}{']' if inclusive_hi else ')'}")
            return 0.0

    duration = float(cfg["eval"]["duration_s"])
    torque_limit = float(cfg["eval"]["torque_limit"])
    att_limit = float(cfg["eval"]["pitch_roll_limit_rad"])
    min_distance = float(cfg["eval"]["min_distance_m"])
    kp = float(cfg["eval"]["control_kp"])
    kd = float(cfg["eval"]["control_kd"])

    model = mujoco.MjModel.from_xml_path(str((task_root / "references" / "ant.xml").resolve()))
    data = mujoco.MjData(model)

    ctrl_min = np.full(model.nu, -1.0)
    ctrl_max = np.full(model.nu, 1.0)
    if model.actuator_ctrllimited is not None and np.any(model.actuator_ctrllimited):
        ctrl_min = model.actuator_ctrlrange[:, 0].copy()
        ctrl_max = model.actuator_ctrlrange[:, 1].copy()

    freq = params["step_frequency"]
    duty = params["duty_factor"]
    step_len = params["step_length"]
    step_h = params["step_height"]
    lateral = params["lateral_distance"]

    phase_leg = {
        "FL": 0.0,
        "FR": params["phase_FR"],
        "RL": params["phase_RL"],
        "RR": params["phase_RR"],
    }

    # Ant actuator index order maps as:
    # [hip_4, ankle_4, hip_1, ankle_1, hip_2, ankle_2, hip_3, ankle_3]
    # Here we pair them into (front-left, front-right, rear-left, rear-right).
    leg_act = {
        "FL": (2, 3),
        "FR": (4, 5),
        "RL": (6, 7),
        "RR": (0, 1),
    }

    hip_amp = np.clip(2.0 * step_len, 0.08, 0.65)
    knee_amp = np.clip(3.0 * step_h, 0.05, 0.85)
    lateral_bias = np.clip((lateral - 0.14) * 4.0, -0.25, 0.25)

    x0 = float(data.qpos[0])
    n_steps = int(duration / model.opt.timestep)

    for i in range(n_steps):
        t = i * model.opt.timestep

        qj = data.qpos[7:15]
        vj = data.qvel[6:14]
        target = np.zeros(8, dtype=float)

        for leg_name, (hip_idx, knee_idx) in leg_act.items():
            ph = _leg_phase(t, freq, phase_leg[leg_name])
            in_stance = ph < duty
            swing = 0.0 if in_stance else (ph - duty) / (1.0 - duty)

            stance_wave = np.sin(2.0 * np.pi * ph)
            swing_wave = np.sin(np.pi * swing)

            sign = 1.0 if leg_name in {"FL", "RR"} else -1.0
            hip_target = sign * hip_amp * stance_wave + (lateral_bias if leg_name in {"FL", "RL"} else -lateral_bias)
            knee_target = -0.45 + knee_amp * swing_wave

            target[hip_idx] = hip_target
            target[knee_idx] = knee_target

        ctrl = kp * (target - qj) - kd * vj
        ctrl = np.clip(ctrl, ctrl_min, ctrl_max)
        data.ctrl[:] = ctrl

        mujoco.mj_step(model, data)

        qw, qx, qy, qz = map(float, data.qpos[3:7])
        roll, pitch = _quat_to_roll_pitch(qw, qx, qy, qz)
        if abs(roll) > att_limit or abs(pitch) > att_limit:
            print(f"ERROR: fell over (roll={roll:.3f}, pitch={pitch:.3f})")
            return 0.0

        if np.any(np.abs(data.actuator_force) > torque_limit + 1e-6):
            print("ERROR: actuator force limit exceeded")
            return 0.0

    distance = float(data.qpos[0] - x0)
    if distance < min_distance:
        print(f"ERROR: insufficient progress ({distance:.4f} m < {min_distance:.4f} m)")
        return 0.0

    speed = distance / duration
    print(f"VALID speed={speed:.6f} m/s, distance={distance:.3f} m over {duration:.1f} s")
    return float(speed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Quadruped gait evaluator (MuJoCo)")
    parser.add_argument("--submission", default="submission.json", help="Path to submission JSON")
    args = parser.parse_args()

    score = evaluate(Path(args.submission))
    result = {"score": score, "feasible": bool(score > 0.0)}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
