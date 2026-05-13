"""Evaluator for DynamicObstacleAvoidanceNavigation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


def _wrap_angle(angle: float) -> float:
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


def _interp_dynamic_position(trajectory: list[list[float]], t: float) -> np.ndarray:
    pts = np.array(trajectory, dtype=float)
    if t <= pts[0, 0]:
        return pts[0, 1:3]
    if t >= pts[-1, 0]:
        return pts[-1, 1:3]
    idx = int(np.searchsorted(pts[:, 0], t, side="right") - 1)
    t0, x0, y0 = pts[idx]
    t1, x1, y1 = pts[idx + 1]
    ratio = (t - t0) / max(1e-9, (t1 - t0))
    return np.array([x0 + ratio * (x1 - x0), y0 + ratio * (y1 - y0)], dtype=float)


def _circle_rect_collision(circle_center: np.ndarray, circle_radius: float, rect_center: np.ndarray, rect_half: np.ndarray) -> bool:
    diff = np.abs(circle_center - rect_center) - rect_half
    outside = np.maximum(diff, 0.0)
    return float(np.dot(outside, outside)) <= circle_radius * circle_radius


def _in_bounds(x: float, y: float, radius: float, bounds: list[float]) -> bool:
    xmin, xmax, ymin, ymax = bounds
    return (xmin + radius <= x <= xmax - radius) and (ymin + radius <= y <= ymax - radius)


def _collision_check(pos: np.ndarray, robot_radius: float, static_obstacles: list[dict[str, Any]], dynamic_obstacles: list[dict[str, Any]], t: float) -> bool:
    for obs in static_obstacles:
        if obs["type"] == "circle":
            c = np.array(obs["center"], dtype=float)
            r = float(obs["radius"])
            if np.linalg.norm(pos - c) <= (robot_radius + r):
                return True
        elif obs["type"] == "rect":
            c = np.array(obs["center"], dtype=float)
            h = np.array(obs["half_extents"], dtype=float)
            if _circle_rect_collision(pos, robot_radius, c, h):
                return True
        else:
            return True

    for obs in dynamic_obstacles:
        dyn_pos = _interp_dynamic_position(obs["trajectory"], t)
        r = float(obs["radius"])
        if np.linalg.norm(pos - dyn_pos) <= (robot_radius + r):
            return True

    return False


def _control_at_time(timestamps: np.ndarray, controls: np.ndarray, t: float) -> np.ndarray:
    idx = int(np.searchsorted(timestamps, t, side="right") - 1)
    idx = max(0, min(idx, len(controls) - 1))
    return controls[idx]


def _validate_entry(scene: dict[str, Any], entry: dict[str, Any]) -> tuple[bool, str]:
    if "timestamps" not in entry or "controls" not in entry:
        return False, "missing_timestamps_or_controls"

    try:
        timestamps = np.array(entry["timestamps"], dtype=float)
        controls = np.array(entry["controls"], dtype=float)
    except Exception:
        return False, "invalid_numeric_format"

    if timestamps.ndim != 1 or len(timestamps) < 2:
        return False, "invalid_timestamps"
    if controls.ndim != 2 or controls.shape[1] != 2:
        return False, "controls_must_be_Nx2"
    if len(controls) != len(timestamps):
        return False, "length_mismatch"
    if abs(float(timestamps[0])) > 1e-12:
        return False, "timestamps_must_start_at_zero"
    if not np.all(np.diff(timestamps) > 0):
        return False, "timestamps_must_be_strictly_increasing"

    t_max = float(scene["T_max"])
    if float(timestamps[-1]) > t_max + 1e-9:
        return False, "timestamps_exceed_T_max"

    robot = scene["robot"]
    v_max = float(robot["v_max"])
    omega_max = float(robot["omega_max"])
    a_max = float(robot["a_max"])

    if np.any(np.abs(controls[:, 0]) > v_max + 1e-9):
        return False, "v_limit_violation"
    if np.any(np.abs(controls[:, 1]) > omega_max + 1e-9):
        return False, "omega_limit_violation"

    dt_ctrl = np.diff(timestamps)
    dv = np.abs(np.diff(controls[:, 0])) / dt_ctrl
    dw = np.abs(np.diff(controls[:, 1])) / dt_ctrl
    if np.any(dv > a_max + 1e-9) or np.any(dw > a_max + 1e-9):
        return False, "acceleration_limit_violation"

    return True, "ok"


def _simulate_scene(scene: dict[str, Any], entry: dict[str, Any], dt: float, goal_tol: float) -> tuple[bool, dict[str, Any]]:
    ok, reason = _validate_entry(scene, entry)
    if not ok:
        return False, {"success": False, "reason": reason}

    timestamps = np.array(entry["timestamps"], dtype=float)
    controls = np.array(entry["controls"], dtype=float)

    x, y, theta = map(float, scene["start"])
    goal = np.array(scene["goal"], dtype=float)
    t_max = float(scene["T_max"])
    robot_radius = float(scene["robot"]["radius"])

    pos = np.array([x, y], dtype=float)
    if not _in_bounds(x, y, robot_radius, scene["bounds"]):
        return False, {"success": False, "reason": "start_out_of_bounds"}
    if _collision_check(pos, robot_radius, scene["static_obstacles"], scene["dynamic_obstacles"], 0.0):
        return False, {"success": False, "reason": "start_collision"}

    if np.linalg.norm(pos - goal) <= goal_tol:
        return True, {"success": True, "time": 0.0}

    t = 0.0
    for _ in range(int(np.ceil(t_max / dt)) + 2):
        u = _control_at_time(timestamps, controls, t)
        v, w = float(u[0]), float(u[1])

        x += v * np.cos(theta) * dt
        y += v * np.sin(theta) * dt
        theta = _wrap_angle(theta + w * dt)
        t += dt

        pos = np.array([x, y], dtype=float)

        if not _in_bounds(x, y, robot_radius, scene["bounds"]):
            return False, {"success": False, "reason": "out_of_bounds"}
        if _collision_check(pos, robot_radius, scene["static_obstacles"], scene["dynamic_obstacles"], t):
            return False, {"success": False, "reason": "collision"}
        if np.linalg.norm(pos - goal) <= goal_tol:
            return True, {"success": True, "time": float(t)}
        if t > t_max + 1e-9:
            break

    return False, {"success": False, "reason": "timeout"}


def evaluate(submission_path: Path, scenarios_path: Path | None = None) -> dict[str, Any]:
    task_root = Path(__file__).resolve().parents[1]
    scenarios_path = scenarios_path or (task_root / "references" / "scenarios.json")

    with scenarios_path.open("r", encoding="utf-8-sig") as f:
        cfg = json.load(f)

    try:
        with submission_path.open("r", encoding="utf-8-sig") as f:
            submission = json.load(f)
    except Exception as exc:
        return {
            "score": None,
            "feasible": False,
            "details": {"global": {"success": False, "reason": f"invalid_submission_json: {exc}"}},
        }

    if not isinstance(submission, dict) or "scenarios" not in submission or not isinstance(submission["scenarios"], list):
        return {
            "score": None,
            "feasible": False,
            "details": {"global": {"success": False, "reason": "missing_scenarios_array"}},
        }

    scene_cfgs = cfg["scenarios"]
    scene_map = {s["id"]: s for s in scene_cfgs}
    submitted_map = {}
    for entry in submission["scenarios"]:
        if isinstance(entry, dict) and "id" in entry:
            submitted_map[str(entry["id"])] = entry

    dt = float(cfg.get("dt", 0.05))
    goal_tol = float(cfg.get("goal_tolerance", 0.15))

    details: dict[str, Any] = {}
    times: list[float] = []

    for scene in scene_cfgs:
        sid = scene["id"]
        if sid not in submitted_map:
            details[sid] = {"success": False, "reason": "missing_scene_entry"}
            continue

        success, info = _simulate_scene(scene, submitted_map[sid], dt=dt, goal_tol=goal_tol)
        details[sid] = info
        if success:
            times.append(float(info["time"]))

    feasible = len(times) == len(scene_cfgs)
    score = float(np.mean(times)) if feasible else None
    return {"score": score, "feasible": feasible, "details": details}


def main() -> None:
    parser = argparse.ArgumentParser(description="Dynamic obstacle avoidance navigation evaluator")
    parser.add_argument("--submission", default="submission.json", help="Path to submission JSON")
    parser.add_argument("--scenarios", default=None, help="Optional path to scenarios JSON")
    args = parser.parse_args()

    result = evaluate(Path(args.submission), Path(args.scenarios) if args.scenarios else None)
    print(json.dumps(result))


if __name__ == "__main__":
    main()

