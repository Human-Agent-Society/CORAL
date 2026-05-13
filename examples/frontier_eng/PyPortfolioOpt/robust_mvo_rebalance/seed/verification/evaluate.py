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


def _make_psd_matrix(rng: np.random.Generator, n: int, f: int = 8) -> np.ndarray:
    B = rng.normal(0, 0.25, size=(n, f))
    D = rng.uniform(0.03, 0.12, size=n)
    cov = B @ B.T + np.diag(D)
    cov = 0.5 * (cov + cov.T)
    return cov


def _generate_instance(
    seed: int, n_assets: int = 50, n_sectors: int = 8, n_factors: int = 4
) -> dict:
    rng = np.random.default_rng(seed)

    mu = rng.normal(0.06, 0.08, size=n_assets)
    cov = _make_psd_matrix(rng, n_assets)

    lower = np.zeros(n_assets)
    upper = rng.uniform(0.03, 0.10, size=n_assets)

    # Construct feasible previous holdings under per-asset bounds.
    # We sample inside [0, upper] then scale to sum to one.
    for _ in range(100):
        raw = rng.uniform(0.0, 1.0, size=n_assets) * upper
        if raw.sum() > 1.0:
            w_prev = raw / raw.sum()
            break
    else:  # pragma: no cover
        w_prev = np.ones(n_assets) / n_assets

    sector_ids = np.array([i % n_sectors for i in range(n_assets)], dtype=int)

    sector_lower = {}
    sector_upper = {}
    for s in range(n_sectors):
        sec = float(w_prev[sector_ids == s].sum())
        width = float(rng.uniform(0.015, 0.04))
        sector_lower[s] = max(0.0, sec - width)
        sector_upper[s] = min(1.0, sec + width)

    factor_loadings = rng.normal(0.0, 1.0, size=(n_assets, n_factors))
    factor_prev = factor_loadings.T @ w_prev
    factor_width = rng.uniform(0.02, 0.06, size=n_factors)
    factor_lower = factor_prev - factor_width
    factor_upper = factor_prev + factor_width

    instance = {
        "mu": mu,
        "cov": cov,
        "w_prev": w_prev,
        "lower": lower,
        "upper": upper,
        "sector_ids": sector_ids,
        "sector_lower": sector_lower,
        "sector_upper": sector_upper,
        "factor_loadings": factor_loadings,
        "factor_lower": factor_lower,
        "factor_upper": factor_upper,
        "risk_aversion": float(rng.uniform(3.0, 7.0)),
        "transaction_penalty": float(rng.uniform(0.01, 0.04)),
        "turnover_limit": float(rng.uniform(0.15, 0.30)),
    }
    return instance


def _objective(instance: dict, w: np.ndarray) -> float:
    mu = instance["mu"]
    cov = instance["cov"]
    w_prev = instance["w_prev"]
    ra = instance["risk_aversion"]
    tc = instance["transaction_penalty"]
    return float(mu @ w - ra * (w @ cov @ w) - tc * np.abs(w - w_prev).sum())


def _feasibility_penalty(instance: dict, w: np.ndarray) -> float:
    lower = instance["lower"]
    upper = instance["upper"]
    sector_ids = instance["sector_ids"]
    sector_lower = instance["sector_lower"]
    sector_upper = instance["sector_upper"]
    factor_loadings = instance["factor_loadings"]
    factor_lower = instance["factor_lower"]
    factor_upper = instance["factor_upper"]
    w_prev = instance["w_prev"]
    turnover_limit = instance["turnover_limit"]

    p = 0.0

    p += max(0.0, np.abs(w.sum() - 1.0) - 1e-4) * 2.0
    p += np.maximum(0.0, lower - w).sum() * 15.0
    p += np.maximum(0.0, w - upper).sum() * 15.0

    for s, lo in sector_lower.items():
        sec = w[sector_ids == int(s)].sum()
        p += max(0.0, lo - sec) * 12.0

    for s, hi in sector_upper.items():
        sec = w[sector_ids == int(s)].sum()
        p += max(0.0, sec - hi) * 12.0

    turn = np.abs(w - w_prev).sum()
    p += max(0.0, turn - turnover_limit) * 10.0
    exposure = factor_loadings.T @ w
    p += np.maximum(0.0, factor_lower - exposure).sum() * 30.0
    p += np.maximum(0.0, exposure - factor_upper).sum() * 30.0

    return float(min(1.0, p))


def _score_instance(instance: dict, w_cand: np.ndarray, w_ref: np.ndarray) -> dict:
    n = w_ref.size
    w_uni = np.ones(n) / n

    f_ref = _objective(instance, w_ref)
    f_prev = _objective(instance, instance["w_prev"])
    f_uni = _objective(instance, w_uni)
    f_cand = _objective(instance, w_cand)

    f_anchor = min(f_uni, f_prev)
    if f_anchor >= f_ref - 1e-12:
        f_anchor = f_ref - 1e-3

    norm = (f_cand - f_anchor) / (f_ref - f_anchor + 1e-12)
    norm = float(np.clip(norm, 0.0, 1.0))

    penalty = _feasibility_penalty(instance, w_cand)
    score = 100.0 * norm * (1.0 - penalty)

    return {
        "score": score,
        "f_ref": f_ref,
        "f_cand": f_cand,
        "penalty": penalty,
    }


def _evaluate_candidate(candidate_path: Path) -> dict:
    baseline = _load_module(candidate_path, "candidate_solution")
    reference = _load_module(REFERENCE_PATH, "reference_solution")

    seeds = list(range(2026, 2036))
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
        description="Evaluate robust_mvo_rebalance candidate."
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

    print("=== Task 01 Evaluation ===")
    for r in rows:
        print(
            f"seed={r['seed']} score={r['score']:.2f} "
            f"obj(base)={r['f_cand']:.6f} obj(ref)={r['f_ref']:.6f} penalty={r['penalty']:.3f}"
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
