import importlib.util
import os
import pickle
import signal
import subprocess
import sys
import tempfile
import time
import traceback

import numpy as np


class TimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    """Handle timeout signal"""
    raise TimeoutError("Function execution timed out")


def validate_schedule(txn_seq):
    for i in range(len(txn_seq)):
        if not i in txn_seq:
            return False

    return True


def run_with_timeout(program_path, timeout_seconds=20):
    """
    Run the program in a separate process with timeout
    using a simple subprocess approach

    Args:
        program_path: Path to the program file
        timeout_seconds: Maximum execution time in seconds

    Returns:
        makespan, schedule tuple from the program
    """
    # Create a temporary file to execute
    # Ensure the scheduling module directory is on sys.path for imports like `import workloads`
    sched_dir = os.path.dirname(os.path.abspath(__file__))
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as temp_file:
        # Write a script that executes the program and saves results
        script = f"""
import sys
import numpy as np
import os
import pickle
import traceback

# Add the directory to sys.path
sys.path.insert(0, os.path.dirname('{program_path}'))
# Also add the scheduling directory for importing sibling modules like `workloads`
sys.path.insert(0, r'{sched_dir}')

# Debugging info
print(f"Running in subprocess, Python version: {{sys.version}}")
print(f"Program path: {program_path}")

try:
    # Import the program
    spec = __import__('importlib.util').util.spec_from_file_location("program", '{program_path}')
    program = __import__('importlib.util').util.module_from_spec(spec)
    spec.loader.exec_module(program)
    
    # Run the packing function
    print("Calling scheduling()...")
    makespan, schedule = program.get_random_costs()
    print(f"scheduling() returned successfully: makespan = {{makespan}}")

    # Save results to a file
    results = {{
        'makespan': makespan,
        'schedule': schedule,
    }}

    with open('{temp_file.name}.results', 'wb') as f:
        pickle.dump(results, f)
    print(f"Results saved to {temp_file.name}.results")
    
except Exception as e:
    # If an error occurs, save the error instead
    print(f"Error in subprocess: {{str(e)}}")
    traceback.print_exc()
    with open('{temp_file.name}.results', 'wb') as f:
        pickle.dump({{'error': str(e)}}, f)
    print(f"Error saved to {temp_file.name}.results")
"""
        temp_file.write(script.encode())
        temp_file_path = temp_file.name

    results_path = f"{temp_file_path}.results"

    try:
        # Run the script with timeout
        process = subprocess.Popen(
            [sys.executable, temp_file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
            exit_code = process.returncode

            # Always print output for debugging purposes
            print(f"Subprocess stdout: {stdout.decode()}")
            if stderr:
                print(f"Subprocess stderr: {stderr.decode()}")

            # Still raise an error for non-zero exit codes, but only after printing the output
            if exit_code != 0:
                raise RuntimeError(f"Process exited with code {exit_code}")

            # Load the results
            if os.path.exists(results_path):
                with open(results_path, "rb") as f:
                    results = pickle.load(f)

                # Check if an error was returned
                if "error" in results:
                    raise RuntimeError(f"Program execution failed: {results['error']}")

                return results["makespan"], results["schedule"]
            else:
                raise RuntimeError("Results file not found")

        except subprocess.TimeoutExpired:
            # Kill the process if it times out
            process.kill()
            process.wait()
            raise TimeoutError(f"Process timed out after {timeout_seconds} seconds")

    finally:
        # Clean up temporary files
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        if os.path.exists(results_path):
            os.unlink(results_path)


def evaluate(program_path):
    """
    Evaluate the program by running it once and checking the schedule

    Args:
        program_path: Path to the program file

    Returns:
        Dictionary of metrics
    """

    try:
        # For constructor-based approaches, a single evaluation is sufficient
        # since the result is deterministic
        start_time = time.time()

        # Use subprocess to run with timeout
        makespan, schedule = run_with_timeout(
            program_path, timeout_seconds=600  # Single timeout
        )

        end_time = time.time()
        eval_time = end_time - start_time

        # Validate solution
        valid = True
        for s in schedule:
            valid &= validate_schedule(s)
            if not valid:
                break

        # Validity score
        validity = 1.0 if valid else 0.0

        # Combined score - higher is better, positive values that scale with makespan
        # Use reciprocal scaling: higher makespan = lower score, but always positive
        combined_score = 1000 / (1 + makespan) * 1000 

        print(f"Evaluation: valid={valid}, makespan={makespan}, time={eval_time:.2f}s")

        return {
            "makespan": float(makespan),
            "schedule": float(len(schedule)),
            "validity": float(validity),
            "combined_score": float(combined_score),
        }

    except Exception as e:
        print(f"Evaluation failed completely: {str(e)}")
        traceback.print_exc()
        return {
            "makespan": 0.0,
            "schedule": 0.0,
            "validity": 0.0,
            "combined_score": 0.0,
        }

# Stage-based evaluation for cascade evaluation
def evaluate_stage1(program_path):
    """
    First stage evaluation - quick validation check
    """
    try:
        # Use the simplified subprocess approach
        try:
            makespan, schedule = run_with_timeout(program_path, timeout_seconds=600)

            valid = True
            for s in schedule:
                valid &= validate_schedule(s)
                if not valid:
                    break

            # Simple combined score for stage 1 - positive values that scale with makespan
            combined_score = 1000 / (1 + makespan) * 1000 if valid else 0.0

            # Return evaluation metrics
            return {
                "validity": 1.0 if valid else 0.0,
                "makespan": float(makespan),
                "schedule": float(len(schedule)),
                "combined_score": float(combined_score),
            }

        except TimeoutError as e:
            print(f"Stage 1 evaluation timed out: {e}")
            return {"validity": 0.0, "combined_score": 0.0, "error": "Timeout"}
        except Exception as e:
            print(f"Stage 1 evaluation failed: {e}")
            print(traceback.format_exc())
            return {"validity": 0.0, "combined_score": 0.0, "error": str(e)}

    except Exception as e:
        print(f"Stage 1 evaluation failed completely: {e}")
        print(traceback.format_exc())
        return {"validity": 0.0, "combined_score": 0.0, "error": str(e)}


def evaluate_stage2(program_path):
    """
    Second stage evaluation - full evaluation
    """
    # Full evaluation as in the main evaluate function
    return evaluate(program_path)


if __name__ == "__main__":
    # Backwards-compat: bridges old evaluate() -> dict to the container JSON
    # protocol.  wrapper.py is auto-injected at build time from
    # skydiscover/evaluation/wrapper.py.
    from wrapper import run

    run(evaluate)
