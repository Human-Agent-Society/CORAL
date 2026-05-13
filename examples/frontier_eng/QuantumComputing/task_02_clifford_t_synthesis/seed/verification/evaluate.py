from __future__ import annotations

import argparse
from pathlib import Path
from statistics import mean
from typing import Any

from qiskit import transpile

TASK_DIR = Path(__file__).resolve().parent.parent

from utils import (
    compute_metrics,
    create_run_dir,
    dump_json,
    load_cases,
    load_solver,
    save_circuit_artifacts,
    timed_call,
)
from mqt.bench import BenchmarkLevel, get_benchmark
from mqt.bench.targets.gatesets import get_target_for_gateset


def synthesis_cost(depth: int, two_qubit_count: int, t_count: int, tdg_count: int) -> float:
    t_total = t_count + tdg_count
    return t_total + 0.2 * two_qubit_count + 0.05 * depth


def normalize_score_0_to_3(cost: float, opt0_cost: float, opt3_cost: float) -> float:
    if abs(opt0_cost - opt3_cost) < 1e-12:
        return 0.0
    return 3.0 * (opt0_cost - cost) / (opt0_cost - opt3_cost)


def evaluate_case(case: dict[str, Any], solver: Any, artifact_root: Path) -> dict[str, Any]:
    benchmark = case["benchmark"]
    num_qubits = case["num_qubits"]
    target = get_target_for_gateset(case["target_gateset"], num_qubits)
    case_dir = artifact_root / case["case_id"]
    case_dir.mkdir(parents=True, exist_ok=True)

    input_qc = get_benchmark(
        benchmark=benchmark,
        level=BenchmarkLevel.ALG,
        circuit_size=num_qubits,
    )
    save_circuit_artifacts(input_qc, case_dir, "input")

    candidate_raw, solve_time = timed_call(solver, input_qc.copy(), target, case)
    save_circuit_artifacts(candidate_raw, case_dir, "candidate_raw")

    candidate_canon, canon_time = timed_call(
        transpile,
        candidate_raw,
        target=target,
        optimization_level=0,
        seed_transpiler=10,
    )
    save_circuit_artifacts(candidate_canon, case_dir, "candidate_canonical", save_image=False)

    candidate_metrics = compute_metrics(candidate_canon)
    candidate_cost = synthesis_cost(
        candidate_metrics.depth,
        candidate_metrics.two_qubit_count,
        candidate_metrics.t_count,
        candidate_metrics.tdg_count,
    )

    bench_rows: dict[str, Any] = {}
    for opt_level in (0, 1, 2, 3):
        bench_qc, bench_time = timed_call(
            get_benchmark,
            benchmark,
            BenchmarkLevel.NATIVEGATES,
            num_qubits,
            target=target,
            opt_level=opt_level,
        )
        save_circuit_artifacts(bench_qc, case_dir, f"reference_opt_{opt_level}", save_image=False)
        metrics = compute_metrics(bench_qc)
        cost = synthesis_cost(metrics.depth, metrics.two_qubit_count, metrics.t_count, metrics.tdg_count)
        bench_rows[f"opt_{opt_level}"] = {
            "runtime_s": bench_time,
            "cost": cost,
            "metrics": metrics.to_dict(),
        }

    opt0_cost = bench_rows["opt_0"]["cost"]
    opt3_cost = bench_rows["opt_3"]["cost"]

    for opt_level in (0, 1, 2, 3):
        key = f"opt_{opt_level}"
        bench_rows[key]["score_0_to_3"] = normalize_score_0_to_3(bench_rows[key]["cost"], opt0_cost, opt3_cost)
    bench_rows["opt_0"]["score_0_to_3"] = 0.0
    bench_rows["opt_3"]["score_0_to_3"] = 3.0

    candidate_score = normalize_score_0_to_3(candidate_cost, opt0_cost, opt3_cost)
    improvement_vs_opt0 = (opt0_cost - candidate_cost) / opt0_cost if opt0_cost else 0.0
    gap_vs_opt3 = (candidate_cost - opt3_cost) / opt3_cost if opt3_cost else 0.0

    return {
        "case_id": case["case_id"],
        "candidate": {
            "solve_runtime_s": solve_time,
            "canonicalize_runtime_s": canon_time,
            "total_runtime_s": solve_time + canon_time,
            "cost": candidate_cost,
            "score_0_to_3": candidate_score,
            "metrics": candidate_metrics.to_dict(),
        },
        "references": bench_rows,
        "improvement_vs_opt0": improvement_vs_opt0,
        "gap_vs_opt3": gap_vs_opt3,
        "artifacts_dir": str(case_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Task 02 candidate solver.")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional path to store a JSON report.")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Optional artifact output directory. Default: task_02_clifford_t_synthesis/runs/eval_<timestamp>",
    )
    args = parser.parse_args()

    artifact_root = args.artifact_dir if args.artifact_dir is not None else create_run_dir(TASK_DIR, prefix="eval")
    artifact_root.mkdir(parents=True, exist_ok=True)

    solver = load_solver(TASK_DIR)
    cases = load_cases(TASK_DIR)
    results = [evaluate_case(case, solver, artifact_root) for case in cases]

    avg_candidate_cost = mean(r["candidate"]["cost"] for r in results)
    avg_candidate_score = mean(r["candidate"]["score_0_to_3"] for r in results)
    avg_opt0_cost = mean(r["references"]["opt_0"]["cost"] for r in results)
    avg_opt3_cost = mean(r["references"]["opt_3"]["cost"] for r in results)

    print("Task 02 Evaluation Summary")
    print(f"cases={len(results)}")
    print(f"avg_candidate_cost={avg_candidate_cost:.4f}")
    print(f"avg_candidate_score_0_to_3={avg_candidate_score:.4f}")
    print(f"avg_opt0_cost={avg_opt0_cost:.4f}")
    print(f"avg_opt3_cost={avg_opt3_cost:.4f}")
    print(f"artifacts_dir={artifact_root}")
    print("")

    for row in results:
        print(
            f"{row['case_id']}: candidate_cost={row['candidate']['cost']:.4f}, "
            f"candidate_score={row['candidate']['score_0_to_3']:.4f}, "
            f"opt0={row['references']['opt_0']['cost']:.4f}, "
            f"opt3={row['references']['opt_3']['cost']:.4f}"
        )
        for opt_level in (0, 1, 2, 3):
            ref = row["references"][f"opt_{opt_level}"]
            print(
                f"  opt{opt_level}: cost={ref['cost']:.4f}, "
                f"score_0_to_3={ref['score_0_to_3']:.4f}, "
                f"runtime_s={ref['runtime_s']:.6f}"
            )

    if args.json_out is not None:
        payload = {
            "task": "task_02_clifford_t_synthesis",
            "summary": {
                "cases": len(results),
                "avg_candidate_cost": avg_candidate_cost,
                "avg_candidate_score_0_to_3": avg_candidate_score,
                "avg_opt0_cost": avg_opt0_cost,
                "avg_opt3_cost": avg_opt3_cost,
                "artifacts_dir": str(artifact_root),
            },
            "results": results,
        }
        dump_json(args.json_out, payload)
        print(f"\nJSON report saved to {args.json_out}")


if __name__ == "__main__":
    main()
