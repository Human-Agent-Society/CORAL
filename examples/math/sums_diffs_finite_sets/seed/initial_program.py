# EVOLVE-BLOCK-START
import numpy as np
from dataclasses import dataclass


@dataclass
class Hyperparameters:
    max_integer: int = 250
    num_restarts: int = 5
    num_search_steps: int = 1000
    initial_temperature: float = 0.01


def compute_c6(u_set: np.ndarray) -> float:
    """Compute the C6 lower bound for a given set U."""
    if len(u_set) < 2:
        return -1.0

    U = np.array(u_set, dtype=int)
    u_plus_u = np.unique(U[:, None] + U[None, :])
    u_minus_u = np.unique(U[:, None] - U[None, :])

    size_U_plus_U = len(u_plus_u)
    size_U_minus_U = len(u_minus_u)
    max_U = np.max(U)

    if max_U == 0:
        return -1.0

    ratio = size_U_minus_U / size_U_plus_U
    c6_bound = 1 + np.log(ratio) / np.log(2 * max_U + 1)
    return c6_bound


def run_single_trial(hypers: Hyperparameters, seed: int):
    """Run one trial of simulated annealing search."""
    np.random.seed(seed)

    # Initialize a random sparse set, ensuring 0 is included
    sparsity = 0.95
    u_mask = np.random.random(hypers.max_integer + 1) > sparsity
    u_mask[0] = True  # Ensure 0 is included

    current_set = np.where(u_mask)[0]
    current_c6 = compute_c6(current_set)

    best_set = current_set.copy()
    best_c6 = current_c6

    for step in range(hypers.num_search_steps):
        temp = hypers.initial_temperature * (1 - step / hypers.num_search_steps)
        temp = max(temp, 1e-6)

        # Propose a random mutation: flip a random element (except 0)
        idx = np.random.randint(1, hypers.max_integer + 1)
        new_mask = u_mask.copy()
        new_mask[idx] = not new_mask[idx]

        new_set = np.where(new_mask)[0]
        if len(new_set) < 2:
            continue

        new_c6 = compute_c6(new_set)
        delta = new_c6 - current_c6

        # Accept if better, or probabilistically if worse
        if delta > 0 or np.random.random() < np.exp(delta / temp):
            u_mask = new_mask
            current_set = new_set
            current_c6 = new_c6

            if current_c6 > best_c6:
                best_c6 = current_c6
                best_set = current_set.copy()

    return best_set, best_c6


def run():
    hypers = Hyperparameters()

    best_c6 = -float("inf")
    best_set = None

    for i in range(hypers.num_restarts):
        u_set, c6 = run_single_trial(hypers, seed=42 + i)
        if c6 > best_c6:
            best_c6 = c6
            best_set = u_set

    print(f"Search complete. Best C6 lower bound found: {best_c6:.8f}")
    return best_set, best_c6


# EVOLVE-BLOCK-END
