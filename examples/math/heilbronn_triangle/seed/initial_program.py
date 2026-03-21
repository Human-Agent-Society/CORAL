import numpy as np


def run() -> np.ndarray:
    """
    Construct an arrangement of 11 points inside an equilateral triangle
    with vertices (0,0), (1,0), (0.5, sqrt(3)/2) in order to maximize
    the area of the smallest triangle formed by any 3 of these points.

    Returns:
        points: np.ndarray of shape (11, 2) with the x, y coordinates of the points.
    """
    n = 11
    points = np.zeros((n, 2))
    return points
