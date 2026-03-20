#!/usr/bin/env python3
import argparse
import importlib.util
import json
import math
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Tuple

# Add resources to path for imports
HERE = Path(__file__).resolve().parent
RESOURCES_DIR = HERE / "resources"
sys.path.insert(0, str(RESOURCES_DIR))

from benchmark import run_benchmark
from qknorm_baseline import customized_qknorm as baseline_qknorm
import torch
import triton

DEFAULT_SPEC = HERE / "resources" / "submission_spec.json"
ARTIFACT_PATH = Path("./output_ans").resolve()


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


def materialize_artifact(result: Any, solution_path: Path) -> Path:
    """Materialize the solution result into an artifact file."""
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(result, dict):
        with ARTIFACT_PATH.open("w", encoding="utf-8") as fout:
            json.dump(result, fout)
        return ARTIFACT_PATH
    if isinstance(result, str):
        is_possible_path = len(result) < 4096 and '\n' not in result
        if is_possible_path:
            candidate = Path(result)
            try:
                if candidate.is_file():
                    with ARTIFACT_PATH.open("w", encoding="utf-8") as fout:
                        json.dump({"program_path": str(candidate.resolve())}, fout)
                    return ARTIFACT_PATH
            except OSError:
                pass
        with ARTIFACT_PATH.open("w", encoding="utf-8") as fout:
            fout.write(result)
        return ARTIFACT_PATH
    raise TypeError(
        "Solution.solve() must return a dict/path-string/code-string; got "
        f"{type(result)!r}."
    )


def load_qknorm_from_artifact(artifact_path: Path) -> Any:
    """Load the qknorm function from the artifact."""
    with artifact_path.open("r", encoding="utf-8") as fin:
        artifact = json.load(fin)
    
    if "code" in artifact:
        # Write code to temporary file and import as module to avoid Triton source inspection issues
        import tempfile
        import os
        
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(artifact["code"])
                temp_file = f.name
            
            # Import the module
            spec = importlib.util.spec_from_file_location("temp_qknorm_module", temp_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if not hasattr(module, "qknorm"):
                raise ValueError("Code must define a 'qknorm' function")

            # Don't delete temp file - Triton JIT needs source file at compile time
            return module.qknorm
        except Exception as e:
            raise
    
    elif "program_path" in artifact:
        # Load from external file
        program_path = Path(artifact["program_path"])
        if not program_path.exists():
            raise FileNotFoundError(f"Program file not found: {program_path}")
        
        spec = importlib.util.spec_from_file_location("submitted_program", program_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load spec for {program_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if not hasattr(module, "qknorm"):
            raise ValueError("Program must define a 'qknorm' function")
        return module.qknorm
    
    else:
        raise ValueError("Artifact must contain either 'code' or 'program_path'")


def evaluate_kernel_performance(qknorm_func: Any) -> Dict[str, Any]:
    """Evaluate the performance of a qknorm implementation."""
    try:
        # Run benchmark comparing against baseline
        result = run_benchmark(qknorm_func, baseline_qknorm, print_output=False)
        
        # Extract key metrics
        geometric_mean_speedup = result["geometric_mean_speedup"]
        arithmetic_mean_speedup = result["arithmetic_mean_speedup"]
        median_speedup = result["median_speedup"]
        pass_all = result["pass_all"]
        
        # Enforce strict correctness: if any test fails, score 0
        if not pass_all:
            return {
                "error": "Correctness not 100% across all tests",
                "geometric_mean_speedup": geometric_mean_speedup,
                "arithmetic_mean_speedup": arithmetic_mean_speedup,
                "median_speedup": median_speedup,
                "score": 0,
                "pass_all": False,
                "total_tests": len(result["rows"]),
                "passed_tests": sum(1 for r in result["rows"] if r["close_passed"]),
            }
        
        score_unbounded = 100 * geometric_mean_speedup
        score = max(0, min(100, score_unbounded))

        return {
            "geometric_mean_speedup": geometric_mean_speedup,
            "arithmetic_mean_speedup": arithmetic_mean_speedup,
            "median_speedup": median_speedup,
            "score": score,
            "score_unbounded": score_unbounded,
            "pass_all": pass_all,
            "total_tests": len(result["rows"]),
            "passed_tests": sum(1 for r in result["rows"] if r["close_passed"]),
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "score": 0,
            "pass_all": False,
        }


def evaluate(solution_path: Path, spec_path: Path) -> dict:
    """Main evaluation function."""
    try:
        # Load solution module
        module = load_solution_module(solution_path)
        
        if not hasattr(module, "Solution"):
            raise ValueError("Solution module must define a 'Solution' class")
        
        solution_class = module.Solution
        solution_instance = solution_class()
        
        if not hasattr(solution_instance, "solve"):
            raise ValueError("Solution class must have a 'solve' method")
        
        # Get solution result
        result = solution_instance.solve(spec_path)
        
        # Materialize artifact
        artifact_path = materialize_artifact(result, solution_path)
        
        # Load qknorm function from artifact
        qknorm_func = load_qknorm_from_artifact(artifact_path)
        
        # Evaluate performance
        evaluation_result = evaluate_kernel_performance(qknorm_func)

        # Check if evaluation had an internal error
        if "error" in evaluation_result and "geometric_mean_speedup" not in evaluation_result:
            return {
                "status": "error",
                "artifact_path": str(artifact_path),
                **evaluation_result,
            }

        return {
            "status": "success",
            "artifact_path": str(artifact_path),
            **evaluation_result,
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "score": 0,
        }


def main():
    parser = argparse.ArgumentParser(description="Evaluate qknorm optimization solutions")
    parser.add_argument(
        "--solution-path",
        type=Path,
        default=Path("./solution.py"),
        help="Path to solution.py file",
    )
    parser.add_argument(
        "--spec-path",
        type=Path,
        default=DEFAULT_SPEC,
        help="Path to specification file",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path("./result.json"),
        help="Path to output result file",
    )
    
    args = parser.parse_args()
    
    # Run evaluation
    result = evaluate(args.solution_path, args.spec_path)
    
    # Write result
    with args.output_path.open("w", encoding="utf-8") as fout:
        json.dump(result, fout, indent=2)
    
    # Print summary
    if result["status"] == "success":
        print(f"Evaluation completed successfully!")
        print(f"Score: {result['score']:.2f}/100")
        print(f"Geometric mean speedup: {result['geometric_mean_speedup']:.3f}x")
        print(f"Tests passed: {result['passed_tests']}/{result['total_tests']}")
        # Print score as last line for main_loop.sh to extract
        # Format: "score score_unbounded" (space-separated)
        print(f"{result['score']} {result.get('score_unbounded', result['score'])}")
    else:
        print(f"Evaluation failed: {result.get('error', 'Unknown error')}")
        # Print error score as last line
        print("0")
        sys.exit(1)


if __name__ == "__main__":
    main()
