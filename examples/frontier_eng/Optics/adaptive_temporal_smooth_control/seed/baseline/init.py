# EVOLVE-BLOCK-START
import numpy as np


def compute_dm_commands(
    slopes: np.ndarray,
    reconstructor: np.ndarray,
    control_model: dict,
    prev_commands: np.ndarray,
    max_voltage: float = 0.25,
) -> np.ndarray:
    """
    Baseline: frame-wise independent control.

    Ignores temporal smoothness and command slew limits.
    """
    u = reconstructor @ slopes
    return np.clip(u, -max_voltage, max_voltage)
# EVOLVE-BLOCK-END
