"""Initial EngDesign unified submission baseline.

Edit values inside `SUBMISSION` only.
"""

# EVOLVE-BLOCK-START
def _traj(points: list[tuple[int, int, int]]) -> list[dict[str, int]]:
    return [{"t": t, "x": x, "y": y} for (t, x, y) in points]


def _zeros(rows: int, cols: int) -> list[list[float]]:
    return [[0.0 for _ in range(cols)] for _ in range(rows)]


CY03_VIOBLK_READ = """
def vioblk_read(vioblk, pos, buf, len):
    if vioblk is None or buf is None:
        return -1
    if pos < 0 or len < 0 or pos >= vioblk.capacity:
        return -1
    return -1
""".strip()


CY03_VIOBLK_WRITE = """
def vioblk_write(vioblk, pos, buf, len):
    if vioblk is None or buf is None:
        return -1
    if pos < 0 or len < 0 or pos >= vioblk.capacity:
        return -1
    return -1
""".strip()


WJ01_FUNCTION_CODE = """
def denoise_image(noisy_img):
    import numpy as np
    return np.zeros_like(noisy_img)
""".strip()


XY05_PORTS_TABLE = {}
XY05_EXPLANATION = {}
XY05_STATE_TRANSITIONS = {}


SUBMISSION = {
    "AM_02": {
        "reasoning": "Weak baseline with intentionally simple trajectories.",
        "config": {
            "robot_trajectory1": _traj(
                [
                    (0, 0, 0),
                    (1, 0, 0),
                    (2, 0, 0),
                    (3, 0, 0),
                    (4, 0, 0),
                    (5, 0, 0),
                    (6, 0, 0),
                    (7, 0, 0),
                    (8, 0, 0),
                    (9, 0, 0),
                    (10, 0, 0),
                    (11, 0, 0),
                    (12, 0, 0),
                    (13, 0, 0),
                    (14, 0, 0),
                    (15, 0, 0),
                    (16, 0, 0),
                    (17, 0, 0),
                    (18, 0, 0),
                    (19, 0, 0),
                ]
            ),
            "robot_trajectory2": _traj(
                [
                    (0, 1, 1),
                    (1, 1, 1),
                    (2, 1, 1),
                    (3, 1, 1),
                    (4, 1, 1),
                    (5, 1, 1),
                    (6, 1, 1),
                    (7, 1, 1),
                    (8, 1, 1),
                    (9, 1, 1),
                    (10, 1, 1),
                    (11, 1, 1),
                    (12, 1, 1),
                    (13, 1, 1),
                    (14, 1, 1),
                    (15, 1, 1),
                    (16, 1, 1),
                    (17, 1, 1),
                    (18, 1, 1),
                    (19, 1, 1),
                ]
            ),
        },
    },
    "AM_03": {
        "reasoning": "Weak baseline with intentionally simple trajectories.",
        "config": {
            "robot_trajectory": _traj(
                [
                    (0, 2, 2),
                    (1, 2, 2),
                    (2, 2, 2),
                    (3, 2, 2),
                    (4, 2, 2),
                    (5, 2, 2),
                    (6, 2, 2),
                    (7, 2, 2),
                    (8, 2, 2),
                    (9, 2, 2),
                    (10, 2, 2),
                    (11, 2, 2),
                    (12, 2, 2),
                    (13, 2, 2),
                    (14, 2, 2),
                    (15, 2, 2),
                    (16, 2, 2),
                    (17, 2, 2),
                    (18, 2, 2),
                    (19, 2, 2),
                    (20, 2, 2),
                    (21, 2, 2),
                    (22, 2, 2),
                    (23, 2, 2),
                    (24, 2, 2),
                    (25, 2, 2),
                    (26, 2, 2),
                    (27, 2, 2),
                    (28, 2, 2),
                    (29, 2, 2),
                ]
            )
        },
    },
    "CY_03": {
        "reasoning": "Weak baseline implementation for vioblk read/write.",
        "config": {
            "vioblk_read": CY03_VIOBLK_READ,
            "vioblk_write": CY03_VIOBLK_WRITE,
        },
    },
    "WJ_01": {
        "reasoning": "Weak baseline that returns an all-zero image.",
        "config": {
            "denoising_strategy": "Return a zero image as placeholder baseline.",
            "filter_sequence": ["zeros_like(noisy_img)"],
            "function_code": WJ01_FUNCTION_CODE,
        },
    },
    "XY_05": {
        "reasoning": "Weak baseline with empty control table.",
        "config": {
            "ports_table": XY05_PORTS_TABLE,
            "explanation": XY05_EXPLANATION,
            "state_transitions": XY05_STATE_TRANSITIONS,
        },
    },
    "YJ_02": {
        "reasoning": "Weak baseline with wrong compliance prediction.",
        "config": {
            "y_hat": _zeros(1, 1),
            "C_y_hat": 0.0,
        },
    },
    "YJ_03": {
        "reasoning": "Weak baseline with wrong stress prediction.",
        "config": {
            "y_hat": _zeros(1, 1),
            "K_y_hat": 0.0,
        },
    },
}
# EVOLVE-BLOCK-END
