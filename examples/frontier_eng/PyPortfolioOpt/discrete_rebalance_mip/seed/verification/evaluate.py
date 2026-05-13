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


def _objective(instance: dict, lots: np.ndarray) -> float:
    prices = instance["prices"]
    lot_sizes = instance["lot_sizes"]
    current_lots = instance["current_lots"]
    target_weights = instance["target_weights"]
    portfolio_value = float(instance["portfolio_value"])
    fee_rate = float(instance["fee_rate"])

    unit = prices * lot_sizes
    target_dollar = target_weights * portfolio_value
    lots = np.asarray(lots, dtype=float)

    hold = unit * lots
    traded = unit * np.abs(lots - current_lots)
    traded_notional = traded.sum()

    return float(np.abs(hold - target_dollar).sum() + fee_rate * traded_notional)


def _feasibility_penalty(instance: dict, lots: np.ndarray) -> float:
    prices = instance["prices"]
    lot_sizes = instance["lot_sizes"]
    current_lots = instance["current_lots"]
    portfolio_value = float(instance["portfolio_value"])
    fee_rate = float(instance["fee_rate"])
    turnover_limit = float(instance["turnover_limit_value"])
    max_lots = instance["max_lots"]

    lots = np.asarray(lots, dtype=float)
    unit = prices * lot_sizes

    traded_notional = float((unit * np.abs(lots - current_lots)).sum())
    spend = float((unit * lots).sum() + fee_rate * traded_notional)

    p = 0.0
    p += np.maximum(0.0, -lots).sum() * 0.2
    p += np.maximum(0.0, lots - max_lots).sum() * 0.2

    integer_err = np.abs(lots - np.rint(lots)).sum()
    p += integer_err * 0.2

    p += max(0.0, traded_notional - turnover_limit) / max(1.0, turnover_limit)
    p += max(0.0, spend - portfolio_value) / max(1.0, portfolio_value)

    return float(min(1.0, p))


def _generate_instance(seed: int, n_assets: int = 15) -> dict:
    rng = np.random.default_rng(seed)

    prices = rng.uniform(15.0, 450.0, size=n_assets)
    lot_sizes = rng.choice([1, 5, 10, 20], size=n_assets, p=[0.55, 0.2, 0.2, 0.05])
    unit = prices * lot_sizes

    current_lots = rng.integers(0, 25, size=n_assets)
    current_value = float((unit * current_lots).sum())

    portfolio_value = float(current_value * rng.uniform(1.0, 1.15))
    target_weights = rng.dirichlet(np.ones(n_assets) * 1.5)

    max_lots = np.maximum(
        current_lots + 5,
        np.floor((portfolio_value / np.maximum(unit, 1e-12)) * rng.uniform(1.2, 1.8, size=n_assets)),
    ).astype(int)

    turnover_limit_value = float(portfolio_value * rng.uniform(0.2, 0.5))

    return {
        "prices": prices,
        "lot_sizes": lot_sizes.astype(int),
        "current_lots": current_lots.astype(int),
        "target_weights": target_weights,
        "portfolio_value": portfolio_value,
        "fee_rate": float(rng.uniform(0.001, 0.004)),
        "turnover_limit_value": turnover_limit_value,
        "max_lots": max_lots,
    }


def _score_instance(instance: dict, lots_cand: np.ndarray, lots_ref: np.ndarray) -> dict:
    current = np.asarray(instance["current_lots"], dtype=float)

    obj_ref = _objective(instance, lots_ref)
    obj_cand = _objective(instance, lots_cand)
    obj_anchor = _objective(instance, current)

    if obj_anchor < obj_ref + 1e-8:
        obj_anchor = obj_ref + 1e-3

    norm = (obj_anchor - obj_cand) / (obj_anchor - obj_ref + 1e-12)
    norm = float(np.clip(norm, 0.0, 1.0))

    penalty = _feasibility_penalty(instance, lots_cand)
    score = 100.0 * norm * (1.0 - penalty)

    return {
        "score": score,
        "obj_ref": obj_ref,
        "obj_cand": obj_cand,
        "obj_anchor": obj_anchor,
        "penalty": penalty,
    }


def _evaluate_candidate(candidate_path: Path) -> dict:
    baseline = _load_module(candidate_path, "candidate_solution")
    reference = _load_module(REFERENCE_PATH, "reference_solution")

    seeds = list(range(2226, 2236))
    rows = []
    lp_bounds = []

    for seed in seeds:
        inst = _generate_instance(seed)

        ref_out = reference.solve_instance(inst)
        lp_out = reference.solve_lp_relaxation(inst)
        base_out = baseline.solve_instance(inst)

        lots_ref = np.asarray(ref_out["lots"], dtype=float)
        lots_base = np.asarray(base_out["lots"], dtype=float)

        row = _score_instance(inst, lots_base, lots_ref)
        row["seed"] = seed
        rows.append(row)

        lp_bounds.append(float(lp_out["objective"]))

    return {
        "rows": rows,
        "lp_bounds": lp_bounds,
        "avg_score": float(np.mean([r["score"] for r in rows])),
        "avg_obj_ref": float(np.mean([r["obj_ref"] for r in rows])),
        "avg_obj_lp": float(np.mean(lp_bounds)),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate discrete_rebalance_mip candidate."
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
    lp_bounds = result["lp_bounds"]
    avg_score = float(result["avg_score"])
    avg_obj_ref = float(result["avg_obj_ref"])
    avg_obj_lp = float(result["avg_obj_lp"])

    print("=== Task 03 Evaluation ===")
    for r in rows:
        print(
            f"seed={r['seed']} score={r['score']:.2f} "
            f"obj(base)={r['obj_cand']:.2f} obj(ref)={r['obj_ref']:.2f} penalty={r['penalty']:.3f}"
        )

    print("---")
    print(f"baseline_average_score: {avg_score:.2f}/100")
    print("reference_integer_upper_bound_score: 100.00/100")
    print(
        f"average_lp_relaxation_objective_lower_bound: {avg_obj_lp:.2f} "
        f"(reference average objective: {avg_obj_ref:.2f})"
    )

    metrics = {
        "combined_score": avg_score,
        "valid": 1.0,
        "baseline_average_score_100": avg_score,
        "num_instances": float(len(rows)),
        "average_lp_relaxation_objective_lower_bound": avg_obj_lp,
        "reference_average_objective": avg_obj_ref,
    }
    artifacts = {
        "candidate_path": str(candidate_path),
        "rows": rows,
        "lp_bounds": lp_bounds,
    }

    if args.metrics_out:
        _write_json(args.metrics_out, metrics)
    if args.artifacts_out:
        _write_json(args.artifacts_out, artifacts)


if __name__ == "__main__":
    main()
