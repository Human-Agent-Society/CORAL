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

import torch
import triton
import numpy as np

DEFAULT_SPEC = HERE / "resources" / "submission_spec.json"
ARTIFACT_PATH = Path("./output_ans").resolve()

DEVICE = triton.runtime.driver.active.get_active_torch_device()


def _determine_large_test_sizes() -> List[int]:
    """Return test size: 2^28 (268,435,456 elements)."""
    return [2**28]


DEFAULT_SEED = 1337
NUM_VECTOR_SAMPLES = 5
GPU_WARMUP_ITERS = 10
INNER_ADD_WARMUP_ITERS = 5


def warmup_gpu(iters: int = GPU_WARMUP_ITERS) -> None:
    """Run a few trivial GPU ops to warm up kernels and clocks."""
    if not torch.cuda.is_available():
        return
    torch.cuda.synchronize()
    n = 1 << 20
    a = torch.rand(n, device=DEVICE, dtype=torch.float32)
    b = torch.rand(n, device=DEVICE, dtype=torch.float32)
    for _ in range(max(1, int(iters))):
        c = a + b
    torch.cuda.synchronize()


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
        # Check if the string could be a file path (reasonable length and no newlines)
        # before calling is_file() to avoid "File name too long" errors
        is_possible_path = len(result) < 4096 and '\n' not in result
        if is_possible_path:
            candidate = Path(result)
            try:
                if candidate.is_file():
                    with ARTIFACT_PATH.open("w", encoding="utf-8") as fout:
                        json.dump({"program_path": str(candidate.resolve())}, fout)
                    return ARTIFACT_PATH
            except OSError:
                # Path too long or other OS error - treat as code string
                pass
        # Treat as code string
        with ARTIFACT_PATH.open("w", encoding="utf-8") as fout:
            fout.write(result)
        return ARTIFACT_PATH
    raise TypeError(
        "Solution.solve() must return a dict/path-string/code-string; got "
        f"{type(result)!r}."
    )


def load_add_from_artifact(artifact_path: Path) -> Any:
    """Load the add function from the artifact."""
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
            spec = importlib.util.spec_from_file_location("temp_add_module", temp_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if not hasattr(module, "add"):
                raise ValueError("Code must define an 'add' function")
            
            # Don't delete temp file - Triton JIT needs source file at compile time
            return module.add
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
        
        if not hasattr(module, "add"):
            raise ValueError("Program must define an 'add' function")
        return module.add
    
    else:
        raise ValueError("Artifact must contain either 'code' or 'program_path'")


def benchmark_add(add_func: Any, sizes: List[int], seed: int = DEFAULT_SEED, num_samples: int = NUM_VECTOR_SAMPLES) -> Dict[str, Any]:
    """Benchmark the add function against PyTorch baseline with seeding and averaging."""
    results = []
    
    # Warm up the GPU for more stable timings
    warmup_gpu(GPU_WARMUP_ITERS)
    
    for size in sizes:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        np.random.seed(seed)
        
        pytorch_ms_list = []
        cpu_ms_list = []
        custom_ms_list = []
        correctness_list = []
        
        for sample_idx in range(max(1, int(num_samples))):
            # Create test vectors deterministically
            x = torch.rand(size, device=DEVICE, dtype=torch.float32)
            y = torch.rand(size, device=DEVICE, dtype=torch.float32)
            # CPU baseline vectors
            x_cpu = x.detach().cpu()
            y_cpu = y.detach().cpu()
            
            # PyTorch baseline (GPU)
            def pytorch_add():
                return x + y
            # Inner warmup additions before timing
            if torch.cuda.is_available():
                for _ in range(INNER_ADD_WARMUP_ITERS):
                    _ = pytorch_add()
                torch.cuda.synchronize()
            pytorch_ms = triton.testing.do_bench(pytorch_add, quantiles=[0.5])
            if isinstance(pytorch_ms, (tuple, list)):
                pytorch_ms = pytorch_ms[0]
            pytorch_ms_list.append(float(pytorch_ms))
            
            # Naive CPU baseline
            def cpu_add():
                return x_cpu + y_cpu
            cpu_ms = triton.testing.do_bench(cpu_add, quantiles=[0.5])
            if isinstance(cpu_ms, (tuple, list)):
                cpu_ms = cpu_ms[0]
            cpu_ms_list.append(float(cpu_ms))
            
            # Custom implementation (GPU)
            def custom_add():
                return add_func(x, y)
            # Inner warmup additions before timing
            if torch.cuda.is_available():
                for _ in range(INNER_ADD_WARMUP_ITERS):
                    _ = custom_add()
                torch.cuda.synchronize()
            custom_ms = triton.testing.do_bench(custom_add, quantiles=[0.5])
            if isinstance(custom_ms, (tuple, list)):
                custom_ms = custom_ms[0]
            custom_ms_list.append(float(custom_ms))
            
            # Correctness test on this sample
            pytorch_result = pytorch_add()
            custom_result = custom_add()
            is_correct = torch.allclose(pytorch_result, custom_result, rtol=1e-5, atol=1e-8)
            correctness_list.append(bool(is_correct))
        
        # Aggregate timings as medians for stability
        def median(lst):
            s = sorted(lst)
            mid = len(s) // 2
            if len(s) % 2 == 1:
                return s[mid]
            return 0.5 * (s[mid - 1] + s[mid])
        
        pytorch_ms = median(pytorch_ms_list)
        cpu_ms = median(cpu_ms_list)
        custom_ms = median(custom_ms_list)
        
        # Bandwidths (GB/s)
        pytorch_bandwidth = 3 * size * 4 * 1e-9 / (pytorch_ms * 1e-3)
        cpu_bandwidth = 3 * size * 4 * 1e-9 / (cpu_ms * 1e-3)
        custom_bandwidth = 3 * size * 4 * 1e-9 / (custom_ms * 1e-3)
        
        is_correct = all(correctness_list)
        
        results.append({
            "size": size,
            "pytorch_ms": pytorch_ms,
            "cpu_ms": cpu_ms,
            "custom_ms": custom_ms,
            "pytorch_bandwidth": pytorch_bandwidth,
            "cpu_bandwidth": cpu_bandwidth,
            "custom_bandwidth": custom_bandwidth,
            "speedup": pytorch_ms / custom_ms if custom_ms > 0 else 0.0,
            "bandwidth_ratio": custom_bandwidth / cpu_bandwidth if cpu_bandwidth > 0 else 0.0,
            "is_correct": is_correct,
        })
    
    return results


def evaluate_vector_addition(add_func: Any) -> Dict[str, Any]:
    """Evaluate the performance of a vector addition implementation."""
    try:
        # Use large sizes based on GPU memory so GPU >> CPU
        sizes = _determine_large_test_sizes()
        
        # Run benchmark
        results = benchmark_add(add_func, sizes)
        
        # Enforce strict correctness: if any test fails, score 0
        if not results or not all(r["is_correct"] for r in results):
            return {
                "error": "Correctness not 100% across all samples/sizes",
                "score": 0,
                "pass_all": False,
                "total_tests": len(results),
                "passed_tests": sum(1 for r in results if r.get("is_correct")),
                "results": results,
            }
        
        # Calculate metrics
        bandwidth_ratios = [r["bandwidth_ratio"] for r in results if r["is_correct"]]
        speedups = [r["speedup"] for r in results if r["is_correct"]]
        pytorch_vs_cpu = [
            max(r["pytorch_bandwidth"] / max(r["cpu_bandwidth"], 1e-12), 1e-12)
            for r in results if r["is_correct"]
        ]
        custom_vs_cpu = [
            max(r["custom_bandwidth"] / max(r["cpu_bandwidth"], 1e-12), 1e-12)
            for r in results if r["is_correct"]
        ]
        
        if not bandwidth_ratios:
            return {
                "error": "All correctness tests failed",
                "score": 0,
                "pass_all": False,
            }
        
        geometric_mean_bandwidth_ratio = math.exp(sum(math.log(r) for r in bandwidth_ratios) / len(bandwidth_ratios))
        arithmetic_mean_bandwidth_ratio = sum(bandwidth_ratios) / len(bandwidth_ratios)
        gm_pytorch_vs_cpu = math.exp(sum(math.log(r) for r in pytorch_vs_cpu) / len(pytorch_vs_cpu))
        gm_custom_vs_cpu = math.exp(sum(math.log(r) for r in custom_vs_cpu) / len(custom_vs_cpu))
        
        # Calculate score (0-100 scale)
        # Anchor 0 at CPU naive baseline (custom/cpu = 1x)
        # Anchor 100 at 2x PyTorch GPU baseline (custom/cpu = 2 * pytorch/cpu)
        target = max(2.0 * gm_pytorch_vs_cpu, 1.0 + 1e-12)
        numerator = max(0.0, gm_custom_vs_cpu - 1.0)
        denominator = max(target - 1.0, 1e-12)
        normalized_unbounded = numerator / denominator
        normalized = max(0.0, min(1.0, normalized_unbounded))
        score_unbounded = normalized_unbounded * 100.0
        score = max(0.0, min(100.0, score_unbounded))

        return {
            "geometric_mean_bandwidth_ratio": geometric_mean_bandwidth_ratio,
            "arithmetic_mean_bandwidth_ratio": arithmetic_mean_bandwidth_ratio,
            "geometric_mean_custom_vs_cpu": gm_custom_vs_cpu,
            "geometric_mean_pytorch_vs_cpu": gm_pytorch_vs_cpu,
            "score": score,
            "score_unbounded": score_unbounded,
            "pass_all": True,
            "total_tests": len(results),
            "passed_tests": sum(1 for r in results if r["is_correct"]),
            "results": results,
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
        
        # Load add function from artifact
        add_func = load_add_from_artifact(artifact_path)
        
        # Evaluate performance
        evaluation_result = evaluate_vector_addition(add_func)
        
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
    parser = argparse.ArgumentParser(description="Evaluate vector addition solutions")
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
        print(f"Score: {result.get('score', 0):.2f}/100")
        if 'geometric_mean_bandwidth_ratio' in result:
            print(f"Geometric mean bandwidth ratio: {result['geometric_mean_bandwidth_ratio']:.3f}x")
        if 'passed_tests' in result and 'total_tests' in result:
            print(f"Tests passed: {result['passed_tests']}/{result['total_tests']}")
        if 'error' in result:
            print(f"Error: {result['error']}")
        # Print score as last line for main_loop.sh to extract
        # Format: "score score_unbounded" (space-separated)
        score = result.get('score', 0)
        score_unbounded = result.get('score_unbounded', score)
        print(f"{score} {score_unbounded}")
    else:
        print(f"Evaluation failed: {result.get('error', 'Unknown error')}")
        # Print error score as last line
        print("0")
        sys.exit(1)


if __name__ == "__main__":
    main()
