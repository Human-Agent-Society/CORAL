import numpy as np


def run():
    """
    Constructs a packing of 11 disjoint unit regular hexagons inside a larger
    regular hexagon, maximizing 1/outer_hex_side_length.

    Returns:
        inner_hex_data: np.ndarray of shape (11, 3), each row is
            (x, y, angle_degrees) for each inner hexagon.
        outer_hex_data: np.ndarray of shape (3,), (x, y, angle_degrees)
            for the outer hexagon.
        outer_hex_side_length: float, side length of the outer hexagon.
    """
    n = 11
    # Simple grid arrangement of inner hexagons
    inner_hex_data = np.array(
        [
            [0, 0, 0],  # center
            [-2.5, 0, 0],  # left
            [2.5, 0, 0],  # right
            [-1.25, 2.17, 0],  # top-left
            [1.25, 2.17, 0],  # top-right
            [-1.25, -2.17, 0],  # bottom-left
            [1.25, -2.17, 0],  # bottom-right
            [-3.75, 2.17, 0],  # far top-left
            [3.75, 2.17, 0],  # far top-right
            [-3.75, -2.17, 0],  # far bottom-left
            [3.75, -2.17, 0],  # far bottom-right
        ]
    )

    outer_hex_data = np.array([0, 0, 0])  # centered at origin
    outer_hex_side_length = 8  # large enough to contain all inner hexagons

    return inner_hex_data, outer_hex_data, outer_hex_side_length
