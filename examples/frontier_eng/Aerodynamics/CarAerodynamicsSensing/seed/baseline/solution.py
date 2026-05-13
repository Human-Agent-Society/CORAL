#!/usr/bin/env python3
"""Random baseline that samples 30 sensor indices."""

import argparse
import json
from pathlib import Path

import numpy as np

SENSOR_NUM = 30
DEFAULT_SEED = 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("submission.json"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--ref-points",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "references" / "car_surface_points.npy",
    )
    args = parser.parse_args()

    if not args.ref_points.exists():
        raise FileNotFoundError(
            f"Missing reference points: {args.ref_points}. "
            "Run references/extract_car_mesh.py first."
        )

    points = np.load(args.ref_points)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("Reference points must have shape (M, 3).")

    rng = np.random.default_rng(args.seed)
    indices = rng.choice(points.shape[0], size=SENSOR_NUM, replace=False)

    payload = {"indices": indices.tolist()}
    args.output.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {SENSOR_NUM} indices to {args.output}")


if __name__ == "__main__":
    main()
