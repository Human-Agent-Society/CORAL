# EVOLVE-BLOCK-START
import numpy as np


def run() -> np.ndarray:
    """
    Creates 14 points in 3 dimensions to maximize the ratio of minimum to
    maximum pairwise distance: (min_dist / max_dist)^2.

    Returns:
        points: np.ndarray of shape (14, 3) containing the coordinates.
    """
    n = 14
    d = 3

    # Initialize with random points
    np.random.seed(42)
    points = np.random.randn(n, d)

    return points


# EVOLVE-BLOCK-END
