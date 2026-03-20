#!/usr/bin/env python3
"""
VDB Design Evaluator

Evaluates custom ANN index implementations by benchmarking them on SIFT1M dataset.
The solution.py should export a class with the following interface:
  - __init__(dim: int, **kwargs)
  - add(xb: np.ndarray) -> None
  - search(xq: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]
"""

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from types import ModuleType

import numpy as np

try:
    from faiss.contrib.datasets_fb import DatasetSIFT1M
except ImportError:
    from faiss.contrib.datasets import DatasetSIFT1M


CONFIG_PATH = Path(__file__).with_name("score_config.json")


def load_score_config() -> dict:
    """Load scoring configuration from JSON, returning defaults if missing."""
    default = {
        "baseline": {
            "name": "baseline",
            "recall_at_1": 0.99,
            "avg_query_time_ms": 5.0,
        },
        "scoring": {
            "scale": 60.0,
            "recall_weight": 2.0,
            "latency_weight": 1.0,
            "max_score": 100.0,
            "min_score": 0.0,
            "epsilon": 1e-9,
        },
        "pareto": {
            "recall_margin": 0.0,
            "latency_margin_ms": 0.0,
        },
    }
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            # Merge loaded values onto defaults without mutating default structure
            def merge(base: dict, new: dict) -> dict:
                result = dict(base)
                for key, value in new.items():
                    if isinstance(value, dict) and isinstance(result.get(key), dict):
                        result[key] = merge(result[key], value)
                    else:
                        result[key] = value
                return result

            return merge(default, loaded)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[evaluator] WARNING: Failed to load score_config.json ({exc}); using defaults", file=sys.stderr)
    return default


SCORE_CONFIG = load_score_config()


def load_solution_module(solution_path: Path) -> ModuleType:
    """Load the solution module from the given path."""
    if not solution_path.exists():
        raise FileNotFoundError(f"solution.py not found at {solution_path}")
    spec = importlib.util.spec_from_file_location("submitted_solution", solution_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load spec for {solution_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # Register before exec for self-referential imports
    spec.loader.exec_module(module)
    return module


def find_solution_class(module: ModuleType):
    """
    Find the custom ANN index class in the solution module.
    Looks for a class with add() and search() methods.
    """
    for name in dir(module):
        if name.startswith('_'):
            continue
        obj = getattr(module, name)
        if not isinstance(obj, type):
            continue
        if hasattr(obj, 'add') and hasattr(obj, 'search'):
            return obj
    raise AttributeError(
        "solution.py must define a class with add(xb) and search(xq, k) methods"
    )


def evaluate_index(index, xq: np.ndarray, gt: np.ndarray, k: int) -> dict:
    """
    Evaluate index performance on query set.
    Returns metrics: recall@1, total_time_ms, avg_query_time_ms
    """
    nq = xq.shape[0]
    
    # Batched search timing
    t0 = time.time()
    D, I = index.search(xq, k)
    t1 = time.time()
    
    # Calculate metrics
    recall_at_1 = (I[:, :1] == gt[:, :1]).sum() / float(nq)
    total_ms = (t1 - t0) * 1000.0
    per_query_ms = total_ms / float(nq)
    
    # Single-request latency sample (measure first 100 queries)
    num_samples = min(100, nq)
    single_total = 0.0
    for i in range(num_samples):
        q = xq[i:i+1]
        s0 = time.time()
        index.search(q, k)
        s1 = time.time()
        single_total += (s1 - s0)
    single_avg_ms = (single_total / num_samples) * 1000.0
    
    return {
        'recall_at_1': float(recall_at_1),
        'total_time_ms': float(total_ms),
        'avg_query_time_ms': float(per_query_ms),
        'single_query_avg_ms': float(single_avg_ms),
        'num_queries': int(nq),
    }


def _safe_ratio(numerator: float, denominator: float, epsilon: float) -> float:
    """Return a stable ratio, clamping to epsilon on the denominator."""
    denom = max(denominator, epsilon)
    return max(numerator / denom, epsilon)


def compute_score(metrics: dict, config: dict = SCORE_CONFIG) -> float:
    """
    Compute score based on scoring mode in config.
    
    Modes:
    - "latency_gated_recall": If latency meets threshold, score based on recall.
                              If recall > baseline_recall: 100 points
                              Otherwise: (recall - lower_threshold) / (baseline_recall - lower_threshold) * 100
    - "balanced" (default): Balances recall and latency improvements
    """
    scoring_cfg = config["scoring"]
    baseline_cfg = config["baseline"]
    max_score = float(scoring_cfg.get("max_score", 100.0))
    min_score = float(scoring_cfg.get("min_score", 0.0))
    
    # Check if using new latency_gated_recall mode
    mode = scoring_cfg.get("mode", "balanced")
    
    if mode == "latency_gated_recall":
        # New scoring: latency is a gate, recall determines score
        latency_threshold = float(scoring_cfg.get("latency_threshold_ms", 3.85))
        recall_lower_threshold = float(scoring_cfg.get("recall_lower_threshold", 0.9914))
        
        actual_latency = float(metrics["avg_query_time_ms"])
        actual_recall = float(metrics["recall_at_1"])
        baseline_recall = float(baseline_cfg["recall_at_1"])
        
        # Check if latency meets threshold
        if actual_latency > latency_threshold:
            # Latency gate not met - score 0
            return min_score
        
        # Latency gate met - score based on recall
        if actual_recall > baseline_recall:
            # Exceeds baseline recall - perfect score
            return max_score
        else:
            # Score proportional to recall vs lower threshold
            recall_range = baseline_recall - recall_lower_threshold
            if recall_range <= 0:
                # Edge case: lower threshold >= baseline
                return max_score if actual_recall >= recall_lower_threshold else min_score
            
            recall_proportion = (actual_recall - recall_lower_threshold) / recall_range
            # Clamp to [0, 1] and scale to [min_score, max_score]
            recall_proportion = max(0.0, min(1.0, recall_proportion))
            score = min_score + (max_score - min_score) * recall_proportion
            return float(score)
    else:
        # Original balanced mode
        recall_ratio = _safe_ratio(metrics["recall_at_1"], baseline_cfg["recall_at_1"], scoring_cfg.get("epsilon", 1e-9))
        latency_ratio = _safe_ratio(baseline_cfg["avg_query_time_ms"], metrics["avg_query_time_ms"], scoring_cfg.get("epsilon", 1e-9))
        
        recall_weight = float(scoring_cfg.get("recall_weight", 2.0))
        latency_weight = float(scoring_cfg.get("latency_weight", 1.0))
        scale = float(scoring_cfg.get("scale", 60.0))
        threshold = max(0.0, float(scoring_cfg.get("improvement_threshold", 0.0)))
        
        raw = (recall_ratio ** recall_weight) * (latency_ratio ** latency_weight)
        
        if raw <= 1.0:
            score = scale * raw
        else:
            improvement = raw - 1.0
            if improvement <= threshold:
                score = scale
            else:
                target_cfg = config.get("targets", {})
                target_recall = max(
                    float(target_cfg.get("aspirational_recall", baseline_cfg["recall_at_1"])),
                    float(baseline_cfg["recall_at_1"]),
                )
                target_latency = min(
                    float(target_cfg.get("aspirational_avg_query_time_ms", baseline_cfg["avg_query_time_ms"])),
                    float(baseline_cfg["avg_query_time_ms"]),
                )
                target_raw = (
                    _safe_ratio(target_recall, baseline_cfg["recall_at_1"], scoring_cfg.get("epsilon", 1e-9)) ** recall_weight
                ) * (
                    _safe_ratio(baseline_cfg["avg_query_time_ms"], target_latency, scoring_cfg.get("epsilon", 1e-9)) ** latency_weight
                )
                
                effective_raw = 1.0 + (improvement - threshold)
                target_effective = max(1.0 + (target_raw - 1.0 - threshold), 1.0 + scoring_cfg.get("epsilon", 1e-9))
                effective_clamped = min(effective_raw, target_effective)
                growth = max(
                    0.0,
                    min(1.0, (effective_clamped - 1.0) / max(target_effective - 1.0, scoring_cfg.get("epsilon", 1e-9))),
                )
                score = scale + (max_score - scale) * growth
        
        return float(min(max_score, max(min_score, score)))


def assess_pareto(metrics: dict, config: dict = SCORE_CONFIG) -> dict:
    """
    Compare solution metrics against the configured baseline to determine Pareto status.
    
    Returns:
        Dict containing:
          - reference: name of baseline
          - pareto_frontier: bool (True if not dominated by reference)
          - dominates_reference: bool
          - dominated_by_reference: bool
          - status: human-readable label
          - deltas: recall/time deltas vs reference
    """
    baseline = config["baseline"]
    margins = config.get("pareto", {})
    recall_margin = float(margins.get("recall_margin", 0.0))
    latency_margin = float(margins.get("latency_margin_ms", 0.0))
    
    recall = float(metrics["recall_at_1"])
    latency = float(metrics["avg_query_time_ms"])
    base_recall = float(baseline["recall_at_1"])
    base_latency = float(baseline["avg_query_time_ms"])
    
    recall_delta = recall - base_recall
    latency_delta = latency - base_latency
    
    dominates = (
        recall >= base_recall - recall_margin
        and latency <= base_latency + latency_margin
        and (recall > base_recall + recall_margin or latency < base_latency - latency_margin)
    )
    dominated = (
        recall <= base_recall + recall_margin
        and latency >= base_latency - latency_margin
        and (recall < base_recall - recall_margin or latency > base_latency + latency_margin)
    )
    
    if dominates:
        status = "dominates_reference"
    elif dominated:
        status = "dominated_by_reference"
    else:
        status = "tradeoff"
    
    return {
        "reference": baseline.get("name", "baseline"),
        "pareto_frontier": not dominated,
        "dominates_reference": dominates,
        "dominated_by_reference": dominated,
        "status": status,
        "deltas": {
            "recall_at_1": recall_delta,
            "avg_query_time_ms": latency_delta,
        },
        "reference_metrics": {
            "recall_at_1": base_recall,
            "avg_query_time_ms": base_latency,
        },
    }


def evaluate(solution_path: Path, k: int = 1) -> dict:
    """
    Main evaluation function.

    Args:
        solution_path: Path to solution.py
        k: Number of nearest neighbors to retrieve (default: 1)

    Returns:
        Dictionary with evaluation results and score
    """
    print("[evaluator] Loading solution module...", file=sys.stderr)
    module = load_solution_module(solution_path)
    
    print("[evaluator] Finding solution class...", file=sys.stderr)
    IndexClass = find_solution_class(module)
    print(f"[evaluator] Using class: {IndexClass.__name__}", file=sys.stderr)
    
    print("[evaluator] Loading SIFT1M dataset...", file=sys.stderr)
    ds = DatasetSIFT1M()
    xb = ds.get_database()  # 1M base vectors
    xq = ds.get_queries()    # 10k query vectors
    gt = ds.get_groundtruth()  # Ground truth
    xt = ds.get_train()      # Training vectors (optional)
    
    d = xb.shape[1]  # dimension (128 for SIFT1M)
    print(f"[evaluator] Dataset loaded: {xb.shape[0]} base vectors, dim={d}", file=sys.stderr)
    
    print("[evaluator] Building index...", file=sys.stderr)
    index = IndexClass(d)
    
    print("[evaluator] Adding vectors to index...", file=sys.stderr)
    t0 = time.time()
    index.add(xb)
    build_time = time.time() - t0
    print(f"[evaluator] Index built in {build_time:.2f}s", file=sys.stderr)
    
    print("[evaluator] Running evaluation...", file=sys.stderr)
    metrics = evaluate_index(index, xq, gt, k)
    
    print(f"[evaluator] Recall@1: {metrics['recall_at_1']:.4f}", file=sys.stderr)
    print(f"[evaluator] Avg query time: {metrics['avg_query_time_ms']:.3f}ms", file=sys.stderr)
    
    # Compute final score
    score = compute_score(metrics)
    # Compute unbounded score by temporarily removing score limits
    config_unbounded = dict(SCORE_CONFIG)
    config_unbounded["scoring"] = dict(config_unbounded["scoring"])
    config_unbounded["scoring"]["max_score"] = float('inf')
    config_unbounded["scoring"]["min_score"] = float('-inf')
    score_unbounded = compute_score(metrics, config_unbounded)

    pareto = assess_pareto(metrics)
    print(f"[evaluator] Final score: {score:.2f}", file=sys.stderr)
    print(f"[evaluator] Unbounded score: {score_unbounded:.2f}", file=sys.stderr)
    print(f"[evaluator] Pareto status vs {pareto['reference']}: {pareto['status']}", file=sys.stderr)

    return {
        'score': score,
        'score_unbounded': score_unbounded,
        'metrics': metrics,
        'build_time_seconds': build_time,
        'index_class': IndexClass.__name__,
        'k': k,
        'pareto': pareto,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate VDB design solution")
    parser.add_argument(
        "--solution",
        default="/work/execution_env/solution_env/solution.py",
        help="Path to solution.py",
    )
    parser.add_argument(
        "--out",
        default="results.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=1,
        help="Number of nearest neighbors to retrieve",
    )
    args = parser.parse_args()
    
    solution_path = Path(args.solution).resolve()
    output_path = Path(args.out)
    
    try:
        results = evaluate(solution_path, k=args.k)
        
        # Write results to file
        with output_path.open('w') as f:
            json.dump(results, f, indent=2)
        
        print(f"[evaluator] Results written to {output_path}", file=sys.stderr)
        
        # Print score to stdout for evaluate.sh to capture
        # Format: "score score_unbounded" (space-separated)
        print(f"{results['score']} {results.get('score_unbounded', results['score'])}")

    except Exception as e:
        error_payload = {
            'score': 0.0,
            'error': str(e),
            'error_type': type(e).__name__,
        }
        with output_path.open('w') as f:
            json.dump(error_payload, f, indent=2)
        print(f"[evaluator] ERROR: {e}", file=sys.stderr)
        print("0")
        sys.exit(1)


if __name__ == "__main__":
    main()
