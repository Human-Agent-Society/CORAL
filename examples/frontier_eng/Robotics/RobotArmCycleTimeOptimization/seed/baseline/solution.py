# EVOLVE-BLOCK-START
"""Baseline solver for RobotArmCycleTimeOptimization.

Approach:
1. Use a fixed 3-waypoint path (start -> via -> goal).
2. Time-scale the path and binary-search the smallest feasible total time.
3. Feasibility is checked with the same constraints as the evaluator
   (joint limits, velocity, acceleration, and collision in PyBullet).
"""

from __future__ import annotations

import json

import numpy as np
import pybullet as p
import pybullet_data
from scipy.interpolate import CubicSpline

Q_START = np.array([0.0, 0.5, 0.0, -1.5, 0.0, 1.0, 0.0], dtype=float)
Q_VIA = np.array([0.6, 0.1, 0.4, -1.8, 0.2, 0.9, 0.5], dtype=float)
Q_GOAL = np.array([1.2, -0.3, 0.8, -0.8, 0.5, 0.8, 1.0], dtype=float)

MAX_VEL = np.array([1.48, 1.48, 1.74, 1.74, 2.27, 2.27, 2.27], dtype=float)
MAX_ACC = np.array([3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0], dtype=float)
SAMPLES_PER_SEG = 30

OBS_CENTER = [0.45, -0.35, 0.65]
OBS_HALF = [0.08, 0.20, 0.08]


def _joint_index_map(robot_id: int) -> list[int]:
    idxs: list[int] = []
    for j in range(p.getNumJoints(robot_id)):
        info = p.getJointInfo(robot_id, j)
        if info[2] in (p.JOINT_REVOLUTE, p.JOINT_PRISMATIC):
            idxs.append(j)
    return idxs[:7]


def _set_q(robot_id: int, q: np.ndarray, joint_idxs: list[int]) -> None:
    for i, joint_idx in enumerate(joint_idxs):
        p.resetJointState(robot_id, joint_idx, float(q[i]))


def _build_timestamps(total_time: float) -> np.ndarray:
    ratios = np.array([0.0, 0.48, 1.0], dtype=float)
    return total_time * ratios


def _is_feasible(total_time: float, joint_limits: np.ndarray, robot_id: int, obs_id: int, joint_idxs: list[int]) -> bool:
    waypoints = np.vstack([Q_START, Q_VIA, Q_GOAL])
    timestamps = _build_timestamps(total_time)

    cs = CubicSpline(timestamps, waypoints, bc_type="clamped")
    cs_vel = cs.derivative(1)
    cs_acc = cs.derivative(2)

    for seg in range(2):
        t0 = float(timestamps[seg])
        t1 = float(timestamps[seg + 1])
        t_samp = np.linspace(t0, t1, SAMPLES_PER_SEG, endpoint=False)
        q_batch = cs(t_samp)
        v_batch = cs_vel(t_samp)
        a_batch = cs_acc(t_samp)

        for k in range(len(t_samp)):
            q = q_batch[k]
            v = v_batch[k]
            a = a_batch[k]

            if np.any(q < joint_limits[:, 0] - 1e-4) or np.any(q > joint_limits[:, 1] + 1e-4):
                return False
            if np.any(np.abs(v) > MAX_VEL + 1e-4):
                return False
            if np.any(np.abs(a) > MAX_ACC + 1e-4):
                return False

            _set_q(robot_id, q, joint_idxs)
            if len(p.getClosestPoints(robot_id, obs_id, distance=0.0)) > 0:
                return False

    return True


def solve() -> tuple[list[list[float]], list[float]]:
    physics = p.connect(p.DIRECT)
    try:
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.loadURDF("plane.urdf")
        robot_id = p.loadURDF("kuka_iiwa/model.urdf", useFixedBase=True)
        obs_shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=OBS_HALF)
        obs_id = p.createMultiBody(baseMass=0.0, baseCollisionShapeIndex=obs_shape, basePosition=OBS_CENTER)

        joint_idxs = _joint_index_map(robot_id)
        joint_limits = np.array(
            [[p.getJointInfo(robot_id, j)[8], p.getJointInfo(robot_id, j)[9]] for j in joint_idxs],
            dtype=float,
        )

        lower_bound = float(np.max(np.abs(Q_GOAL - Q_START) / (MAX_VEL * 0.95)))
        lo = max(1.0, lower_bound)
        hi = 12.0

        while not _is_feasible(hi, joint_limits, robot_id, obs_id, joint_idxs):
            hi *= 1.5
            if hi > 60.0:
                break

        for _ in range(36):
            mid = 0.5 * (lo + hi)
            if _is_feasible(mid, joint_limits, robot_id, obs_id, joint_idxs):
                hi = mid
            else:
                lo = mid

        best_t = hi
        waypoints = [Q_START.tolist(), Q_VIA.tolist(), Q_GOAL.tolist()]
        timestamps = _build_timestamps(best_t).tolist()
        return waypoints, timestamps
    finally:
        p.disconnect(physics)


def main() -> None:
    waypoints, timestamps = solve()
    submission = {"waypoints": waypoints, "timestamps": timestamps}
    with open("submission.json", "w", encoding="utf-8") as f:
        json.dump(submission, f, indent=2)

    total_time = timestamps[-1]
    print("Baseline submission written to submission.json")
    print(f"Total time: {total_time:.4f} s")


if __name__ == "__main__":
    main()
# EVOLVE-BLOCK-END
