# EVOLVE-BLOCK-START
import numpy as np
from dataclasses import dataclass


@dataclass
class Hyperparameters:
    """Hyperparameters for the optimization process."""

    num_intervals: int = 400
    num_steps: int = 5000
    perturbation_scale: float = 0.01


class C3Optimizer:
    """
    Optimizes a function f (with positive and negative values) to find an
    upper bound for the C3 constant.
    C3 = max(|autoconvolution(f)|) / (integral(f))^2
    """

    def __init__(self, hypers: Hyperparameters):
        self.hypers = hypers
        self.domain_width = 0.5
        self.dx = self.domain_width / self.hypers.num_intervals

    def compute_c3(self, f_values: np.ndarray) -> float:
        """Compute the C3 ratio for a function (may be negative)."""
        integral_f_sq = (np.sum(f_values) * self.dx) ** 2

        if integral_f_sq < 1e-9:
            return float("inf")

        conv = np.convolve(f_values, f_values, mode="full") * self.dx
        max_abs_conv = np.max(np.abs(conv))
        c3_ratio = max_abs_conv / integral_f_sq
        return float(c3_ratio)

    def run_optimization(self):
        """Run a simple random perturbation optimization."""
        N = self.hypers.num_intervals

        # Initialize with random normal values (f can be negative for C3)
        np.random.seed(42)
        f_values = np.random.randn(N)

        best_c3 = self.compute_c3(f_values)
        best_f = f_values.copy()

        print(f"Number of intervals (N): {N}, Steps: {self.hypers.num_steps}")
        print(f"Initial C3: {best_c3:.8f}")

        for step in range(self.hypers.num_steps):
            perturbation = np.random.randn(N) * self.hypers.perturbation_scale
            candidate = best_f + perturbation

            c3 = self.compute_c3(candidate)
            if c3 < best_c3:
                best_c3 = c3
                best_f = candidate.copy()

            if step % 1000 == 0 or step == self.hypers.num_steps - 1:
                print(f"Step {step:5d} | C3 = {best_c3:.8f}")

        print(f"Final C3 upper bound found: {best_c3:.8f}")
        return best_f, best_c3


def run():
    """Entry point for running the optimization."""
    hypers = Hyperparameters()
    optimizer = C3Optimizer(hypers)
    optimized_f, final_c3 = optimizer.run_optimization()

    return optimized_f, float(final_c3), float(final_c3), hypers.num_intervals


# EVOLVE-BLOCK-END
