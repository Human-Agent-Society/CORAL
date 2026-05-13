#!/usr/bin/env python
"""Verification script for Task 1 (WDM channel + power allocation)."""

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

from oracle import allocate_wdm_oracle


def load_solver(solver_path: Path):
    spec = importlib.util.spec_from_file_location("candidate_solver", solver_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.allocate_wdm


def build_scenario(seed=42):
    rng = np.random.default_rng(seed)
    n_users = 14
    n_channels = 20
    fc = 193.1e12
    spacing = 37.5e9
    channel_centers_hz = fc + (np.arange(n_channels) - (n_channels - 1) / 2.0) * spacing

    user_demands_gbps = rng.uniform(180.0, 320.0, size=n_users)

    return {
        "user_demands_gbps": user_demands_gbps,
        "channel_centers_hz": channel_centers_hz,
        "total_power_dbm": 16.0,
        "pmin_dbm": -10.0,
        "pmax_dbm": 7.0,
        "target_ber": 1e-3,
        "seed": seed,
    }


def check_valid_output(result, n_users, n_channels, pmin_dbm, pmax_dbm, total_power_dbm):
    if not isinstance(result, dict):
        return False, "Output must be a dict"

    if "assignment" not in result or "power_dbm" not in result:
        return False, "Missing keys: assignment/power_dbm"

    assignment = np.asarray(result["assignment"])
    power_dbm = np.asarray(result["power_dbm"], dtype=float)

    if assignment.shape != (n_users,):
        return False, f"assignment shape must be {(n_users,)}, got {assignment.shape}"
    if power_dbm.shape != (n_channels,):
        return False, f"power_dbm shape must be {(n_channels,)}, got {power_dbm.shape}"

    if not np.issubdtype(assignment.dtype, np.integer):
        return False, "assignment must be integer array"

    if np.any((assignment < -1) | (assignment >= n_channels)):
        return False, "assignment contains out-of-range channel indices"

    used = assignment[assignment >= 0]
    if used.size != np.unique(used).size:
        return False, "Each channel can be assigned to at most one user"

    if np.any(power_dbm < pmin_dbm - 1e-9) or np.any(power_dbm > pmax_dbm + 1e-9):
        return False, "power_dbm violates per-channel bounds"

    total_lin = np.sum(10 ** (power_dbm / 10.0))
    if total_lin > 10 ** (total_power_dbm / 10.0) * 1.001:
        return False, "power_dbm violates total power budget"

    return True, "ok"


def evaluate(result, scenario):
    demands = np.asarray(scenario["user_demands_gbps"], dtype=float)
    assignment = np.asarray(result["assignment"], dtype=int)
    power_dbm = np.asarray(result["power_dbm"], dtype=float)

    n_users = len(demands)
    n_channels = len(power_dbm)

    M = 4
    capacity_scale = 28.0
    noise_floor_lin = 2e-3
    interference_scale = 0.12
    interference_decay = 0.9

    user_snr_db = np.full(n_users, -30.0)
    user_ber = np.ones(n_users)
    user_capacity = np.zeros(n_users)

    for u in range(n_users):
        ch = assignment[u]
        if ch < 0:
            continue

        sig = 10 ** (power_dbm[ch] / 10.0)
        interf = 0.0
        for v in range(n_users):
            ch2 = assignment[v]
            if v == u or ch2 < 0:
                continue
            interf += (10 ** (power_dbm[ch2] / 10.0)) * np.exp(-abs(ch - ch2) / interference_decay)

        snr_lin = sig / (noise_floor_lin + interference_scale * interf)
        snr_db = 10.0 * np.log10(max(snr_lin, 1e-12))
        user_snr_db[u] = snr_db

        ebn0_db = snr_db - 10.0 * np.log10(np.log2(M))
        ber = float(theoryBER(M, ebn0_db, "qam"))
        user_ber[u] = ber

        # Abstract per-user link capacity proxy (Gbps)
        user_capacity[u] = capacity_scale * np.log2(1.0 + max(snr_lin, 1e-12))

    sat = np.minimum(user_capacity / np.maximum(demands, 1e-9), 1.0)
    demand_satisfaction = float(np.mean(sat))

    assigned_mask = assignment >= 0
    if np.any(assigned_mask):
        ber_pass_ratio = float(np.mean(user_ber[assigned_mask] <= scenario["target_ber"]))
        avg_snr_db = float(np.mean(user_snr_db[assigned_mask]))
    else:
        ber_pass_ratio = 0.0
        avg_snr_db = -30.0

    spectral_util = float(np.sum(assigned_mask) / n_channels)
    total_power_lin = float(np.sum(10 ** (power_dbm / 10.0)))
    budget_lin = float(10 ** (scenario["total_power_dbm"] / 10.0))
    power_penalty = max(0.0, (total_power_lin - budget_lin) / max(budget_lin, 1e-12))

    snr_term = np.clip((avg_snr_db - 5.0) / 20.0, 0.0, 1.0)
    score = 0.35 * demand_satisfaction + 0.40 * ber_pass_ratio + 0.05 * spectral_util + 0.20 * snr_term - 0.15 * power_penalty

    is_valid = demand_satisfaction >= 0.30 and ber_pass_ratio >= 0.20 and spectral_util >= 0.55

    return {
        "is_valid": bool(is_valid),
        "score": float(score),
        "demand_satisfaction": demand_satisfaction,
        "ber_pass_ratio": ber_pass_ratio,
        "spectral_utilization": spectral_util,
        "avg_snr_db": avg_snr_db,
        "avg_ber_assigned": float(np.mean(user_ber[assigned_mask])) if np.any(assigned_mask) else 1.0,
        "assignment": assignment.tolist(),
        "power_dbm": power_dbm.tolist(),
        "user_demands_gbps": demands.tolist(),
        "user_capacity_gbps": user_capacity.tolist(),
        "user_ber": user_ber.tolist(),
    }


def save_plot(eval_data, oracle_data, output_png: Path):
    demands = np.asarray(eval_data["user_demands_gbps"])
    cap_a = np.asarray(eval_data["user_capacity_gbps"])
    cap_o = np.asarray(oracle_data["user_capacity_gbps"])
    p_a = np.asarray(eval_data["power_dbm"])
    p_o = np.asarray(oracle_data["power_dbm"])

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))

    x = np.arange(len(demands))
    axes[0].bar(x - 0.25, demands, width=0.25, label="Demand")
    axes[0].bar(x, cap_a, width=0.25, label="Candidate")
    axes[0].bar(x + 0.25, cap_o, width=0.25, label="Oracle")
    axes[0].set_title("Per-user demand vs achieved capacity")
    axes[0].set_xlabel("User index")
    axes[0].set_ylabel("Gbps")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)

    cx = np.arange(len(p_a))
    axes[1].plot(cx, p_a, "o-", label="Candidate")
    axes[1].plot(cx, p_o, "s--", label="Oracle")
    axes[1].set_title("Per-channel launch power")
    axes[1].set_xlabel("Channel index")
    axes[1].set_ylabel("dBm")
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--solver",
        type=str,
        default=str(Path(__file__).resolve().parents[1] / "baseline" / "init.py"),
        help="Path to candidate init.py",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=str(Path(__file__).resolve().parent / "outputs"),
    )
    parser.add_argument(
        "--oracle-mode",
        type=str,
        default="auto",
        choices=["auto", "hybrid_scipy", "heuristic"],
        help="Oracle backend mode",
    )
    parser.add_argument(
        "--oracle-time-limit",
        type=float,
        default=10.0,
        help="Oracle time budget hint (seconds)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenario = build_scenario(seed=42)

    candidate_fn = load_solver(Path(args.solver))
    candidate_result = candidate_fn(**scenario)

    ok, msg = check_valid_output(
        candidate_result,
        n_users=len(scenario["user_demands_gbps"]),
        n_channels=len(scenario["channel_centers_hz"]),
        pmin_dbm=scenario["pmin_dbm"],
        pmax_dbm=scenario["pmax_dbm"],
        total_power_dbm=scenario["total_power_dbm"],
    )

    if not ok:
        summary = {"is_valid": False, "error": msg}
        print(json.dumps(summary, indent=2))
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return

    cand_eval = evaluate(candidate_result, scenario)

    oracle_result = allocate_wdm_oracle(
        **scenario,
        mode=args.oracle_mode,
        time_limit_s=args.oracle_time_limit,
    )
    oracle_eval = evaluate(oracle_result, scenario)
    oracle_meta = oracle_result.get("__oracle_meta__", {})

    summary = {
        "candidate": cand_eval,
        "oracle": oracle_eval,
        "oracle_meta": oracle_meta,
        "score_gap_oracle_minus_candidate": float(oracle_eval["score"] - cand_eval["score"]),
    }

    save_plot(cand_eval, oracle_eval, out_dir / "task1_verification.png")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
