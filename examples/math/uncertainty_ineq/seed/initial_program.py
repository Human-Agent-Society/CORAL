# EVOLVE-BLOCK-START
import numpy as np
from dataclasses import dataclass
from scipy.special import hermite


@dataclass
class Hyperparameters:
    learning_rate: float = 0.001
    num_steps: int = 50000
    num_restarts: int = 10
    num_hermite_coeffs: int = 4  # uses H0, H4, H8, H12


class UncertaintyOptimizer:
    """
    Finds coefficients for a generalized Hermite polynomial P(x) that minimize
    the largest positive root, providing an upper bound for C4.
    """

    def __init__(self, hypers: Hyperparameters):
        self.hypers = hypers
        self.degrees = [4 * k for k in range(hypers.num_hermite_coeffs)]
        self.hermite_polys = [hermite(d) for d in self.degrees]
        self.H_vals_at_zero = np.array([p(0) for p in self.hermite_polys])
        self.x_grid = np.linspace(0.0, 10.0, 3000)

    def build_polynomial(self, c_others, c_last):
        """Build the polynomial from Hermite coefficients with P(0)=0 constraint."""
        # Enforce P(0) = 0 by solving for c0
        c0 = (
            -(np.sum(c_others * self.H_vals_at_zero[1:-1]) + c_last * self.H_vals_at_zero[-1])
            / self.H_vals_at_zero[0]
        )
        hermite_coeffs = np.concatenate([[c0], np.array(c_others), [c_last]])
        return hermite_coeffs

    def evaluate_polynomial(self, hermite_coeffs):
        """Evaluate the polynomial on the grid and compute loss (negative values)."""
        max_degree = self.degrees[-1]
        P_poly_coeffs = np.zeros(max_degree + 1)
        for i, c in enumerate(hermite_coeffs):
            poly = self.hermite_polys[i]
            pad_amount = max_degree - poly.order
            P_poly_coeffs[pad_amount:] += c * poly.coef

        p_values = np.polyval(P_poly_coeffs, self.x_grid)
        return P_poly_coeffs, p_values

    def compute_c4(self, hermite_coeffs):
        """Compute r_max and C4 from Hermite coefficients."""
        max_degree = self.degrees[-1]
        P_poly_coeffs = np.zeros(max_degree + 1)
        for i, c in enumerate(hermite_coeffs):
            poly = self.hermite_polys[i]
            pad_amount = max_degree - poly.order
            P_poly_coeffs[pad_amount:] += c * poly.coef

        # Ensure leading coefficient is positive
        if P_poly_coeffs[0] < 0:
            P_poly_coeffs = -P_poly_coeffs
            hermite_coeffs = -hermite_coeffs

        P = np.poly1d(P_poly_coeffs)

        # Divide by x^2
        Q, R = np.polydiv(P, np.poly1d([1.0, 0.0, 0.0]))
        if np.max(np.abs(R.c)) > 1e-10:
            return None, None, None

        roots = Q.r
        real_pos = roots[(np.isreal(roots)) & (roots.real > 0)].real
        if real_pos.size == 0:
            return None, None, None

        # Find largest positive root with sign change
        r_candidates = np.sort(real_pos)
        r_max = None
        for r in r_candidates:
            eps = 1e-10 * max(1.0, abs(r))
            left = np.polyval(Q, r - eps)
            right = np.polyval(Q, r + eps)
            if left * right < 0:
                r_max = float(r)
        if r_max is None:
            r_max = float(r_candidates[-1])

        c4 = (r_max ** 2) / (2 * np.pi)
        return hermite_coeffs, c4, r_max


def run():
    hypers = Hyperparameters()
    optimizer = UncertaintyOptimizer(hypers)

    best_c4_bound = float("inf")
    best_coeffs = None
    best_r_max = None

    # Known good starting point
    base_c1 = -0.01158510802599293
    base_c2 = -8.921606035407065e-05
    base_log_c_last = np.log(1e-6)

    for trial in range(hypers.num_restarts):
        np.random.seed(42 + trial)

        # Perturb around known good point
        c1 = base_c1 + np.random.normal() * 1e-3
        c2 = base_c2 + np.random.normal() * 1e-5
        log_c_last = base_log_c_last + np.random.normal() * 0.5
        c_last = np.exp(log_c_last)

        c_others = np.array([c1, c2])
        hermite_coeffs = optimizer.build_polynomial(c_others, c_last)

        # Simple gradient-free optimization via perturbation
        current_result = optimizer.compute_c4(hermite_coeffs)
        if current_result[1] is None:
            continue

        _, current_c4, current_r_max = current_result

        for step in range(hypers.num_steps):
            # Random perturbation
            delta = np.random.normal(size=3) * np.array([1e-5, 1e-7, 0.1])
            new_c1 = c1 + delta[0]
            new_c2 = c2 + delta[1]
            new_log_c_last = log_c_last + delta[2]
            new_c_last = np.exp(new_log_c_last)

            new_c_others = np.array([new_c1, new_c2])
            new_coeffs = optimizer.build_polynomial(new_c_others, new_c_last)
            new_result = optimizer.compute_c4(new_coeffs)

            if new_result[1] is not None and new_result[1] < current_c4:
                c1, c2, log_c_last = new_c1, new_c2, new_log_c_last
                c_last = new_c_last
                hermite_coeffs = new_coeffs
                current_c4 = new_result[1]
                current_r_max = new_result[2]

        if current_c4 < best_c4_bound:
            best_c4_bound = current_c4
            best_coeffs = hermite_coeffs
            best_r_max = current_r_max

    if best_coeffs is None:
        raise RuntimeError("Failed to find a valid solution in any restart.")

    print(f"Best C4 upper bound: {best_c4_bound:.8f}")
    print(f"Best r_max: {best_r_max:.8f}")

    return best_coeffs, best_c4_bound, best_r_max


# EVOLVE-BLOCK-END
