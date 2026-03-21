import numpy as np


def run() -> np.ndarray:
    """
    Construct an arrangement of 14 points in 2D in order to maximize the area of the
    smallest triangle formed by any 3 of these points, normalized by the convex hull area.

    Returns:
        points: np.ndarray of shape (14, 2) with the x, y coordinates of the points.
    """
    n = 14
    rng = np.random.default_rng(seed=42)
    points = rng.random((n, 2))
    return points
