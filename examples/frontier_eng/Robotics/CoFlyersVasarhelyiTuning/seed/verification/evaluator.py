from __future__ import annotations

import argparse
import importlib.util
import json
import math
import traceback
from pathlib import Path
from typing import Any

import numpy as np


PARAMETER_KEYS = [
    "r_rep_0",
    "p_rep",
    "r_frict_0",
    "c_frict",
    "v_frict",
    "p_frict",
    "a_frict",
    "r_shill_0",
    "v_shill",
    "p_shill",
    "a_shill",
]
PARAMETER_BOUNDS = {
    "r_rep_0": (0.05, 4.0),
    "p_rep": (0.01, 2.0),
    "r_frict_0": (0.2, 12.0),
    "c_frict": (0.001, 1.5),
    "v_frict": (0.001, 1.5),
    "p_frict": (0.05, 12.0),
    "a_frict": (0.001, 1.5),
    "r_shill_0": (0.05, 2.5),
    "v_shill": (0.05, 3.0),
    "p_shill": (0.05, 12.0),
    "a_shill": (0.001, 1.5),
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _load_reference(benchmark_root: Path) -> dict[str, Any]:
    return json.loads((benchmark_root / "references" / "coflyers_cases.json").read_text(encoding="utf-8"))


def _load_candidate_module(candidate_path: Path):
    spec = importlib.util.spec_from_file_location("candidate_submission", str(candidate_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load candidate module from {candidate_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _generate_initial_state(global_cfg: dict[str, Any], seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    number = int(global_cfg["number"])
    delta_r = float(global_cfg["delta_r"])
    x_min = float(global_cfg["map_x_range"][0])
    initial_height = float(global_cfg["initial_height"])
    nsqrt = int(math.ceil(math.sqrt(number)))
    row_center = math.floor((number - 1) / nsqrt) / 2.0

    ids = np.arange(number, dtype=float)
    x = (np.mod(ids, nsqrt) * delta_r) + x_min + delta_r
    y = ((np.floor(ids / nsqrt)) - row_center) * delta_r
    positions3d = np.stack([x, y, np.full(number, initial_height)], axis=1)

    rng = np.random.default_rng(seed)
    velocities3d = (rng.random((number, 3)) - 0.5) * 0.001
    if str(global_cfg.get("motion_model_type", "")).lower() == "quadcopter":
        velocities3d[:, 2] = 0.0
    return positions3d[:, :2], velocities3d[:, :2]


def _generate_boundary_shills(global_cfg: dict[str, Any], spacing: float) -> tuple[np.ndarray, np.ndarray]:
    x_min, x_max = map(float, global_cfg["map_x_range"])
    y_min, y_max = map(float, global_cfg["map_y_range"])
    spacing = max(float(spacing), 0.25)
    xs = np.arange(x_min, x_max + 0.5 * spacing, spacing)
    ys = np.arange(y_min, y_max + 0.5 * spacing, spacing)

    points: list[tuple[float, float]] = []
    normals: list[tuple[float, float]] = []
    for y in ys:
        points.append((x_min, float(y)))
        normals.append((1.0, 0.0))
        points.append((x_max, float(y)))
        normals.append((-1.0, 0.0))
    for x in xs:
        points.append((float(x), y_min))
        normals.append((0.0, 1.0))
        points.append((float(x), y_max))
        normals.append((0.0, -1.0))

    dedup: dict[tuple[float, float], tuple[float, float]] = {}
    for point, normal in zip(points, normals):
        dedup.setdefault(point, normal)
    pos = np.array(list(dedup.keys()), dtype=float)
    vel = np.array(list(dedup.values()), dtype=float)
    return pos, vel


def _dfunction(r: np.ndarray, a: float, p: float) -> np.ndarray:
    out = np.zeros_like(r, dtype=float)
    threshold = a / (p * p)
    temp = r < threshold
    cond1 = (r > 0.0) & temp
    cond2 = ~temp
    out[cond1] = r[cond1] * p
    out[cond2] = np.sqrt(np.maximum(0.0, 2.0 * a * r[cond2] - (a * a) / (p * p)))
    return out


def _clip_norm_rows(values: np.ndarray, max_norm: float) -> np.ndarray:
    norms = np.linalg.norm(values, axis=1)
    scale = np.ones_like(norms)
    mask = norms > max_norm
    scale[mask] = max_norm / norms[mask]
    return values * scale[:, None]


def _validate_and_merge_params(baseline_params: dict[str, Any], submission: dict[str, Any]) -> dict[str, float]:
    if "params" in submission:
        raw_updates = submission["params"]
        if not isinstance(raw_updates, dict):
            raise TypeError("submission['params'] must be a dict")
    else:
        raw_updates = submission
        if not isinstance(raw_updates, dict):
            raise TypeError("solve(problem) must return a dict")

    merged = {key: float(baseline_params[key]) for key in baseline_params}
    for key in PARAMETER_KEYS:
        if key in raw_updates:
            value = float(raw_updates[key])
            if not np.isfinite(value):
                raise ValueError(f"parameter {key} is not finite")
            lo, hi = PARAMETER_BOUNDS[key]
            merged[key] = min(max(value, lo), hi)
    return merged


def _step_metrics(positions: np.ndarray, velocities: np.ndarray, global_cfg: dict[str, Any]) -> dict[str, float]:
    number = positions.shape[0]
    eval_cfg = global_cfg["evaluation_0"]
    r_coll = float(eval_cfg["r_coll"])
    v_flock = float(eval_cfg["v_flock"])

    delta = positions[:, None, :] - positions[None, :, :]
    dist = np.linalg.norm(delta, axis=2)
    np.fill_diagonal(dist, np.inf)
    pairwise = dist[np.triu_indices(number, k=1)]

    phi_coll = float(np.mean(pairwise < r_coll)) if pairwise.size else 0.0
    min_dist = float(np.min(pairwise)) if pairwise.size else float("inf")
    phi_mnd = float(r_coll / min_dist) if pairwise.size and min_dist > 1e-12 else 0.0

    speed = np.linalg.norm(velocities, axis=1)
    unit = np.zeros_like(velocities)
    nz = speed > 1e-12
    unit[nz] = velocities[nz] / speed[nz, None]
    mean_unit = np.mean(unit, axis=0)
    if number > 1:
        phi_corr = float((np.linalg.norm(mean_unit) ** 2 * number - 1.0) / (number - 1.0))
    else:
        phi_corr = float(np.linalg.norm(mean_unit) ** 2)
    phi_vel = float(np.mean(speed) / v_flock) if v_flock > 0 else 0.0

    x_min, x_max = map(float, global_cfg["map_x_range"])
    y_min, y_max = map(float, global_cfg["map_y_range"])
    out = (
        (positions[:, 0] < x_min)
        | (positions[:, 0] > x_max)
        | (positions[:, 1] < y_min)
        | (positions[:, 1] > y_max)
    )
    wall_margin = np.minimum.reduce([
        positions[:, 0] - x_min,
        x_max - positions[:, 0],
        positions[:, 1] - y_min,
        y_max - positions[:, 1],
    ])
    near_wall = wall_margin < (r_coll / 2.0)
    phi_wall = float(np.mean(out | near_wall))

    return {
        "phi_corr": phi_corr,
        "phi_vel": phi_vel,
        "phi_coll": phi_coll,
        "phi_wall": phi_wall,
        "phi_mnd": phi_mnd,
        "min_pairwise_distance": min_dist,
    }


def _fitness_components(phi_vel: float, phi_coll: float, phi_wall: float, phi_corr: float, a_tol: float) -> dict[str, float]:
    f_speed = max(phi_vel, 0.0)
    f_coll = (a_tol * a_tol) / ((phi_coll + a_tol) ** 2)
    f_wall = (a_tol * a_tol) / ((phi_wall + a_tol) ** 2)
    f_corr = max(phi_corr, 0.0)
    product = f_speed * f_coll * f_wall * f_corr
    original_fitness = 1.0 - product
    return {
        "f_speed": f_speed,
        "f_coll": f_coll,
        "f_wall": f_wall,
        "f_corr": f_corr,
        "coflyers_product": product,
        "original_fitness": original_fitness,
    }


def simulate_case(global_cfg: dict[str, Any], params: dict[str, float], *, horizon_scale: float = 1.0) -> dict[str, Any]:
    point_mass = global_cfg["point_mass"]
    dt = float(global_cfg["sample_time_control_upper"])
    steps = max(1, int(round(float(global_cfg["time_max"]) * horizon_scale / dt)))
    positions, velocities = _generate_initial_state(global_cfg, seed=0)
    shill_pos, shill_vel = _generate_boundary_shills(global_cfg, float(params.get("dr_shill", 1.0)))
    a_max = float(point_mass["a_max"])
    v_max_pm = float(point_mass["v_max"])
    T_v = float(point_mass["T_v"])
    eval_cfg = global_cfg["evaluation_0"]
    a_tol = float(eval_cfg["a_tol"])
    number = positions.shape[0]

    phi_corr_sum = 0.0
    phi_vel_sum = 0.0
    phi_coll_sum = 0.0
    phi_wall_sum = 0.0
    phi_mnd_sum = 0.0
    min_pairwise_distance = float("inf")
    max_wall_ratio = 0.0
    max_collision_ratio = 0.0

    for _ in range(steps):
        delta = positions[:, None, :] - positions[None, :, :]
        dist = np.linalg.norm(delta, axis=2)
        np.fill_diagonal(dist, np.inf)
        neighbors = dist < float(params["r_com"])

        speed = np.linalg.norm(velocities, axis=1)
        v_flock = np.zeros_like(velocities)
        nz = speed > 1e-12
        v_flock[nz] = velocities[nz] / speed[nz, None]
        v_flock[~nz] = np.array([1.0, 0.0])
        v_flock = v_flock * float(params["v_flock"])

        rep_mask = dist < float(params["r_rep_0"])
        rep_scale = np.zeros_like(dist)
        rep_scale[rep_mask] = (float(params["r_rep_0"]) - dist[rep_mask]) / np.maximum(dist[rep_mask], 1e-12)
        v_rep = float(params["p_rep"]) * np.sum(rep_scale[:, :, None] * delta, axis=1)

        rel_vel = velocities[:, None, :] - velocities[None, :, :]
        rel_speed = np.linalg.norm(rel_vel, axis=2)
        vij_frict = np.maximum(
            float(params["v_frict"]),
            _dfunction(dist - float(params["r_frict_0"]), float(params["a_frict"]), float(params["p_frict"])),
        )
        frict_mask = neighbors & (rel_speed > vij_frict)
        frict_scale = np.zeros_like(rel_speed)
        frict_scale[frict_mask] = (rel_speed[frict_mask] - vij_frict[frict_mask]) / np.maximum(rel_speed[frict_mask], 1e-12)
        v_frict = -float(params["c_frict"]) * np.sum(frict_scale[:, :, None] * rel_vel, axis=1)

        if shill_pos.size:
            delta_s = positions[:, None, :] - shill_pos[None, :, :]
            dist_s = np.linalg.norm(delta_s, axis=2)
            in_com_s = dist_s < float(params["r_com"])
            vel_rel_s = velocities[:, None, :] - float(params["v_shill"]) * shill_vel[None, :, :]
            rel_s_speed = np.linalg.norm(vel_rel_s, axis=2)
            vis_frict = _dfunction(
                dist_s - float(params["r_shill_0"]),
                float(params["a_shill"]),
                float(params["p_shill"]),
            )
            shill_mask = in_com_s & (rel_s_speed > vis_frict)
            shill_scale = np.zeros_like(rel_s_speed)
            shill_scale[shill_mask] = (rel_s_speed[shill_mask] - vis_frict[shill_mask]) / np.maximum(rel_s_speed[shill_mask], 1e-12)
            v_shill = -np.sum(shill_scale[:, :, None] * vel_rel_s, axis=1)
        else:
            v_shill = np.zeros_like(velocities)

        vel_desired = v_flock + v_rep + v_frict + v_shill
        vel_desired = _clip_norm_rows(vel_desired, float(params["v_max"]))

        accelerations = (vel_desired - velocities) / max(T_v, 1e-12)
        accelerations = _clip_norm_rows(accelerations, a_max)
        velocities = velocities + accelerations * dt
        velocities = _clip_norm_rows(velocities, v_max_pm)
        positions = positions + velocities * dt

        metrics = _step_metrics(positions, velocities, global_cfg)
        phi_corr_sum += metrics["phi_corr"]
        phi_vel_sum += metrics["phi_vel"]
        phi_coll_sum += metrics["phi_coll"]
        phi_wall_sum += metrics["phi_wall"]
        phi_mnd_sum += metrics["phi_mnd"]
        min_pairwise_distance = min(min_pairwise_distance, metrics["min_pairwise_distance"])
        max_wall_ratio = max(max_wall_ratio, metrics["phi_wall"])
        max_collision_ratio = max(max_collision_ratio, metrics["phi_coll"])

    phi_corr = phi_corr_sum / steps
    phi_vel = phi_vel_sum / steps
    phi_coll = phi_coll_sum / steps
    phi_wall = phi_wall_sum / steps
    phi_mnd = phi_mnd_sum / steps
    fitness = _fitness_components(phi_vel, phi_coll, phi_wall, phi_corr, a_tol)

    return {
        "valid": 1.0,
        "score": float(100.0 * fitness["coflyers_product"]),
        "original_fitness": float(fitness["original_fitness"]),
        "coflyers_product": float(fitness["coflyers_product"]),
        "phi_corr": float(phi_corr),
        "phi_vel": float(phi_vel),
        "phi_coll": float(phi_coll),
        "phi_wall": float(phi_wall),
        "phi_mnd": float(phi_mnd),
        "max_wall_ratio": float(max_wall_ratio),
        "max_collision_ratio": float(max_collision_ratio),
        "min_pairwise_distance": float(min_pairwise_distance),
        "steps": float(steps),
        "number": float(number),
    }


def evaluate_candidate(candidate_path: Path, benchmark_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    reference = _load_reference(benchmark_root)
    module = _load_candidate_module(candidate_path)
    solve_fn = getattr(module, "solve", None)
    if not callable(solve_fn):
        raise AttributeError("candidate module must define solve(problem)")

    case_results: list[dict[str, Any]] = []
    for case in reference["cases"]:
        problem = {
            "case_id": case["case_id"],
            "baseline_params": case["baseline_params"],
            "global_config": reference["global_config"],
        }
        submission = solve_fn(problem)
        if not isinstance(submission, dict):
            raise TypeError(f"solve(problem) must return a dict, got {type(submission)!r}")
        params = _validate_and_merge_params(case["baseline_params"], submission)
        result = simulate_case(reference["global_config"], params)
        result["case_id"] = case["case_id"]
        result["source_url"] = case["source_url"]
        result["params"] = {key: params[key] for key in PARAMETER_KEYS}
        case_results.append(result)

    count = max(len(case_results), 1)
    metrics = {
        "combined_score": float(sum(item["score"] for item in case_results) / count),
        "valid": 1.0,
        "case_count": float(len(case_results)),
        "mean_original_fitness": float(sum(item["original_fitness"] for item in case_results) / count),
        "mean_phi_corr": float(sum(item["phi_corr"] for item in case_results) / count),
        "mean_phi_vel": float(sum(item["phi_vel"] for item in case_results) / count),
        "mean_phi_coll": float(sum(item["phi_coll"] for item in case_results) / count),
        "mean_phi_wall": float(sum(item["phi_wall"] for item in case_results) / count),
        "mean_phi_mnd": float(sum(item["phi_mnd"] for item in case_results) / count),
        "worst_min_pairwise_distance": float(min(item["min_pairwise_distance"] for item in case_results)),
    }
    artifacts = {
        "benchmark": "Robotics/CoFlyersVasarhelyiTuning",
        "candidate_path": str(candidate_path),
        "source_repo": reference["source_repo"],
        "cases": case_results,
    }
    return metrics, artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a candidate on the original CoFlyers Vasarhelyi tuning cases.")
    parser.add_argument("candidate", nargs="?", default="scripts/init.py")
    parser.add_argument("--metrics-out", default="metrics.json")
    parser.add_argument("--artifacts-out", default="artifacts.json")
    args = parser.parse_args()

    benchmark_root = Path(__file__).resolve().parents[1]
    candidate_path = Path(args.candidate)
    if not candidate_path.is_absolute():
        candidate_path = (Path.cwd() / candidate_path).resolve()
    metrics_path = Path(args.metrics_out)
    artifacts_path = Path(args.artifacts_out)
    if not metrics_path.is_absolute():
        metrics_path = (Path.cwd() / metrics_path).resolve()
    if not artifacts_path.is_absolute():
        artifacts_path = (Path.cwd() / artifacts_path).resolve()

    try:
        metrics, artifacts = evaluate_candidate(candidate_path, benchmark_root)
    except Exception as exc:
        metrics = {"combined_score": 0.0, "valid": 0.0, "error": str(exc)}
        artifacts = {
            "benchmark": "Robotics/CoFlyersVasarhelyiTuning",
            "candidate_path": str(candidate_path),
            "traceback": traceback.format_exc(),
        }

    _write_json(metrics_path, metrics)
    _write_json(artifacts_path, artifacts)
    print(json.dumps(metrics, ensure_ascii=False))
    return 0 if float(metrics.get("valid", 0.0)) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
