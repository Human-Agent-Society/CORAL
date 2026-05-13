import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE_PATH = ROOT / "baseline" / "init.py"
REFERENCE_PATH = ROOT / "verification" / "reference.py"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _generate_instance(seed: int, n_assets: int = 26, n_sectors: int = 5, T: int = 260) -> dict:
    rng = np.random.default_rng(seed)

    # Heavy-tailed factor model scenarios
    f = 4
    factor = rng.standard_t(df=4, size=(T, f)) * 0.01
    loadings = rng.normal(0.0, 0.7, size=(n_assets, f))
    idio = rng.standard_t(df=5, size=(T, n_assets)) * 0.012
    drift = rng.normal(0.0004, 0.00025, size=n_assets)

    R = factor @ loadings.T + idio + drift
    mu = R.mean(axis=0)

    lower = np.zeros(n_assets)
    upper = rng.uniform(0.07, 0.18, size=n_assets)

    w_prev = rng.dirichlet(np.ones(n_assets) * 2.0)

    sector_ids = np.array([i % n_sectors for i in range(n_assets)], dtype=int)
    sector_lower = {}
    sector_upper = {}

    base = 1.0 / n_sectors
    for s in range(n_sectors):
        lo = max(0.0, base * 0.2 + rng.uniform(-0.015, 0.015))
        hi = min(1.0, base * 2.3 + rng.uniform(-0.04, 0.04))
        sector_lower[s] = float(lo)
        sector_upper[s] = float(max(hi, lo + 0.05))

    sector_upper[int(rng.integers(0, n_sectors))] = min(
        1.0, sector_upper[int(rng.integers(0, n_sectors))] + 0.2
    )

    target_return = float(mu.mean() + 0.05 * mu.std())

    return {
        "scenario_returns": R,
        "mu": mu,
        "w_prev": w_prev,
        "lower": lower,
        "upper": upper,
        "sector_ids": sector_ids,
        "sector_lower": sector_lower,
        "sector_upper": sector_upper,
        "beta": float(rng.uniform(0.9, 0.98)),
        "target_return": target_return,
        "turnover_limit": float(rng.uniform(0.25, 0.55)),
    }


def _cvar(R: np.ndarray, w: np.ndarray, beta: float) -> float:
    losses = -(R @ w)
    q = np.quantile(losses, beta)
    tail = losses[losses >= q]
    if tail.size == 0:
        return float(q)
    return float(tail.mean())


def _feasibility_penalty(instance: dict, w: np.ndarray) -> float:
    mu = instance["mu"]
    lower = instance["lower"]
    upper = instance["upper"]
    sector_ids = instance["sector_ids"]
    sector_lower = instance["sector_lower"]
    sector_upper = instance["sector_upper"]
    target_return = instance["target_return"]
    w_prev = instance["w_prev"]
    turnover_limit = instance["turnover_limit"]

    p = 0.0
    p += max(0.0, abs(w.sum() - 1.0) - 1e-4) * 2.0
    p += np.maximum(0.0, lower - w).sum() * 15.0
    p += np.maximum(0.0, w - upper).sum() * 15.0

    ret = float(mu @ w)
    p += max(0.0, target_return - ret) * 600.0

    for s, lo in sector_lower.items():
        sec = w[sector_ids == int(s)].sum()
        p += max(0.0, lo - sec) * 10.0

    for s, hi in sector_upper.items():
        sec = w[sector_ids == int(s)].sum()
        p += max(0.0, sec - hi) * 10.0

    turn = np.abs(w - w_prev).sum()
    p += max(0.0, turn - turnover_limit) * 10.0

    return float(min(1.0, p))


def _score_instance(instance: dict, w_cand: np.ndarray, w_ref: np.ndarray) -> dict:
    R = instance["scenario_returns"]
    beta = instance["beta"]
    w_prev = instance["w_prev"]
    n = w_ref.size
    w_uniform = np.ones(n) / n

    c_ref = _cvar(R, w_ref, beta)
    c_cand = _cvar(R, w_cand, beta)
    c_anchor = max(_cvar(R, w_uniform, beta), _cvar(R, w_prev, beta))

    if c_anchor < c_ref + 1e-6:
        c_anchor = c_ref + 1e-3

    norm = (c_anchor - c_cand) / (c_anchor - c_ref + 1e-12)
    norm = float(np.clip(norm, 0.0, 1.0))

    penalty = _feasibility_penalty(instance, w_cand)
    score = 100.0 * norm * (1.0 - penalty)

    return {
        "score": score,
        "c_ref": c_ref,
        "c_cand": c_cand,
        "penalty": penalty,
    }


def _evaluate_candidate(candidate_path: Path) -> dict:
    baseline = _load_module(candidate_path, "candidate_solution")
    reference = _load_module(REFERENCE_PATH, "reference_solution")

    seeds = list(range(2126, 2136))
    rows = []

    for seed in seeds:
        inst = _generate_instance(seed)
        w_ref = np.asarray(reference.solve_instance(inst)["weights"], dtype=float)
        w_base = np.asarray(baseline.solve_instance(inst)["weights"], dtype=float)

        row = _score_instance(inst, w_base, w_ref)
        row["seed"] = seed
        rows.append(row)

    return {
        "rows": rows,
        "avg_score": float(np.mean([r["score"] for r in rows])),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate cvar_stress_control candidate."
    )
    parser.add_argument(
        "candidate",
        nargs="?",
        default=str(DEFAULT_CANDIDATE_PATH),
        help="Path to candidate Python file.",
    )
    parser.add_argument(
        "--metrics-out",
        type=str,
        default=None,
        help="Optional JSON path for frontier_eval metrics output.",
    )
    parser.add_argument(
        "--artifacts-out",
        type=str,
        default=None,
        help="Optional JSON path for additional artifacts output.",
    )
    return parser.parse_args()


def _write_json(path: str, payload: dict) -> None:
    out_path = Path(path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = _parse_args()
    candidate_path = Path(args.candidate).expanduser().resolve()
    result = _evaluate_candidate(candidate_path)
    rows = result["rows"]
    avg_score = float(result["avg_score"])

    print("=== Task 02 Evaluation ===")
    for r in rows:
        print(
            f"seed={r['seed']} score={r['score']:.2f} "
            f"cvar(base)={r['c_cand']:.6f} cvar(ref)={r['c_ref']:.6f} penalty={r['penalty']:.3f}"
        )

    print("---")
    print(f"baseline_average_score: {avg_score:.2f}/100")
    print("reference_theoretical_upper_bound: 100.00/100")

    metrics = {
        "combined_score": avg_score,
        "valid": 1.0,
        "baseline_average_score_100": avg_score,
        "num_instances": float(len(rows)),
    }
    artifacts = {
        "candidate_path": str(candidate_path),
        "rows": rows,
    }

    if args.metrics_out:
        _write_json(args.metrics_out, metrics)
    if args.artifacts_out:
        _write_json(args.artifacts_out, artifacts)


if __name__ == "__main__":
    main()
