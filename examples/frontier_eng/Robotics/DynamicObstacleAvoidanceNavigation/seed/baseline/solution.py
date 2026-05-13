# EVOLVE-BLOCK-START
"""Baseline for DynamicObstacleAvoidanceNavigation.

Policy:
- Static path planning with 2D A* on an obstacle-inflated grid.
- Differential-drive waypoint tracking with strict speed/turn/acceleration clipping.
- One-step dynamic-obstacle safety stop when predicted separation is too small.
"""

from __future__ import annotations

import heapq
import json
from pathlib import Path
from typing import Any

import numpy as np


def wrap_angle(angle: float) -> float:
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


def _in_bounds(pos: np.ndarray, bounds: list[float], radius: float) -> bool:
    xmin, xmax, ymin, ymax = map(float, bounds)
    return bool((xmin + radius <= pos[0] <= xmax - radius) and (ymin + radius <= pos[1] <= ymax - radius))


def _static_collision(pos: np.ndarray, scene: dict[str, Any], inflate: float) -> bool:
    radius = float(scene["robot"]["radius"]) + inflate
    if not _in_bounds(pos, scene["bounds"], radius):
        return True

    for obs in scene["static_obstacles"]:
        if obs["type"] == "circle":
            c = np.array(obs["center"], dtype=float)
            r = float(obs["radius"])
            if np.linalg.norm(pos - c) <= (radius + r):
                return True
        elif obs["type"] == "rect":
            c = np.array(obs["center"], dtype=float)
            h = np.array(obs["half_extents"], dtype=float)
            if _circle_rect_collision(pos, radius, c, h):
                return True
        else:
            return True

    return False


def _segment_in_collision(a: np.ndarray, b: np.ndarray, scene: dict[str, Any], inflate: float) -> bool:
    length = float(np.linalg.norm(b - a))
    samples = max(2, int(np.ceil(length / 0.05)))
    for alpha in np.linspace(0.0, 1.0, samples):
        p = (1.0 - alpha) * a + alpha * b
        if _static_collision(p, scene, inflate):
            return True
    return False


def _build_grid(scene: dict[str, Any], resolution: float, inflate: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    radius = float(scene["robot"]["radius"]) + inflate
    xmin, xmax, ymin, ymax = map(float, scene["bounds"])

    xs = np.arange(xmin + radius, xmax - radius + 1e-9, resolution, dtype=float)
    ys = np.arange(ymin + radius, ymax - radius + 1e-9, resolution, dtype=float)
    occ = np.zeros((len(xs), len(ys)), dtype=bool)

    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            occ[i, j] = _static_collision(np.array([x, y], dtype=float), scene, inflate)

    return xs, ys, occ


def _nearest_index(value: float, grid_values: np.ndarray) -> int:
    return int(np.argmin(np.abs(grid_values - value)))


def _astar_path(scene: dict[str, Any], resolution: float = 0.20, inflate: float = 0.03) -> list[np.ndarray]:
    xs, ys, occ = _build_grid(scene, resolution=resolution, inflate=inflate)
    start = np.array(scene["start"][:2], dtype=float)
    goal = np.array(scene["goal"], dtype=float)

    sx = _nearest_index(start[0], xs)
    sy = _nearest_index(start[1], ys)
    gx = _nearest_index(goal[0], xs)
    gy = _nearest_index(goal[1], ys)

    occ[sx, sy] = False
    occ[gx, gy] = False

    neighbors = [
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),
    ]

    def heuristic(ix: int, iy: int) -> float:
        return float(np.hypot(xs[ix] - xs[gx], ys[iy] - ys[gy]))

    open_heap: list[tuple[float, int, int]] = []
    heapq.heappush(open_heap, (heuristic(sx, sy), sx, sy))
    g_cost = {(sx, sy): 0.0}
    parent: dict[tuple[int, int], tuple[int, int]] = {}
    closed: set[tuple[int, int]] = set()

    while open_heap:
        _, ix, iy = heapq.heappop(open_heap)
        node = (ix, iy)
        if node in closed:
            continue
        closed.add(node)

        if ix == gx and iy == gy:
            break

        for dx, dy in neighbors:
            nx, ny = ix + dx, iy + dy
            if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                continue
            if occ[nx, ny]:
                continue

            step = float(np.hypot(xs[nx] - xs[ix], ys[ny] - ys[iy]))
            cand = g_cost[(ix, iy)] + step
            if cand + 1e-12 < g_cost.get((nx, ny), float("inf")):
                g_cost[(nx, ny)] = cand
                parent[(nx, ny)] = (ix, iy)
                heapq.heappush(open_heap, (cand + heuristic(nx, ny), nx, ny))

    if (gx, gy) not in g_cost:
        return [start, goal]

    path_idx: list[tuple[int, int]] = []
    cur = (gx, gy)
    while True:
        path_idx.append(cur)
        if cur == (sx, sy):
            break
        cur = parent[cur]
    path_idx.reverse()

    dense_path = [np.array([xs[i], ys[j]], dtype=float) for i, j in path_idx]
    simplified = [dense_path[0]]
    anchor = 0
    while anchor < len(dense_path) - 1:
        jump = len(dense_path) - 1
        while jump > anchor + 1 and _segment_in_collision(dense_path[anchor], dense_path[jump], scene, inflate=inflate):
            jump -= 1
        simplified.append(dense_path[jump])
        anchor = jump

    simplified[0] = start
    simplified[-1] = goal
    return simplified


def _track_control(
    scene: dict[str, Any],
    pos: np.ndarray,
    theta: float,
    target: np.ndarray,
    goal: np.ndarray,
    t_next: float,
    dt: float,
    v_prev: float,
    w_prev: float,
) -> tuple[float, float]:
    vmax = float(scene["robot"]["v_max"])
    wmax = float(scene["robot"]["omega_max"])
    amax = float(scene["robot"]["a_max"])

    heading = float(np.arctan2(target[1] - pos[1], target[0] - pos[0]))
    err = wrap_angle(heading - theta)

    if abs(err) > 1.10:
        v_des = 0.08 * vmax
    elif abs(err) > 0.65:
        v_des = 0.40 * vmax
    else:
        v_des = vmax

    dist_goal = float(np.linalg.norm(goal - pos))
    if dist_goal < 2.0:
        v_des = min(v_des, 0.20 + 0.45 * dist_goal)
    if dist_goal < 0.7:
        v_des = min(v_des, 0.10 + 0.40 * dist_goal)
    if dist_goal < 1.0:
        c = float(np.cos(theta))
        if c > 1e-4:
            v_cap = (goal[0] + 0.01 - pos[0]) / (c * dt)
            v_des = min(v_des, max(0.0, v_cap))

    w_des = float(np.clip(3.0 * err, -wmax, wmax))

    for obs in scene["dynamic_obstacles"]:
        dyn_r = float(obs["radius"])
        safe = float(scene["robot"]["radius"]) + dyn_r + 0.07
        risk = False
        for h in range(1, 7):
            tt = t_next + (h - 1) * dt
            dyn = _interp_dynamic_position(obs["trajectory"], tt)
            pred = np.array(
                [
                    pos[0] + v_des * np.cos(theta) * dt * h,
                    pos[1] + v_des * np.sin(theta) * dt * h,
                ],
                dtype=float,
            )
            if np.linalg.norm(pred - dyn) < safe:
                risk = True
                break
        if risk:
            v_des = 0.0
            break

    v_lb = max(-vmax, v_prev - amax * dt)
    v_ub = min(vmax, v_prev + amax * dt)
    w_lb = max(-wmax, w_prev - amax * dt)
    w_ub = min(wmax, w_prev + amax * dt)

    v = float(np.clip(v_des, v_lb, v_ub))
    w = float(np.clip(w_des, w_lb, w_ub))

    pred = np.array([pos[0] + v * np.cos(theta) * dt, pos[1] + v * np.sin(theta) * dt], dtype=float)
    if _static_collision(pred, scene, inflate=0.0):
        v = float(np.clip(0.0, v_lb, v_ub))
        pred = np.array([pos[0] + v * np.cos(theta) * dt, pos[1] + v * np.sin(theta) * dt], dtype=float)
        if _static_collision(pred, scene, inflate=0.0):
            v = float(np.clip(v_prev, v_lb, v_ub))

    return v, w


def build_controls_for_scene(scene: dict[str, Any], dt: float, goal_tol: float) -> dict[str, Any]:
    tmax = float(scene["T_max"])
    x, y, theta = map(float, scene["start"])
    goal = np.array(scene["goal"], dtype=float)
    amax = float(scene["robot"]["a_max"])
    vmax = float(scene["robot"]["v_max"])
    wmax = float(scene["robot"]["omega_max"])

    path = _astar_path(scene, resolution=0.20, inflate=0.03)
    wp_idx = 1 if len(path) > 1 else 0

    timestamps: list[float] = []
    controls: list[list[float]] = []
    v_prev = 0.0
    w_prev = 0.0
    t = 0.0

    while t <= tmax + 1e-12:
        pos = np.array([x, y], dtype=float)
        dist_before = float(np.linalg.norm(goal - pos))

        if dist_before <= goal_tol:
            v_lb = max(-vmax, v_prev - amax * dt)
            v_ub = min(vmax, v_prev + amax * dt)
            w_lb = max(-wmax, w_prev - amax * dt)
            w_ub = min(wmax, w_prev + amax * dt)
            v = float(np.clip(0.0, v_lb, v_ub))
            w = float(np.clip(0.0, w_lb, w_ub))
        else:
            while wp_idx < len(path) - 1 and float(np.linalg.norm(path[wp_idx] - pos)) < 0.30:
                wp_idx += 1
            target = path[wp_idx]

            t_next = t + dt
            v, w = _track_control(
                scene=scene,
                pos=pos,
                theta=theta,
                target=target,
                goal=goal,
                t_next=t_next,
                dt=dt,
                v_prev=v_prev,
                w_prev=w_prev,
            )

        timestamps.append(float(t))
        controls.append([v, w])

        x += v * np.cos(theta) * dt
        y += v * np.sin(theta) * dt
        theta = wrap_angle(theta + w * dt)

        dist_after = float(np.linalg.norm(goal - np.array([x, y], dtype=float)))
        v_prev, w_prev = v, w
        if dist_after <= goal_tol:
            break
        t += dt

    return {"id": scene["id"], "timestamps": timestamps, "controls": controls}


def main() -> None:
    task_root = Path(__file__).resolve().parents[1]
    cfg_path = task_root / "references" / "scenarios.json"
    with cfg_path.open("r", encoding="utf-8-sig") as f:
        cfg = json.load(f)

    dt = float(cfg.get("dt", 0.05))
    goal_tol = float(cfg.get("goal_tolerance", 0.15))
    scenario_entries = [build_controls_for_scene(scene, dt=dt, goal_tol=goal_tol) for scene in cfg["scenarios"]]

    submission = {"scenarios": scenario_entries}
    with open("submission.json", "w", encoding="utf-8") as f:
        json.dump(submission, f, indent=2)

    print("Baseline submission written to submission.json")


if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
