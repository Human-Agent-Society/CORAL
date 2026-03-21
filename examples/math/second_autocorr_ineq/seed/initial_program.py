# EVOLVE-BLOCK-START
import numpy as np
from dataclasses import dataclass


@dataclass
class Hyperparameters:
    """Hyperparameters for the optimization process."""

    num_intervals: int = 50
    num_steps: int = 5000
    perturbation_scale: float = 0.05


class C2Optimizer:
    """
    Optimizes a discretized non-negative function to find a lower bound for
    the C2 constant using the unitless, piecewise-linear integral method.
    C2 = ||f*f||_2^2 / (||f*f||_1 * ||f*f||_inf)
    """

    def __init__(self, hypers: Hyperparameters):
        self.hypers = hypers

    def compute_c2(self, f_values: np.ndarray) -> float:
        """Compute the C2 ratio for a non-negative function."""
        f_non_negative = np.maximum(f_values, 0.0)
        convolution = np.convolve(f_non_negative, f_non_negative, mode="full")

        # L2 norm squared via piecewise linear integration
        num_conv_points = len(convolution)
        h = 1.0 / (num_conv_points + 1)
        y_points = np.concatenate(([0.0], convolution, [0.0]))
        y1, y2 = y_points[:-1], y_points[1:]
        l2_norm_squared = float(np.sum((h / 3) * (y1**2 + y1 * y2 + y2**2)))

        # L1 norm
        norm_1 = float(np.sum(np.abs(convolution)) / (len(convolution) + 1))

        # Infinity norm
        norm_inf = float(np.max(np.abs(convolution)))

        if norm_1 * norm_inf < 1e-15:
            return 0.0

        c2_ratio = l2_norm_squared / (norm_1 * norm_inf)
        return c2_ratio

    def run_optimization(self):
        """Run a simple random perturbation optimization."""
        N = self.hypers.num_intervals

        # Initialize with uniform random values
        np.random.seed(42)
        f_values = np.random.uniform(0, 1, N)

        best_c2 = self.compute_c2(f_values)
        best_f = f_values.copy()

        print(f"Number of intervals (N): {N}, Steps: {self.hypers.num_steps}")
        print(f"Initial C2: {best_c2:.8f}")

        for step in range(self.hypers.num_steps):
            perturbation = np.random.randn(N) * self.hypers.perturbation_scale
            candidate = np.maximum(best_f + perturbation, 0.0)

            c2 = self.compute_c2(candidate)
            if c2 > best_c2:
                best_c2 = c2
                best_f = candidate.copy()

            if step % 1000 == 0 or step == self.hypers.num_steps - 1:
                print(f"Step {step:5d} | C2 = {best_c2:.8f}")

        print(f"Final C2 lower bound found: {best_c2:.8f}")
        return best_f, best_c2


def run():
    """Entry point for running the optimization."""
    hypers = Hyperparameters()
    optimizer = C2Optimizer(hypers)
    optimized_f, final_c2 = optimizer.run_optimization()

    loss_val = -final_c2
    return optimized_f, float(final_c2), float(loss_val), hypers.num_intervals


# EVOLVE-BLOCK-END
