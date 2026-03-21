# EVOLVE-BLOCK-START
import numpy as np
from dataclasses import dataclass


@dataclass
class Hyperparameters:
    """Hyperparameters for the optimization process."""

    num_intervals: int = 600
    learning_rate: float = 0.005
    num_steps: int = 5000
    perturbation_scale: float = 0.01


class AutocorrelationOptimizer:
    """
    Optimizes a discretized non-negative function to find the minimal C1 constant.
    C1 = max(autoconvolution(f)) / (integral(f))^2
    """

    def __init__(self, hypers: Hyperparameters):
        self.hypers = hypers
        self.domain_width = 0.5
        self.dx = self.domain_width / self.hypers.num_intervals

    def compute_c1(self, f_values: np.ndarray) -> float:
        """Compute the C1 ratio for a non-negative function."""
        f_non_negative = np.maximum(f_values, 0.0)
        integral_f = np.sum(f_non_negative) * self.dx

        if integral_f < 1e-9:
            return float("inf")

        autoconv = np.convolve(f_non_negative, f_non_negative, mode="full") * self.dx
        max_conv = np.max(autoconv)
        c1_ratio = max_conv / (integral_f ** 2)
        return float(c1_ratio)

    def run_optimization(self):
        """Run a simple random perturbation optimization."""
        N = self.hypers.num_intervals

        # Initialize with a hat function
        f_values = np.zeros(N)
        start_idx, end_idx = N // 4, 3 * N // 4
        f_values[start_idx:end_idx] = 1.0

        best_c1 = self.compute_c1(f_values)
        best_f = f_values.copy()

        print(f"Number of intervals (N): {N}, Steps: {self.hypers.num_steps}")
        print(f"Initial C1: {best_c1:.8f}")

        np.random.seed(42)
        for step in range(self.hypers.num_steps):
            # Random perturbation
            perturbation = np.random.randn(N) * self.hypers.perturbation_scale
            candidate = np.maximum(best_f + perturbation, 0.0)

            c1 = self.compute_c1(candidate)
            if c1 < best_c1:
                best_c1 = c1
                best_f = candidate.copy()

            if step % 1000 == 0 or step == self.hypers.num_steps - 1:
                print(f"Step {step:5d} | C1 = {best_c1:.8f}")

        print(f"Final C1 found: {best_c1:.8f}")
        return best_f, best_c1


def run():
    """Entry point for running the optimization and returning results."""
    hypers = Hyperparameters()
    optimizer = AutocorrelationOptimizer(hypers)

    optimized_f, final_c1 = optimizer.run_optimization()

    return optimized_f, final_c1, final_c1, hypers.num_intervals


# EVOLVE-BLOCK-END
