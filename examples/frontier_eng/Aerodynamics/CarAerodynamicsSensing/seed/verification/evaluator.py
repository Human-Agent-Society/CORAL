#!/usr/bin/env python3
"""Evaluator for CarAerodynamicsSensing."""

import argparse
import json
import os
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

TASK_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = TASK_ROOT / "data" / "physense_car_data"
CKPT_PATH = TASK_ROOT / "data" / "physense_car_ckpt" / "physense_transolver_car_base.pth"
ALT_CKPT_PATH = (
    TASK_ROOT
    / "data"
    / "physense_car_ckpt"
    / "physense_transolver_car_best_base.pth"
)
if not CKPT_PATH.exists() and ALT_CKPT_PATH.exists():
    CKPT_PATH = ALT_CKPT_PATH

SENSOR_NUM = 30
CASE_START = 76
CASE_END = 100
SAMPLE_K = 10
SAMPLE_SEED = 2025

SIGMA_CLIP = 3.0
P_MIN = -844.3360
P_MAX = 602.6890


def _is_frontier_repo_root(path: Path) -> bool:
    return (path / "frontier_eval").is_dir() and (path / "benchmarks").is_dir()


def find_frontier_engineering_root(start: Path) -> Path:
    env = (os.environ.get("FRONTIER_ENGINEERING_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()

    for parent in [start] + list(start.parents):
        if _is_frontier_repo_root(parent):
            return parent

    raise RuntimeError(
        "Could not locate Frontier-Engineering repo root (missing `frontier_eval/` and `benchmarks/`)."
    )


def find_physense_car_dir(repo_root: Path) -> Path:
    candidates: list[Path] = []
    env = (os.environ.get("PHYSENSE_ROOT") or os.environ.get("PHYSENSE_REPO_ROOT") or "").strip()
    if env:
        candidates.append(Path(env).expanduser().resolve())
    candidates += [
        repo_root / "third_party" / "PhySense",
        repo_root / "PhySense",
        repo_root.parent / "PhySense",
    ]

    for base in candidates:
        base = base.expanduser().resolve()
        if base.name == "Car-Aerodynamics" and base.is_dir():
            return base

        car = (base / "Car-Aerodynamics").resolve()
        if car.is_dir():
            return car

    raise RuntimeError(
        "Could not find `PhySense/Car-Aerodynamics`.\n"
        "Fix by cloning the PhySense repo into one of:\n"
        "  <repo>/third_party/PhySense/Car-Aerodynamics\n"
        "  <workspace>/PhySense/Car-Aerodynamics\n"
        "or set env `PHYSENSE_ROOT=/path/to/PhySense` (or to the Car-Aerodynamics folder)."
    )


def load_case(case_id: int, data_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    pressure_path = data_dir / "pressure_files" / f"case_{case_id}_p_car_patch.raw"
    if not pressure_path.exists():
        raise FileNotFoundError(f"Missing pressure file: {pressure_path}")

    arr = np.loadtxt(pressure_path, comments="#", dtype=np.float32)
    coords = arr[:, :3]
    pressures = arr[:, 3]

    mean = pressures.mean()
    std = pressures.std()
    lower = mean - SIGMA_CLIP * std
    upper = mean + SIGMA_CLIP * std
    mask = (pressures >= lower) & (pressures <= upper)

    coords = coords[mask]
    pressures = pressures[mask]
    pressures = (pressures - P_MIN) / (P_MAX - P_MIN)

    return coords, pressures


def load_reference_points(ref_path: Path, data_dir: Path) -> np.ndarray:
    if ref_path.exists():
        points = np.load(ref_path)
    else:
        points, _ = load_case(1, data_dir)
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(ref_path, points)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("Reference points must have shape (M, 3).")
    return points


def parse_submission(path: Path, max_index: int) -> list[int]:
    if not path.exists():
        raise FileNotFoundError(f"Missing submission file: {path}")
    data = json.loads(path.read_text())
    if isinstance(data, list):
        indices = data
    elif isinstance(data, dict) and "indices" in data:
        indices = data["indices"]
    else:
        raise ValueError("Submission must be a list or a dict with key 'indices'.")

    if len(indices) != SENSOR_NUM:
        raise ValueError(f"Expected {SENSOR_NUM} indices, got {len(indices)}")
    if len(set(indices)) != SENSOR_NUM:
        raise ValueError("Indices must be unique.")
    for idx in indices:
        if not isinstance(idx, int):
            raise ValueError("All indices must be integers.")
        if idx < 0 or idx >= max_index:
            raise ValueError(f"Index out of range: {idx} (max {max_index - 1})")
    return indices


def select_cases() -> list[int]:
    cases = list(range(CASE_START, CASE_END + 1))
    rng = random.Random(SAMPLE_SEED)
    selected = rng.sample(cases, SAMPLE_K)
    selected.sort()
    return selected


def snap_to_case(ref_points: np.ndarray, case_pos: torch.Tensor) -> torch.Tensor:
    ref_t = torch.tensor(ref_points, device=case_pos.device, dtype=case_pos.dtype)
    dist = torch.cdist(ref_t, case_pos)
    idx = torch.argmin(dist, dim=1)
    return case_pos[idx]


def load_model(device: torch.device):
    repo_root = find_frontier_engineering_root(Path(__file__).resolve())
    physense_car = find_physense_car_dir(repo_root)
    if str(physense_car) not in sys.path:
        sys.path.insert(0, str(physense_car))

    from models import physense_transolver_car_walk

    cls = getattr(physense_transolver_car_walk, "Physics_Attention_Irregular_Mesh", None)
    if cls is not None and not getattr(cls, "_frontier_cublas_workaround_applied", False):
        import torch.nn.functional as F

        def _safe_forward(self, x: torch.Tensor) -> torch.Tensor:
            B, N, _ = x.shape

            fx_mid = (
                self.in_project_fx(x)
                .reshape(B, N, self.heads, self.dim_head)
                .permute(0, 2, 1, 3)
                .contiguous()
            )  # (B, H, N, C)
            x_mid = (
                self.in_project_x(x)
                .reshape(B, N, self.heads, self.dim_head)
                .permute(0, 2, 1, 3)
                .contiguous()
            )  # (B, H, N, C)

            slice_weights = self.softmax(self.in_project_slice(x_mid) / self.temperature)  # (B, H, N, G)
            slice_norm = slice_weights.sum(2)  # (B, H, G)

            G = int(slice_weights.shape[-1])
            slice_token = torch.empty(
                (B, self.heads, G, self.dim_head),
                device=x.device,
                dtype=x.dtype,
            )
            for b in range(B):
                for h in range(self.heads):
                    w_t = slice_weights[b, h].transpose(0, 1).contiguous()  # (G, N)
                    slice_token[b, h] = w_t.mm(fx_mid[b, h])  # (G, C)

            slice_token = slice_token / (slice_norm + 1e-5).unsqueeze(-1)

            q_slice_token = self.to_q(slice_token)
            k_slice_token = self.to_k(slice_token)
            v_slice_token = self.to_v(slice_token)

            out_slice_token = F.scaled_dot_product_attention(
                q_slice_token,
                k_slice_token,
                v_slice_token,
                dropout_p=0.1 if self.training else 0.0,
            )

            out_x = torch.empty(
                (B, self.heads, N, self.dim_head),
                device=x.device,
                dtype=x.dtype,
            )
            for b in range(B):
                for h in range(self.heads):
                    out_x[b, h] = slice_weights[b, h].mm(out_slice_token[b, h])

            out_x = out_x.permute(0, 2, 1, 3).contiguous().view(B, N, self.heads * self.dim_head)
            return self.to_out(out_x)

        cls.forward = _safe_forward
        cls._frontier_cublas_workaround_applied = True

    model = physense_transolver_car_walk.Model(
        n_hidden=374,
        n_layers=12,
        space_dim=3,
        fun_dim=0,
        n_head=8,
        mlp_ratio=2,
        out_dim=1,
        slice_num=32,
        unified_pos=1,
    ).to(device)

    if not CKPT_PATH.exists():
        raise FileNotFoundError(f"Missing checkpoint: {CKPT_PATH}")
    state = torch.load(CKPT_PATH, map_location=device)
    model.load_state_dict(state)
    model.eval()
    return model


def evaluate(submission_path: Path) -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for this evaluator.")
    device = torch.device("cuda")

    task_root = Path(__file__).resolve().parents[1]
    ref_path = task_root / "references" / "car_surface_points.npy"

    ref_points = load_reference_points(ref_path, DATA_DIR)
    indices = parse_submission(submission_path, ref_points.shape[0])
    selected_ref = ref_points[np.array(indices, dtype=np.int64)]

    cases = select_cases()
    model = load_model(device)

    rel_losses = []
    with torch.no_grad():
        for case_id in cases:
            torch.manual_seed(SAMPLE_SEED + case_id)

            coords, pressures = load_case(case_id, DATA_DIR)
            pos = torch.from_numpy(coords).to(device)
            y = torch.from_numpy(pressures).to(device).unsqueeze(-1)

            sensor_pos = snap_to_case(selected_ref, pos)
            model.xyz_sens = torch.nn.Parameter(sensor_pos, requires_grad=False)

            data = SimpleNamespace(
                pos=pos,
                y=y,
                v=torch.tensor(0.0, device=device),
                angle=torch.tensor(0.0, device=device),
            )

            rel = model.sample(data).item()
            rel_losses.append(rel)
            print(f"case_{case_id}: rel_l2={rel:.6f}")

    mean_rel = float(np.mean(rel_losses))
    score = 1.0 - mean_rel

    print(f"mean_rel_l2: {mean_rel:.6f}")
    print(f"score: {score:.6f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission", type=Path, default=Path("submission.json"))
    args = parser.parse_args()

    evaluate(args.submission)


if __name__ == "__main__":
    main()
