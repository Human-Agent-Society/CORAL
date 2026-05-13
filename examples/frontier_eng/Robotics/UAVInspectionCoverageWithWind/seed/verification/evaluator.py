"""Evaluator for UAVInspectionCoverageWithWind."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


def _wind_velocity(scene: dict[str, Any], t: float) -> np.ndarray:
    wind = scene["wind"]
    base = np.array(wind["base"], dtype=float)
    amp = np.array(wind["amplitude"], dtype=float)
    freq = np.array(wind["frequency"], dtype=float)
    phase = np.array(wind["phase"], dtype=float)
    return base + amp * np.sin(freq * t + phase)


def _in_bounds(pos: np.ndarray, bounds: list[float]) -> bool:
    xmin, xmax, ymin, ymax, zmin, zmax = map(float, bounds)
    return bool(xmin <= pos[0] <= xmax and ymin <= pos[1] <= ymax and zmin <= pos[2] <= zmax)


def _in_no_fly(pos: np.ndarray, no_fly_zones: list[dict[str, Any]]) -> bool:
    for zone in no_fly_zones:
        if zone.get("type") != "box":
            return True
        pmin = np.array(zone["min"], dtype=float)
        pmax = np.array(zone["max"], dtype=float)
        if np.all(pos >= pmin) and np.all(pos <= pmax):
            return True
    return False


def _control_at_time(timestamps: np.ndarray, controls: np.ndarray, t: float) -> np.ndarray:
    idx = int(np.searchsorted(timestamps, t, side="right") - 1)
    idx = max(0, min(idx, len(controls) - 1))
    return controls[idx]


def _dynamic_obstacle_position(obstacle: dict[str, Any], t: float) -> np.ndarray:
    traj = obstacle.get("trajectory", [])
    if not isinstance(traj, list) or len(traj) == 0:
        raise ValueError("invalid_dynamic_obstacle_trajectory")

    t_nodes = np.array([float(node["t"]) for node in traj], dtype=float)
    p_nodes = np.array([node["pos"] for node in traj], dtype=float)
    if p_nodes.ndim != 2 or p_nodes.shape[1] != 3:
        raise ValueError("invalid_dynamic_obstacle_position_shape")
    if not np.all(np.diff(t_nodes) >= 0):
        raise ValueError("non_monotonic_dynamic_obstacle_timestamps")

    if t <= t_nodes[0]:
        return p_nodes[0]
    if t >= t_nodes[-1]:
        return p_nodes[-1]

    idx = int(np.searchsorted(t_nodes, t, side="right") - 1)
    idx = max(0, min(idx, len(t_nodes) - 2))
    t0, t1 = float(t_nodes[idx]), float(t_nodes[idx + 1])
    p0, p1 = p_nodes[idx], p_nodes[idx + 1]
    alpha = 0.0 if t1 <= t0 else float((t - t0) / (t1 - t0))
    return p0 + alpha * (p1 - p0)


def _collides_dynamic_obstacle(pos: np.ndarray, scene: dict[str, Any], t: float) -> bool:
    for obs in scene.get("dynamic_obstacles", []):
        radius = float(obs.get("radius", 0.0))
        if radius <= 0.0:
            continue
        center = _dynamic_obstacle_position(obs, t)
        if float(np.linalg.norm(pos - center)) <= radius + 1e-9:
            return True
    return False


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
    if controls.ndim != 2 or controls.shape[1] != 3:
        return False, "controls_must_be_Nx3"
    if len(timestamps) != len(controls):
        return False, "length_mismatch"
    if abs(float(timestamps[0])) > 1e-12:
        return False, "timestamps_must_start_at_zero"
    if not np.all(np.diff(timestamps) > 0):
        return False, "timestamps_must_be_strictly_increasing"
    if float(timestamps[-1]) > float(scene["T_max"]) + 1e-9:
        return False, "timestamps_exceed_T_max"

    a_max = float(scene["uav"]["a_max"])
    acc_norm = np.linalg.norm(controls, axis=1)
    if np.any(acc_norm > a_max + 1e-9):
        return False, "acceleration_limit_violation"

    return True, "ok"


def _simulate_scene(
    scene: dict[str, Any],
    entry: dict[str, Any],
    dt: float,
    coverage_radius: float,
) -> tuple[bool, dict[str, Any]]:
    ok, reason = _validate_entry(scene, entry)
    if not ok:
        return False, {"success": False, "reason": reason}

    timestamps = np.array(entry["timestamps"], dtype=float)
    controls = np.array(entry["controls"], dtype=float)
    t_max = float(scene["T_max"])
    v_max = float(scene["uav"]["v_max"])
    a_max = float(scene["uav"]["a_max"])
    points = np.array(scene["inspection_points"], dtype=float)

    state = np.array(scene["start"], dtype=float)
    pos = state[:3].copy()
    vel = state[3:].copy()

    if not _in_bounds(pos, scene["bounds"]):
        return False, {"success": False, "reason": "start_out_of_bounds"}
    if _in_no_fly(pos, scene["no_fly_zones"]):
        return False, {"success": False, "reason": "start_in_no_fly_zone"}
    if _collides_dynamic_obstacle(pos, scene, t=0.0):
        return False, {"success": False, "reason": "collision_dynamic_obstacle"}

    visited = np.zeros(len(points), dtype=bool)
    energy = 0.0
    t = 0.0

    while t <= t_max + 1e-9:
        dists = np.linalg.norm(points - pos, axis=1)
        visited |= dists <= coverage_radius
        if _collides_dynamic_obstacle(pos, scene, t):
            return False, {"success": False, "reason": "collision_dynamic_obstacle"}

        u = _control_at_time(timestamps, controls, t)
        a_norm = float(np.linalg.norm(u))
        if a_norm > a_max + 1e-9:
            return False, {"success": False, "reason": "acceleration_limit_violation"}
        energy += float(np.dot(u, u) * dt)

        vel = vel + u * dt
        if float(np.linalg.norm(vel)) > v_max + 1e-9:
            return False, {"success": False, "reason": "speed_limit_violation"}

        wind_v = _wind_velocity(scene, t)
        pos = pos + (vel + wind_v) * dt
        t += dt

        if not _in_bounds(pos, scene["bounds"]):
            return False, {"success": False, "reason": "out_of_bounds"}
        if _in_no_fly(pos, scene["no_fly_zones"]):
            return False, {"success": False, "reason": "entered_no_fly_zone"}
        if _collides_dynamic_obstacle(pos, scene, t):
            return False, {"success": False, "reason": "collision_dynamic_obstacle"}

    coverage_ratio = float(np.mean(visited)) if len(visited) > 0 else 1.0
    scene_score = coverage_ratio * 100.0 - energy * 0.5
    return True, {
        "success": True,
        "coverage_ratio": coverage_ratio,
        "energy": float(energy),
        "scene_score": float(scene_score),
    }


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

    if not isinstance(submission, dict) or not isinstance(submission.get("scenarios"), list):
        return {
            "score": None,
            "feasible": False,
            "details": {"global": {"success": False, "reason": "missing_scenarios_array"}},
        }

    submitted_map = {
        str(entry["id"]): entry
        for entry in submission["scenarios"]
        if isinstance(entry, dict) and "id" in entry
    }

    dt = float(cfg.get("dt", 0.1))
    coverage_radius = float(cfg.get("coverage_radius", 0.45))
    details: dict[str, Any] = {}
    scores: list[float] = []

    for scene in cfg["scenarios"]:
        sid = scene["id"]
        if sid not in submitted_map:
            details[sid] = {"success": False, "reason": "missing_scene_entry"}
            continue

        success, info = _simulate_scene(
            scene=scene,
            entry=submitted_map[sid],
            dt=dt,
            coverage_radius=coverage_radius,
        )
        details[sid] = info
        if success:
            scores.append(float(info["scene_score"]))

    feasible = len(scores) == len(cfg["scenarios"])
    score = float(np.mean(scores)) if feasible else None
    return {"score": score, "feasible": feasible, "details": details}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluator for UAVInspectionCoverageWithWind")
    parser.add_argument("--submission", default="submission.json", help="Path to submission JSON")
    parser.add_argument("--scenarios", default=None, help="Optional scenarios JSON path")
    args = parser.parse_args()

    result = evaluate(Path(args.submission), Path(args.scenarios) if args.scenarios else None)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
