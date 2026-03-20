#!/usr/bin/env python3
import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
RESOURCES = HERE / "resources"
SPEC_PATH = RESOURCES / "submission_spec.json"
OUTPUT_PROGRAM = HERE / "output_program.py"

sys.path.insert(0, str(RESOURCES))

from simulator import BCSimulator  # noqa: E402
from utils import make_nx_graph  # noqa: E402


def load_solution_module(solution_path: Path) -> ModuleType:
    if not solution_path.exists():
        raise FileNotFoundError(f"solution.py not found at {solution_path}")
    spec = importlib.util.spec_from_file_location("submitted_solution", solution_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load spec for {solution_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # Register before exec for self-referential imports
    spec.loader.exec_module(module)
    return module


def materialize_program(result: Any) -> Path:
    if isinstance(result, dict):
        if "program_path" in result:
            candidate = Path(result["program_path"]).expanduser()
            if not candidate.exists():
                raise FileNotFoundError(f"Provided program_path does not exist: {candidate}")
            return candidate
        if "code" in result:
            OUTPUT_PROGRAM.write_text(result["code"], encoding="utf-8")
            return OUTPUT_PROGRAM
    if isinstance(result, str):
        # treat as code snippet
        OUTPUT_PROGRAM.write_text(result, encoding="utf-8")
        return OUTPUT_PROGRAM
    raise TypeError("Solution.solve must return dict with 'code' or 'program_path', or a raw code string.")


def load_program_module(program_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("candidate_program", program_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load candidate program from {program_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate_search_algorithm(program_module: ModuleType, config_files: List[Path], num_vms: int) -> Dict[str, Any]:
    if not hasattr(program_module, "search_algorithm"):
        return {
            "score": 0.0,
            "combined_score": 0.0,
            "runs_successfully": 0.0,
            "error": "Missing search_algorithm function",
        }

    search_algorithm = getattr(program_module, "search_algorithm")
    total_cost = 0.0
    total_transfer_time = 0.0
    successful = 0

    with tempfile.TemporaryDirectory() as temp_dir:
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        try:
            cost_csv = RESOURCES / "profiles" / "cost.csv"
            throughput_csv = RESOURCES / "profiles" / "throughput.csv"

            for config_path in config_files:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                config_name = config_path.stem

                graph = make_nx_graph(
                    cost_path=str(cost_csv),
                    throughput_path=str(throughput_csv),
                    num_vms=num_vms,
                )

                bc_topology = search_algorithm(
                    config["source_node"],
                    config["dest_nodes"],
                    graph,
                    config["num_partitions"],
                )

                bc_topology.set_num_partitions(config["num_partitions"])

                simulator = BCSimulator(num_vms=num_vms, output_dir="evals")
                transfer_time, cost = simulator.evaluate_path(bc_topology, config)

                total_cost += cost
                total_transfer_time += transfer_time
                successful += 1
        finally:
            os.chdir(original_cwd)

    if successful == 0:
        return {
            "score": 0.0,
            "combined_score": 0.0,
            "runs_successfully": 0.0,
            "error": "No configurations evaluated successfully",
        }

    cost_score = 1.0 / (1.0 + total_cost)
    time_score = 1.0 / (1.0 + total_transfer_time)
    combined_score = cost_score
    score_unbounded = combined_score * 100
    score = score_unbounded

    return {
        "score": score,
        "score_unbounded": score_unbounded,
        "combined_score": combined_score,
        "runs_successfully": 1.0,
        "cost_score": cost_score,
        "time_score": time_score,
        "total_cost": total_cost,
        "total_transfer_time": total_transfer_time,
        "successful_runs": successful,
    }


class Evaluator:
    def __init__(self):
        """Initialize evaluator with hard-coded environment setup and load test traces"""
        # Hard code in evaluator, env setup (done in prepare_env.py)
        self.spec_path = SPEC_PATH
        self.output_program = OUTPUT_PROGRAM
        
        # Load test traces (config files)
        spec = json.loads(self.spec_path.read_text(encoding="utf-8"))
        self.config_files = [RESOURCES / Path(cfg) for cfg in spec["config_files"]]
        self.num_vms = spec["num_vms"]

    def evaluate(self, solution):
        """
        Evaluate the solution using the loaded traces
        Args:
            solution: Solution instance with solve() method
        Returns:
            Dict with score and other metrics
        """
        # Call solution.solve() with trace config and traces
        result = solution.solve(str(self.spec_path))
        program_path = materialize_program(result)
        program_module = load_program_module(program_path)

        # Calculate score using the search algorithm
        metrics = evaluate_search_algorithm(program_module, self.config_files, self.num_vms)
        return metrics


def evaluate(solution_path: Path, spec_path: Path) -> Dict[str, Any]:
    """Legacy function for backward compatibility"""
    solution_module = load_solution_module(solution_path)
    if not hasattr(solution_module, "Solution"):
        raise AttributeError("solution.py must define a Solution class with a solve method")
    solution_obj = solution_module.Solution()
    if not hasattr(solution_obj, "solve"):
        raise AttributeError("Solution class must define a solve(spec_path: str) method")

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    result = solution_obj.solve(str(spec_path))
    program_path = materialize_program(result)
    program_module = load_program_module(program_path)

    config_files = [RESOURCES / Path(cfg) for cfg in spec["config_files"]]
    metrics = evaluate_search_algorithm(program_module, config_files, spec["num_vms"])
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate cloudcast broadcast optimizer")
    parser.add_argument("--solution", default="/work/execution_env/solution_env/solution.py")
    parser.add_argument("--spec", default=str(SPEC_PATH))
    parser.add_argument("--out", default="results.json")
    args = parser.parse_args()

    solution_path = Path(args.solution).resolve()
    spec_path = Path(args.spec).resolve()
    out_path = Path(args.out).resolve()
    try:
        module = load_solution_module(solution_path)
        
        # Use new Solution class format
        solution_class = getattr(module, "Solution", None)
        if solution_class is None:
            raise AttributeError("Solution class not found in solution.py")
        
        print("[evaluator] Using Solution class format", file=sys.stderr)
        evaluator = Evaluator()
        solution = solution_class()
        payload = evaluator.evaluate(solution)
        
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        # Format: "score score_unbounded" (space-separated)
        print(f"{payload['score']} {payload.get('score_unbounded', payload['score'])}")
    except Exception as exc:
        error_payload = {"score": 0.0, "error": str(exc)}
        out_path.write_text(json.dumps(error_payload, indent=2), encoding="utf-8")
        print("0")
        raise


if __name__ == "__main__":
    main()
