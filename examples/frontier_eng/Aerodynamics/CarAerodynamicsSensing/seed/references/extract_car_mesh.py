#!/usr/bin/env python3
"""Generate car_surface_points.npy from the raw pressure files."""

import argparse
from pathlib import Path

import numpy as np

SIGMA_CLIP = 3.0
DEFAULT_CASE_ID = 1


def load_case_points(data_dir: Path, case_id: int) -> np.ndarray:
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

    return coords[mask]


def main() -> None:
    task_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=task_root / "data" / "physense_car_data",
        help="Dataset root directory containing pressure_files/ and velocity_files/.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "car_surface_points.npy",
        help="Output .npy path for the reference surface point set.",
    )
    parser.add_argument("--case-id", type=int, default=DEFAULT_CASE_ID)
    args = parser.parse_args()

    points = load_case_points(args.data_dir, args.case_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, points)
    print(f"Saved {points.shape[0]} points to {args.output}")


if __name__ == "__main__":
    main()
