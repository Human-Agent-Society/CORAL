import numpy as np


def run() -> np.ndarray:
    """
    Creates 16 points in 2 dimensions in order to maximize the ratio
    (min_distance / max_distance)^2 over all pairwise distances.

    Returns:
        points: np.ndarray of shape (16, 2) containing the (x, y) coordinates of the 16 points.
    """
    n = 16
    d = 2

    # Places points randomly
    np.random.seed(42)
    points = np.random.randn(n, d)

    return points
