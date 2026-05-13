# EVOLVE-BLOCK-START
import numpy as np


def compute_dm_commands(
    slopes: np.ndarray,
    reconstructor: np.ndarray,
    control_model: dict,
    prev_commands: np.ndarray | None = None,
    max_voltage: float = 0.15,
) -> np.ndarray:
    """
    Baseline: one-shot linear control + hard clipping.

    This intentionally ignores the constrained least-squares structure.
    """
    u = reconstructor @ slopes
    return np.clip(u, -max_voltage, max_voltage)
# EVOLVE-BLOCK-END
