"""PyBullet evaluator for RobotArmCycleTimeOptimization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pybullet as p
import pybullet_data
from scipy.interpolate import CubicSpline

Q_START = np.array([0.0, 0.5, 0.0, -1.5, 0.0, 1.0, 0.0], dtype=float)
Q_GOAL = np.array([1.2, -0.3, 0.8, -0.8, 0.5, 0.8, 1.0], dtype=float)
GOAL_TOL = 0.01
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
    if len(idxs) < 7:
        raise RuntimeError(f"Expected >=7 controllable joints, got {len(idxs)}")
    return idxs[:7]


def _set_q(robot_id: int, q: np.ndarray, joint_idxs: list[int]) -> None:
    for i, joint_idx in enumerate(joint_idxs):
        p.resetJointState(robot_id, joint_idx, float(q[i]))


def _in_collision(robot_id: int, obs_id: int) -> bool:
    return len(p.getClosestPoints(robot_id, obs_id, distance=0.0)) > 0


def _validate_format(waypoints: np.ndarray, timestamps: np.ndarray) -> bool:
    if waypoints.ndim != 2 or waypoints.shape[1] != 7:
        print("ERROR: 'waypoints' must have shape (N, 7).")
        return False
    if len(timestamps) != len(waypoints):
        print("ERROR: 'timestamps' and 'waypoints' length mismatch.")
        return False
    if len(waypoints) < 2:
        print("ERROR: Need at least 2 waypoints.")
        return False
    if abs(float(timestamps[0])) > 1e-12:
        print("ERROR: timestamps[0] must be 0.0.")
        return False
    if not np.all(np.diff(timestamps) > 0):
        print("ERROR: timestamps must be strictly increasing.")
        return False
    if np.max(np.abs(waypoints[0] - Q_START)) > GOAL_TOL:
        print(f"ERROR: start waypoint does not match q_start (tol={GOAL_TOL}).")
        return False
    if np.max(np.abs(waypoints[-1] - Q_GOAL)) > GOAL_TOL:
        print(f"ERROR: final waypoint does not match q_goal (tol={GOAL_TOL}).")
        return False
    return True


def evaluate(submission_path: Path) -> float:
    try:
        with submission_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        waypoints = np.array(data["waypoints"], dtype=float)
        timestamps = np.array(data["timestamps"], dtype=float)
    except Exception as exc:
        print(f"ERROR: invalid submission.json: {exc}")
        return np.inf

    if not _validate_format(waypoints, timestamps):
        return np.inf

    physics = p.connect(p.DIRECT)
    try:
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)
        p.loadURDF("plane.urdf")
        robot_id = p.loadURDF("kuka_iiwa/model.urdf", useFixedBase=True)

        obs_shape = p.createCollisionShape(p.GEOM_BOX, halfExtents=OBS_HALF)
        obs_id = p.createMultiBody(
            baseMass=0.0,
            baseCollisionShapeIndex=obs_shape,
            basePosition=OBS_CENTER,
        )
        joint_idxs = _joint_index_map(robot_id)

        joint_limits = np.array(
            [[p.getJointInfo(robot_id, j)[8], p.getJointInfo(robot_id, j)[9]] for j in joint_idxs],
            dtype=float,
        )
        if np.any(joint_limits[:, 0] >= joint_limits[:, 1]):
            print("ERROR: invalid joint limits from URDF.")
            return np.inf

        cs = CubicSpline(timestamps, waypoints, bc_type="clamped")
        cs_vel = cs.derivative(1)
        cs_acc = cs.derivative(2)

        for seg in range(len(waypoints) - 1):
            t0 = float(timestamps[seg])
            t1 = float(timestamps[seg + 1])
            t_samp = np.linspace(t0, t1, SAMPLES_PER_SEG, endpoint=False)

            q_batch = cs(t_samp)
            v_batch = cs_vel(t_samp)
            a_batch = cs_acc(t_samp)

            for k, t in enumerate(t_samp):
                q = q_batch[k]
                v = v_batch[k]
                a = a_batch[k]

                low = joint_limits[:, 0]
                high = joint_limits[:, 1]
                if np.any(q < low - 1e-4) or np.any(q > high + 1e-4):
                    print(f"ERROR: joint limit violated at seg={seg}, sample={k}.")
                    return np.inf
                if np.any(np.abs(v) > MAX_VEL + 1e-4):
                    print(f"ERROR: velocity limit violated at seg={seg}, sample={k}, t={t:.4f}s.")
                    return np.inf
                if np.any(np.abs(a) > MAX_ACC + 1e-4):
                    print(f"ERROR: acceleration limit violated at seg={seg}, sample={k}, t={t:.4f}s.")
                    return np.inf

                _set_q(robot_id, q, joint_idxs)
                if _in_collision(robot_id, obs_id):
                    print(f"ERROR: collision at seg={seg}, sample={k}, t={t:.4f}s.")
                    return np.inf

        score = float(timestamps[-1])
        print(f"FEASIBLE score={score:.6f} (lower is better)")
        return score
    finally:
        p.disconnect(physics)


def main() -> None:
    parser = argparse.ArgumentParser(description="PyBullet evaluator for robot arm cycle time.")
    parser.add_argument("--submission", default="submission.json")
    args = parser.parse_args()

    score = evaluate(Path(args.submission))
    result = {"score": score if np.isfinite(score) else None, "feasible": bool(np.isfinite(score))}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
