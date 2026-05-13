#!/usr/bin/env python
"""Verification script for Task 4 (spectrum packing + guard)."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from optic.comm.metrics import theoryBER

from oracle import pack_spectrum_oracle


def load_solver(path: Path):
    spec = importlib.util.spec_from_file_location("candidate_solver", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.pack_spectrum


def build_scenario(seed=99):
    rng = np.random.default_rng(seed)
    # Bimodal demand mix:
    # many small demands + some large demands creates hard packing tradeoff.
    small = rng.integers(2, 4, size=16)
    large = rng.integers(8, 13, size=8)
    user_demand_slots = np.concatenate([small, large])
    rng.shuffle(user_demand_slots)
    user_base_snr_db = rng.uniform(16.0, 26.0, size=user_demand_slots.size)

    return {
        "user_demand_slots": user_demand_slots,
        "n_slots": 68,
        "guard_slots": 1,
        "seed": seed,
        "target_ber": 1e-3,
        "modulation_order": 16,
        "user_base_snr_db": user_base_snr_db,
    }


def check_valid_output(result, n_users):
    if not isinstance(result, dict) or "alloc" not in result:
        return False, "Output must be dict with key alloc"

    alloc = np.asarray(result["alloc"], dtype=int)
    if alloc.shape != (n_users, 2):
        return False, f"alloc shape must be {(n_users, 2)}"

    return True, "ok"


def evaluate(result, scenario):
    alloc = np.asarray(result["alloc"], dtype=int)
    demand = np.asarray(scenario["user_demand_slots"], dtype=int)
    base_snr = np.asarray(scenario["user_base_snr_db"], dtype=float)

    n_slots = int(scenario["n_slots"])
    guard = int(scenario["guard_slots"])
    target_ber = float(scenario["target_ber"])
    M = int(scenario["modulation_order"])

    # hard validity checks on geometry
    occ = np.zeros(n_slots, dtype=int)
    valid_geom = True

    for i in range(len(alloc)):
        s, w = int(alloc[i, 0]), int(alloc[i, 1])
        if s == -1 and w == 0:
            continue
        if w <= 0 or s < 0 or s + w > n_slots:
            valid_geom = False
            break
        if w != int(demand[i]):
            valid_geom = False
            break

        left = max(0, s - guard)
        right = min(n_slots, s + w + guard)
        if np.any(occ[left:right] > 0):
            valid_geom = False
            break

        occ[s : s + w] = 1

    accepted = alloc[:, 0] >= 0
    acceptance_ratio = float(np.mean(accepted))
    utilization = float(np.sum(occ) / n_slots)

    # Fragmentation: number of free blocks
    free_blocks = 0
    in_free = False
    for x in occ:
        if x == 0 and not in_free:
            free_blocks += 1
            in_free = True
        elif x == 1:
            in_free = False

    compactness = float(1.0 / (1.0 + free_blocks))

    ber = np.ones(len(alloc))
    snr_eff = np.full(len(alloc), -30.0)

    # BER proxy with adjacency interference from packed spectrum
    for i in range(len(alloc)):
        if not accepted[i]:
            continue

        s_i, w_i = int(alloc[i, 0]), int(alloc[i, 1])
        center_i = s_i + 0.5 * w_i

        interf = 0.0
        for j in range(len(alloc)):
            if i == j or not accepted[j]:
                continue
            s_j, w_j = int(alloc[j, 0]), int(alloc[j, 1])
            center_j = s_j + 0.5 * w_j
            gap = abs(center_i - center_j)
            interf += np.exp(-gap / 3.0)

        eff = base_snr[i] - 2.4 * interf
        snr_eff[i] = eff

        ebn0 = eff - 10 * np.log10(np.log2(M))
        ber[i] = float(theoryBER(M, ebn0, "qam"))

    if np.any(accepted):
        ber_pass = float(np.mean(ber[accepted] <= target_ber))
    else:
        ber_pass = 0.0

    # Put stronger emphasis on service acceptance (economic KPI) instead of pure occupancy.
    score = 0.80 * acceptance_ratio + 0.05 * utilization + 0.05 * compactness + 0.10 * ber_pass
    is_valid = bool(valid_geom and acceptance_ratio >= 0.25 and ber_pass >= 0.80)

    return {
        "is_valid": is_valid,
        "score": float(score),
        "valid_geometry": bool(valid_geom),
        "acceptance_ratio": acceptance_ratio,
        "utilization": utilization,
        "compactness": compactness,
        "ber_pass_ratio": ber_pass,
        "alloc": alloc.tolist(),
        "user_demand_slots": demand.tolist(),
        "effective_snr_db": snr_eff.tolist(),
        "ber": ber.tolist(),
    }


def save_plot(cand, oracle, scenario, out_png: Path):
    n_slots = scenario["n_slots"]
    ac = np.asarray(cand["alloc"], dtype=int)
    ao = np.asarray(oracle["alloc"], dtype=int)

    fig, axes = plt.subplots(2, 1, figsize=(12, 4.8), sharex=True)

    def draw(ax, alloc, title):
        ax.set_xlim(0, n_slots)
        ax.set_ylim(0, len(alloc) + 1)
        for i in range(len(alloc)):
            s, w = alloc[i]
            if s >= 0:
                ax.broken_barh([(s, w)], (i + 0.6, 0.8))
        ax.set_ylabel("User")
        ax.set_title(title)
        ax.grid(alpha=0.25)

    draw(axes[0], ac, "Candidate spectrum occupancy")
    draw(axes[1], ao, "Oracle spectrum occupancy")
    axes[1].set_xlabel("Spectrum slot index")

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--solver",
        default=str(Path(__file__).resolve().parents[1] / "baseline" / "init.py"),
    )
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parent / "outputs"),
    )
    parser.add_argument(
        "--oracle-mode",
        type=str,
        default="auto",
        choices=["auto", "hybrid", "exact_geometry", "heuristic"],
        help="Oracle backend mode",
    )
    parser.add_argument(
        "--oracle-time-limit",
        type=float,
        default=12.0,
        help="Oracle time budget hint (seconds)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenario = build_scenario(seed=99)

    fn = load_solver(Path(args.solver))
    result = fn(
        user_demand_slots=scenario["user_demand_slots"],
        n_slots=scenario["n_slots"],
        guard_slots=scenario["guard_slots"],
        seed=scenario["seed"],
    )

    ok, msg = check_valid_output(result, n_users=len(scenario["user_demand_slots"]))
    if not ok:
        summary = {"is_valid": False, "error": msg}
        print(json.dumps(summary, indent=2))
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return

    cand = evaluate(result, scenario)

    oracle_r = pack_spectrum_oracle(
        user_demand_slots=scenario["user_demand_slots"],
        n_slots=scenario["n_slots"],
        guard_slots=scenario["guard_slots"],
        seed=scenario["seed"],
        mode=args.oracle_mode,
        time_limit_s=args.oracle_time_limit,
    )
    oracle_e = evaluate(oracle_r, scenario)
    oracle_meta = oracle_r.get("__oracle_meta__", {})

    summary = {
        "candidate": cand,
        "oracle": oracle_e,
        "oracle_meta": oracle_meta,
        "score_gap_oracle_minus_candidate": float(oracle_e["score"] - cand["score"]),
    }

    save_plot(cand, oracle_e, scenario, out_dir / "task4_verification.png")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
