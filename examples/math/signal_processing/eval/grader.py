"""Signal processing grader.

Evaluates adaptive signal processing algorithms on multiple test signals using
the multi-objective cost function:
  J(theta) = a1*S + a2*L_recent + a3*L_avg + a4*R
where a1=0.3, a2=a3=0.2, a4=0.3.

The program file must define a run_signal_processing(noisy_signal, window_size)
function returning a dict with "filtered_signal".
"""

from __future__ import annotations

import json
import os
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle


class Grader(TaskGrader):
    """Grader for the signal processing problem.

    Score is based on a composite of smoothness, tracking accuracy,
    correlation with clean signal, noise reduction, and reliability.
    """

    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "initial_program.py")
        program_path = os.path.join(self.codebase_path, program_file)

        if not os.path.exists(program_path):
            return self.fail(f"Program file not found: {program_file}")

        timeout = self.timeout

        try:
            result = _run_evaluation(program_path, timeout, self.get_python_command())
        except TimeoutError:
            return self.fail(f"Evaluation timed out after {timeout}s")
        except Exception as e:
            return self.fail(f"Evaluation failed: {e}")

        if "error" in result:
            return self.fail(f"Error: {result['error']}")

        combined_score = result.get("combined_score", 0.0)
        composite_score = result.get("composite_score", 0.0)
        correlation = result.get("correlation", 0.0)
        noise_reduction = result.get("noise_reduction", 0.0)
        slope_changes = result.get("slope_changes", 0.0)
        lag_error = result.get("lag_error", 0.0)
        success_rate = result.get("success_rate", 0.0)
        eval_time = result.get("execution_time", 0.0)

        explanation = (
            f"Score: {combined_score:.6f} | "
            f"Composite: {composite_score:.4f} | "
            f"Correlation: {correlation:.4f} | "
            f"Noise reduction: {noise_reduction:.4f} | "
            f"Slope changes: {slope_changes:.1f} | "
            f"Lag error: {lag_error:.4f} | "
            f"Success rate: {success_rate:.2f} | "
            f"Time: {eval_time:.1f}s"
        )

        return self.score(combined_score, explanation)


def _run_evaluation(program_path: str, timeout: int, python_cmd: list[str]) -> dict:
    """Run the program in a subprocess with timeout."""
    script = textwrap.dedent(f"""\
        import json, sys, os, time, traceback
        import importlib.util
        import numpy as np
        from scipy.stats import pearsonr
        import concurrent.futures

        def run_with_timeout(func, args=(), kwargs={{}}, timeout_seconds=30):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, *args, **kwargs)
                try:
                    return future.result(timeout=timeout_seconds)
                except concurrent.futures.TimeoutError:
                    raise TimeoutError(f"Function timed out after {{timeout_seconds}} seconds")

        def safe_float(value):
            try:
                if np.isnan(value) or np.isinf(value):
                    return 0.0
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        def calculate_slope_changes(signal_data):
            if len(signal_data) < 3:
                return 0
            diffs = np.diff(signal_data)
            sign_changes = 0
            for i in range(1, len(diffs)):
                if np.sign(diffs[i]) != np.sign(diffs[i - 1]) and diffs[i - 1] != 0:
                    sign_changes += 1
            return sign_changes

        def calculate_lag_error(filtered_signal, original_signal, window_size):
            if len(filtered_signal) == 0:
                return 1.0
            delay = window_size - 1
            if len(original_signal) <= delay:
                return 1.0
            recent_filtered = filtered_signal[-1]
            recent_original = original_signal[delay + len(filtered_signal) - 1]
            return abs(recent_filtered - recent_original)

        def calculate_average_tracking_error(filtered_signal, original_signal, window_size):
            if len(filtered_signal) == 0:
                return 1.0
            delay = window_size - 1
            if len(original_signal) <= delay:
                return 1.0
            aligned_original = original_signal[delay : delay + len(filtered_signal)]
            min_length = min(len(filtered_signal), len(aligned_original))
            if min_length == 0:
                return 1.0
            filtered_aligned = filtered_signal[:min_length]
            original_aligned = aligned_original[:min_length]
            return np.mean(np.abs(filtered_aligned - original_aligned))

        def calculate_false_reversal_penalty(filtered_signal, clean_signal, window_size):
            if len(filtered_signal) < 3 or len(clean_signal) < 3:
                return 0
            delay = window_size - 1
            if len(clean_signal) <= delay:
                return 1.0
            aligned_clean = clean_signal[delay : delay + len(filtered_signal)]
            min_length = min(len(filtered_signal), len(aligned_clean))
            if min_length < 3:
                return 0
            filtered_aligned = filtered_signal[:min_length]
            clean_aligned = aligned_clean[:min_length]
            filtered_diffs = np.diff(filtered_aligned)
            clean_diffs = np.diff(clean_aligned)
            false_reversals = 0
            for i in range(1, len(filtered_diffs)):
                filtered_change = (
                    np.sign(filtered_diffs[i]) != np.sign(filtered_diffs[i - 1])
                    and filtered_diffs[i - 1] != 0
                )
                clean_change = (
                    np.sign(clean_diffs[i]) != np.sign(clean_diffs[i - 1])
                    and clean_diffs[i - 1] != 0
                )
                if filtered_change and not clean_change:
                    false_reversals += 1
            return false_reversals

        def calculate_composite_score(S, L_recent, L_avg, R, alpha=[0.3, 0.2, 0.2, 0.3]):
            S_norm = min(S / 50.0, 2.0)
            L_recent_norm = min(L_recent, 2.0)
            L_avg_norm = min(L_avg, 2.0)
            R_norm = min(R / 25.0, 2.0)
            penalty = (
                alpha[0] * S_norm + alpha[1] * L_recent_norm
                + alpha[2] * L_avg_norm + alpha[3] * R_norm
            )
            score = 1.0 / (1.0 + penalty)
            return score

        def generate_test_signals(num_signals=5):
            test_signals = []
            for i in range(num_signals):
                np.random.seed(42 + i)
                length = 500 + i * 100
                noise_level = 0.2 + i * 0.1
                t = np.linspace(0, 10, length)
                if i == 0:
                    clean = 2 * np.sin(2 * np.pi * 0.5 * t) + 0.1 * t
                elif i == 1:
                    clean = (
                        np.sin(2 * np.pi * 0.5 * t)
                        + 0.5 * np.sin(2 * np.pi * 2 * t)
                        + 0.2 * np.sin(2 * np.pi * 5 * t)
                    )
                elif i == 2:
                    clean = np.sin(2 * np.pi * (0.5 + 0.2 * t) * t)
                elif i == 3:
                    clean = np.concatenate([
                        np.ones(length // 3),
                        2 * np.ones(length // 3),
                        0.5 * np.ones(length - 2 * (length // 3)),
                    ])
                else:
                    clean = np.cumsum(np.random.randn(length) * 0.1) + 0.05 * t
                noise = np.random.normal(0, noise_level, length)
                noisy = clean + noise
                test_signals.append((noisy, clean))
            return test_signals

        # --- Main evaluation ---
        try:
            spec = importlib.util.spec_from_file_location("program", {os.path.abspath(program_path)!r})
            program = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(program)

            if not hasattr(program, "run_signal_processing"):
                print(json.dumps({{"combined_score": 0.0, "error": "Missing run_signal_processing function"}}))
                sys.exit(0)

            test_signals = generate_test_signals(5)
            all_scores = []
            all_metrics = []
            successful_runs = 0

            for i, (noisy_signal, clean_signal) in enumerate(test_signals):
                try:
                    start_time = time.time()
                    result = run_with_timeout(
                        program.run_signal_processing,
                        kwargs={{"noisy_signal": noisy_signal, "window_size": 20}},
                        timeout_seconds=10,
                    )
                    execution_time = time.time() - start_time

                    if not isinstance(result, dict) or "filtered_signal" not in result:
                        continue
                    filtered_signal = np.array(result["filtered_signal"])
                    if len(filtered_signal) == 0:
                        continue

                    window_size = 20
                    S = calculate_slope_changes(filtered_signal)
                    L_recent = calculate_lag_error(filtered_signal, noisy_signal, window_size)
                    L_avg = calculate_average_tracking_error(filtered_signal, noisy_signal, window_size)
                    R = calculate_false_reversal_penalty(filtered_signal, clean_signal, window_size)
                    composite_score = calculate_composite_score(S, L_recent, L_avg, R)

                    correlation = 0.0
                    noise_reduction = 0.0
                    try:
                        delay = window_size - 1
                        aligned_clean = clean_signal[delay : delay + len(filtered_signal)]
                        min_length = min(len(filtered_signal), len(aligned_clean))
                        if min_length > 1:
                            corr_result = pearsonr(
                                filtered_signal[:min_length], aligned_clean[:min_length]
                            )
                            correlation = corr_result[0] if not np.isnan(corr_result[0]) else 0.0
                        aligned_noisy = noisy_signal[delay : delay + len(filtered_signal)]
                        aligned_noisy = aligned_noisy[:min_length]
                        aligned_clean = aligned_clean[:min_length]
                        if min_length > 0:
                            noise_before = np.var(aligned_noisy - aligned_clean)
                            noise_after = np.var(filtered_signal[:min_length] - aligned_clean)
                            noise_reduction = (
                                (noise_before - noise_after) / noise_before
                                if noise_before > 0 else 0
                            )
                            noise_reduction = max(0, noise_reduction)
                    except Exception:
                        pass

                    metrics = {{
                        "slope_changes": safe_float(S),
                        "lag_error": safe_float(L_recent),
                        "avg_error": safe_float(L_avg),
                        "false_reversals": safe_float(R),
                        "composite_score": safe_float(composite_score),
                        "correlation": safe_float(correlation),
                        "noise_reduction": safe_float(noise_reduction),
                        "execution_time": safe_float(execution_time),
                    }}
                    all_scores.append(composite_score)
                    all_metrics.append(metrics)
                    successful_runs += 1

                except TimeoutError:
                    continue
                except Exception:
                    continue

            if successful_runs == 0:
                print(json.dumps({{
                    "combined_score": 0.0,
                    "error": "All test signals failed",
                }}))
                sys.exit(0)

            avg_composite_score = np.mean(all_scores)
            avg_slope_changes = np.mean([m["slope_changes"] for m in all_metrics])
            avg_lag_error = np.mean([m["lag_error"] for m in all_metrics])
            avg_avg_error = np.mean([m["avg_error"] for m in all_metrics])
            avg_false_reversals = np.mean([m["false_reversals"] for m in all_metrics])
            avg_correlation = np.mean([m["correlation"] for m in all_metrics])
            avg_noise_reduction = np.mean([m["noise_reduction"] for m in all_metrics])
            avg_execution_time = np.mean([m["execution_time"] for m in all_metrics])
            success_rate = successful_runs / len(test_signals)

            smoothness_score = 1.0 / (1.0 + avg_slope_changes / 20.0)
            responsiveness_score = 1.0 / (1.0 + avg_lag_error)
            accuracy_score = max(0, avg_correlation)
            efficiency_score = min(1.0, 1.0 / max(0.001, avg_execution_time))

            overall_score = (
                0.4 * avg_composite_score
                + 0.2 * smoothness_score
                + 0.2 * accuracy_score
                + 0.1 * avg_noise_reduction
                + 0.1 * success_rate
            )

            if accuracy_score < 0.1:
                overall_score = 0.0

            print(json.dumps({{
                "combined_score": safe_float(overall_score),
                "composite_score": safe_float(avg_composite_score),
                "slope_changes": safe_float(avg_slope_changes),
                "lag_error": safe_float(avg_lag_error),
                "avg_error": safe_float(avg_avg_error),
                "false_reversals": safe_float(avg_false_reversals),
                "correlation": safe_float(avg_correlation),
                "noise_reduction": safe_float(avg_noise_reduction),
                "smoothness_score": safe_float(smoothness_score),
                "responsiveness_score": safe_float(responsiveness_score),
                "accuracy_score": safe_float(accuracy_score),
                "efficiency_score": safe_float(efficiency_score),
                "execution_time": safe_float(avg_execution_time),
                "success_rate": safe_float(success_rate),
            }}))
        except Exception as e:
            print(json.dumps({{"combined_score": 0.0, "error": str(e)}}))
            sys.exit(0)
    """)
    import subprocess
    result = subprocess.run(
        [*python_cmd, "-c", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-2000:])
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(
            f"Script produced no output.\nstderr: {result.stderr.strip()[-1000:]}"
        )
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        # Handle stdout pollution from print statements
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        raise RuntimeError(
            f"No valid JSON in output.\nstdout: {stdout[-500:]}\nstderr: {result.stderr.strip()[-500:]}"
        )
