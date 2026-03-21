# EVOLVE-BLOCK-START
import numpy as np
from dataclasses import dataclass


@dataclass
class Hyperparameters:
    num_intervals: int = 200
    learning_rate: float = 0.005
    num_steps: int = 20000
    penalty_strength: float = 1000000.0


class ErdosOptimizer:
    """
    Finds a step function h that minimizes the maximum overlap integral.
    """

    def __init__(self, hypers: Hyperparameters):
        self.hypers = hypers
        self.domain_width = 2.0
        self.dx = self.domain_width / self.hypers.num_intervals

    def compute_c5(self, h: np.ndarray) -> float:
        """Compute C5 bound via cross-correlation of h with (1-h)."""
        j = 1.0 - h
        correlation = np.correlate(h, j, mode="full") * self.dx
        return float(np.max(correlation))

    def run_optimization(self):
        """Simple optimization using random restarts and local perturbation."""
        N = self.hypers.num_intervals
        best_h = None
        best_c5 = float("inf")

        for trial in range(5):
            np.random.seed(42 + trial)

            # Initialize h so that integral is 1
            h = np.random.uniform(0.3, 0.7, N)
            h = h / (np.sum(h) * self.dx)  # Normalize integral to 1
            h = np.clip(h, 0, 1)

            # Re-normalize after clipping
            current_integral = np.sum(h) * self.dx
            if current_integral > 0:
                h = h * (1.0 / current_integral)
                h = np.clip(h, 0, 1)

            # Simple perturbation-based local search
            for step in range(self.hypers.num_steps):
                c5 = self.compute_c5(h)

                # Random perturbation
                idx = np.random.randint(0, N)
                delta = np.random.uniform(-0.02, 0.02)
                h_new = h.copy()
                h_new[idx] = np.clip(h_new[idx] + delta, 0, 1)

                # Re-normalize integral
                current_integral = np.sum(h_new) * self.dx
                if current_integral > 0:
                    h_new = h_new * (1.0 / current_integral)
                    h_new = np.clip(h_new, 0, 1)

                c5_new = self.compute_c5(h_new)
                if c5_new < c5:
                    h = h_new

            c5 = self.compute_c5(h)
            if c5 < best_c5:
                best_c5 = c5
                best_h = h.copy()

        print(f"Optimization complete. Final C5 upper bound: {best_c5:.8f}")
        return best_h, best_c5


def run():
    hypers = Hyperparameters()
    optimizer = ErdosOptimizer(hypers)
    final_h_values, c5_bound = optimizer.run_optimization()

    return final_h_values, c5_bound, hypers.num_intervals


# EVOLVE-BLOCK-END
